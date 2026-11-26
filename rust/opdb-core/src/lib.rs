//! EXPERIMENTAL storage v0. The file format is unstable and has no
//! compatibility promise. Append-only record log, replayed on open.
//!
//! Header: 8 bytes magic `OPDBRS0\0`, u32 LE format version.
//! Record: op u8 (1 put, 2 delete), key len u32, value len u32, key, value,
//! CRC-32 u32 over everything before it in the record. All integers LE.

use std::collections::HashMap;
use std::fs::{self, File, OpenOptions, TryLockError};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

pub const MAGIC: &[u8; 8] = b"OPDBRS0\0";
pub const FORMAT_VERSION: u32 = 0;
const HEADER_LEN: u64 = 12;
const OP_PUT: u8 = 1;
const OP_DELETE: u8 = 2;
static CREATE_NONCE: AtomicU64 = AtomicU64::new(0);

/// Largest key or value the record format can describe (lengths are u32).
pub const MAX_FIELD_LEN: usize = u32::MAX as usize;

/// A single operation in an experimental write batch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Op {
    Put(Vec<u8>, Vec<u8>),
    Delete(Vec<u8>),
}

/// Encodes a batch of operations into bytes without any file access.
///
/// Each entry is: kind u8, key length u32 LE, value length u32 LE, key,
/// value. There is no count and no checksum.
///
/// Lengths above `u32::MAX` are truncated here; use `try_encode_ops` for the
/// checked variant.
pub fn encode_ops(ops: &[Op]) -> Vec<u8> {
    let mut out = Vec::new();
    for op in ops {
        match op {
            Op::Put(key, value) => {
                out.push(OP_PUT);
                out.extend_from_slice(&(key.len() as u32).to_le_bytes());
                out.extend_from_slice(&(value.len() as u32).to_le_bytes());
                out.extend_from_slice(key);
                out.extend_from_slice(value);
            }
            Op::Delete(key) => {
                out.push(OP_DELETE);
                out.extend_from_slice(&(key.len() as u32).to_le_bytes());
                out.extend_from_slice(&0u32.to_le_bytes());
                out.extend_from_slice(key);
            }
        }
    }
    out
}

/// Checked variant of `encode_ops`: fails with `Error::TooLarge` before encoding
/// when any key or value is longer than `MAX_FIELD_LEN`.
pub fn try_encode_ops(ops: &[Op]) -> Result<Vec<u8>> {
    for op in ops {
        match op {
            Op::Put(key, value) => {
                check_field_len(key.len())?;
                check_field_len(value.len())?;
            }
            Op::Delete(key) => check_field_len(key.len())?,
        }
    }
    Ok(encode_ops(ops))
}

/// Ok when `len` fits the u32 length field of the record format.
pub fn check_field_len(len: usize) -> Result<()> {
    if len > MAX_FIELD_LEN {
        Err(Error::TooLarge { len })
    } else {
        Ok(())
    }
}

/// Decodes bytes produced by `encode_ops` back into operations.
///
/// Returns `None` when an entry is cut short, the kind is neither 1 nor 2,
/// or a delete carries a non-empty value. Never panics.
pub fn decode_ops(bytes: &[u8]) -> Option<Vec<Op>> {
    let mut pos = 0;
    let mut ops = Vec::new();
    while pos < bytes.len() {
        let kind = *bytes.get(pos)?;
        pos = pos.checked_add(1)?;
        let klen = u32::from_le_bytes(bytes.get(pos..pos.checked_add(4)?)?.try_into().ok()?) as usize;
        pos = pos.checked_add(4)?;
        let vlen = u32::from_le_bytes(bytes.get(pos..pos.checked_add(4)?)?.try_into().ok()?) as usize;
        pos = pos.checked_add(4)?;
        let key_end = pos.checked_add(klen)?;
        let key = bytes.get(pos..key_end)?.to_vec();
        pos = key_end;
        let value_end = pos.checked_add(vlen)?;
        let value = bytes.get(pos..value_end)?.to_vec();
        pos = value_end;
        match kind {
            OP_PUT => ops.push(Op::Put(key, value)),
            OP_DELETE => {
                if !value.is_empty() {
                    return None;
                }
                ops.push(Op::Delete(key));
            }
            _ => return None,
        }
    }
    Some(ops)
}

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    /// Another handle or process currently owns this store file.
    Busy,
    BadMagic,
    UnsupportedVersion(u32),
    /// A complete record failed its checksum or has an unknown op.
    Corrupt { offset: u64 },
    /// The log has an unreplayed damaged tail; call `repair` before writing.
    TailNotRepaired,
    Closed,
    /// A key or value is longer than `MAX_FIELD_LEN`; nothing was written.
    TooLarge { len: usize },
}

impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Error::Io(e)
    }
}

pub type Result<T> = std::result::Result<T, Error>;

fn crc32(data: &[u8]) -> u32 {
    let mut crc = !0u32;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            crc = if crc & 1 == 1 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

pub struct Store {
    file: Option<File>,
    index: HashMap<Vec<u8>, Vec<u8>>,
    /// End of the last valid record.
    valid_len: u64,
    /// Set when open found an incomplete record at the end of the file.
    truncated_tail_at: Option<u64>,
}

impl Store {
    fn lock(file: &File) -> Result<()> {
        match file.try_lock() {
            Ok(()) => Ok(()),
            Err(TryLockError::WouldBlock) => Err(Error::Busy),
            Err(TryLockError::Error(error)) => Err(Error::Io(error)),
        }
    }

    /// Creates a new store; fails if the file already exists.
    /// The file is published only after its lock and header are ready.
    pub fn create(path: impl AsRef<Path>) -> Result<Store> {
        let path = path.as_ref();
        if path.file_name().is_none() {
            return Err(Error::Io(io::Error::new(io::ErrorKind::InvalidInput, "store path has no file name")));
        }
        let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
        for _ in 0..16 {
            let nonce = CREATE_NONCE.fetch_add(1, Ordering::Relaxed);
            let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos();
            let temp = parent.join(format!(".opdb-create-{}-{stamp}-{nonce}.tmp", std::process::id()));
            let mut f = match OpenOptions::new().read(true).write(true).create_new(true).open(&temp) {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(Error::Io(error)),
            };
            let prepared = (|| -> Result<()> {
                Self::lock(&f)?;
                f.write_all(MAGIC)?;
                f.write_all(&FORMAT_VERSION.to_le_bytes())?;
                f.sync_all()?;
                // Hard-link creation fails if path already exists; rename could overwrite it.
                fs::hard_link(&temp, path)?;
                Ok(())
            })();
            match prepared {
                Ok(()) => {
                    // After publication, cleanup failure must not turn a valid store into an error.
                    let _ = fs::remove_file(&temp);
                    return Ok(Store { file: Some(f), index: HashMap::new(), valid_len: HEADER_LEN, truncated_tail_at: None });
                }
                Err(error) => {
                    drop(f);
                    let _ = fs::remove_file(&temp);
                    return Err(error);
                }
            }
        }
        Err(Error::Io(io::Error::new(io::ErrorKind::AlreadyExists, "temporary store name collisions")))
    }

    /// Opens an existing store and replays its log.
    pub fn open(path: impl AsRef<Path>) -> Result<Store> {
        let mut f = OpenOptions::new().read(true).write(true).open(path)?;
        Self::lock(&f)?;
        let mut data = Vec::new();
        f.read_to_end(&mut data)?;
        if data.len() < 12 || &data[..8] != MAGIC {
            return Err(Error::BadMagic);
        }
        let version = u32::from_le_bytes(data[8..12].try_into().unwrap());
        if version != FORMAT_VERSION {
            return Err(Error::UnsupportedVersion(version));
        }
        let mut index = HashMap::new();
        let mut pos = HEADER_LEN as usize;
        let mut truncated_tail_at = None;
        while pos < data.len() {
            let rest = &data[pos..];
            if rest.len() < 9 {
                truncated_tail_at = Some(pos as u64);
                break;
            }
            let klen = u32::from_le_bytes(rest[1..5].try_into().unwrap()) as usize;
            let vlen = u32::from_le_bytes(rest[5..9].try_into().unwrap()) as usize;
            let total = match 9usize.checked_add(klen).and_then(|n| n.checked_add(vlen)).and_then(|n| n.checked_add(4)) {
                Some(t) => t,
                None => return Err(Error::Corrupt { offset: pos as u64 }),
            };
            if rest.len() < total {
                truncated_tail_at = Some(pos as u64);
                break;
            }
            let body = &rest[..total - 4];
            let stored = u32::from_le_bytes(rest[total - 4..total].try_into().unwrap());
            if crc32(body) != stored || (body[0] != OP_PUT && body[0] != OP_DELETE) {
                return Err(Error::Corrupt { offset: pos as u64 });
            }
            let key = body[9..9 + klen].to_vec();
            if body[0] == OP_PUT {
                index.insert(key, body[9 + klen..].to_vec());
            } else {
                index.remove(&key);
            }
            pos += total;
        }
        let valid_len = pos as u64;
        f.seek(SeekFrom::End(0))?;
        Ok(Store { file: Some(f), index, valid_len, truncated_tail_at })
    }

    /// Offset where an incomplete trailing record starts, if open found one.
    pub fn truncated_tail(&self) -> Option<u64> {
        self.truncated_tail_at
    }

    /// Cuts off the incomplete tail so writing can continue.
    pub fn repair(&mut self) -> Result<()> {
        if self.truncated_tail_at.take().is_some() {
            let f = self.file.as_mut().ok_or(Error::Closed)?;
            f.set_len(self.valid_len)?;
            f.seek(SeekFrom::End(0))?;
            f.sync_all()?;
        }
        Ok(())
    }

    fn append(&mut self, op: u8, key: &[u8], value: &[u8]) -> Result<()> {
        if self.truncated_tail_at.is_some() {
            return Err(Error::TailNotRepaired);
        }
        check_field_len(key.len())?;
        check_field_len(value.len())?;
        let mut rec = Vec::with_capacity(13 + key.len() + value.len());
        rec.push(op);
        rec.extend_from_slice(&(key.len() as u32).to_le_bytes());
        rec.extend_from_slice(&(value.len() as u32).to_le_bytes());
        rec.extend_from_slice(key);
        rec.extend_from_slice(value);
        let crc = crc32(&rec);
        rec.extend_from_slice(&crc.to_le_bytes());
        let f = self.file.as_mut().ok_or(Error::Closed)?;
        f.write_all(&rec)?;
        self.valid_len += rec.len() as u64;
        Ok(())
    }

    pub fn put(&mut self, key: &[u8], value: &[u8]) -> Result<()> {
        self.append(OP_PUT, key, value)?;
        self.index.insert(key.to_vec(), value.to_vec());
        Ok(())
    }

    pub fn get(&self, key: &[u8]) -> Option<&[u8]> {
        self.index.get(key).map(|v| v.as_slice())
    }

    /// Deleting a missing key is allowed and returns false.
    pub fn delete(&mut self, key: &[u8]) -> Result<bool> {
        self.append(OP_DELETE, key, &[])?;
        Ok(self.index.remove(key).is_some())
    }

    pub fn len(&self) -> usize {
        self.index.len()
    }

    pub fn is_empty(&self) -> bool {
        self.index.is_empty()
    }

    /// Returns every live key with its value, sorted by key in byte order.
    /// Read-only: does not touch the file and does not change the store.
    pub fn entries(&self) -> Vec<(Vec<u8>, Vec<u8>)> {
        let mut out: Vec<(Vec<u8>, Vec<u8>)> = self.index.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
        out.sort_by(|a, b| a.0.cmp(&b.0));
        out
    }

    /// Writes a NEW store at `path` holding only the live entries, in key order.
    /// Fails (as `Store::create` does) when `path` already exists; this store is not changed.
    pub fn compact_to(&self, path: impl AsRef<Path>) -> Result<()> {
        let mut out = Store::create(path)?;
        for (key, value) in self.entries() {
            out.put(&key, &value)?;
        }
        out.close()
    }

    pub fn close(&mut self) -> Result<()> {
        if let Some(f) = self.file.take() {
            f.sync_all()?;
        }
        Ok(())
    }
}
