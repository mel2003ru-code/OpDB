//! EXPERIMENTAL storage v0. The file format is unstable and has no
//! compatibility promise. Append-only record log, replayed on open.
//!
//! Header: 8 bytes magic `OPDBRS0\0`, u32 LE format version.
//! Record: op u8 (1 put, 2 delete), key len u32, value len u32, key, value,
//! CRC-32 u32 over everything before it in the record. All integers LE.

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;

pub const MAGIC: &[u8; 8] = b"OPDBRS0\0";
pub const FORMAT_VERSION: u32 = 0;
const HEADER_LEN: u64 = 12;
const OP_PUT: u8 = 1;
const OP_DELETE: u8 = 2;

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    BadMagic,
    UnsupportedVersion(u32),
    /// A complete record failed its checksum or has an unknown op.
    Corrupt { offset: u64 },
    /// The log has an unreplayed damaged tail; call `repair` before writing.
    TailNotRepaired,
    Closed,
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
    /// Creates a new store; fails if the file already exists.
    pub fn create(path: impl AsRef<Path>) -> Result<Store> {
        let mut f = OpenOptions::new().read(true).write(true).create_new(true).open(path)?;
        f.write_all(MAGIC)?;
        f.write_all(&FORMAT_VERSION.to_le_bytes())?;
        f.sync_all()?;
        Ok(Store { file: Some(f), index: HashMap::new(), valid_len: HEADER_LEN, truncated_tail_at: None })
    }

    /// Opens an existing store and replays its log.
    pub fn open(path: impl AsRef<Path>) -> Result<Store> {
        let mut f = OpenOptions::new().read(true).write(true).open(path)?;
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

    pub fn close(&mut self) -> Result<()> {
        if let Some(f) = self.file.take() {
            f.sync_all()?;
        }
        Ok(())
    }
}
