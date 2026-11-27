//! LSM write-ahead log (L03 writer, L04 reader). EXPERIMENTAL format.
//!
//! Header: 8 bytes magic `OPDBWAL\0`, u32 LE version 0 (12 bytes).
//! Record: kind u8 (3 = batch), key length u32 (always 0), value length u32 (N),
//! value = `encode_ops(ops)`, crc32 u32 over everything before it in the record.
//! One batch is ONE record, so the framing and the checksum protect it as a unit.

use super::SyncPolicy;
use crate::{crc32, decode_ops, try_encode_ops, Error, Op, Result};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::Path;

pub const WAL_MAGIC: &[u8; 8] = b"OPDBWAL\0";
pub const WAL_VERSION: u32 = 0;
pub const WAL_HEADER_LEN: u64 = 12;
const KIND_BATCH: u8 = 3;
const RECORD_HEAD: usize = 9;

fn header_bytes() -> Vec<u8> {
    let mut h = Vec::with_capacity(WAL_HEADER_LEN as usize);
    h.extend_from_slice(WAL_MAGIC);
    h.extend_from_slice(&WAL_VERSION.to_le_bytes());
    h
}

fn encode_record(ops: &[Op]) -> Result<Vec<u8>> {
    let payload = try_encode_ops(ops)?;
    crate::check_field_len(payload.len())?;
    let mut rec = Vec::with_capacity(RECORD_HEAD + payload.len() + 4);
    rec.push(KIND_BATCH);
    rec.extend_from_slice(&0u32.to_le_bytes());
    rec.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    rec.extend_from_slice(&payload);
    let crc = crc32(&rec);
    rec.extend_from_slice(&crc.to_le_bytes());
    Ok(rec)
}

pub struct WalWriter {
    file: Option<File>,
    policy: SyncPolicy,
    written: u64,
}

impl WalWriter {
    /// Creates a NEW log file (fails with `Error::Io` when the path exists) and writes the header.
    pub fn create(path: impl AsRef<Path>, policy: SyncPolicy) -> Result<WalWriter> {
        let mut file = OpenOptions::new().write(true).create_new(true).open(path.as_ref())?;
        file.write_all(&header_bytes())?;
        if policy != SyncPolicy::Never {
            file.sync_all()?;
        }
        Ok(WalWriter { file: Some(file), policy, written: WAL_HEADER_LEN })
    }

    /// Continues an existing, intact log. A torn tail gives `Error::TailNotRepaired`
    /// (call `repair_wal` first), damage gives `Error::Corrupt`.
    pub fn open_append(path: impl AsRef<Path>, policy: SyncPolicy) -> Result<WalWriter> {
        let replay = read_wal(path.as_ref())?;
        if replay.torn_tail.is_some() {
            return Err(Error::TailNotRepaired);
        }
        let file = OpenOptions::new().append(true).open(path.as_ref())?;
        Ok(WalWriter { file: Some(file), policy, written: replay.valid_end })
    }

    /// Appends ONE record holding the whole batch; with `EveryBatch` it is synced before returning.
    pub fn append_batch(&mut self, ops: &[Op]) -> Result<()> {
        let rec = encode_record(ops)?;
        let file = self.file.as_mut().ok_or(Error::Closed)?;
        file.write_all(&rec)?;
        if self.policy == SyncPolicy::EveryBatch {
            file.sync_data()?;
        }
        self.written += rec.len() as u64;
        Ok(())
    }

    /// File length including the header.
    pub fn bytes_written(&self) -> u64 {
        self.written
    }

    pub fn close(&mut self) -> Result<()> {
        if let Some(f) = self.file.take() {
            if self.policy != SyncPolicy::Never {
                f.sync_all()?;
            }
        }
        Ok(())
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct WalReplay {
    pub batches: Vec<Vec<Op>>,
    /// End of the last good record (12 for an empty log).
    pub valid_end: u64,
    /// Offset of an incomplete record at the end of the file, if any.
    pub torn_tail: Option<u64>,
}

/// Reads a whole log. An INCOMPLETE record at the end is reported as `torn_tail`; a COMPLETE record
/// with a wrong checksum, kind or content is `Error::Corrupt { offset }`.
pub fn read_wal(path: impl AsRef<Path>) -> Result<WalReplay> {
    let bytes = fs::read(path.as_ref())?;
    if bytes.len() < WAL_HEADER_LEN as usize || &bytes[..8] != WAL_MAGIC {
        return Err(Error::BadMagic);
    }
    let version = u32::from_le_bytes(bytes[8..12].try_into().unwrap());
    if version != WAL_VERSION {
        return Err(Error::UnsupportedVersion(version));
    }
    let mut batches = Vec::new();
    let mut offset = WAL_HEADER_LEN as usize;
    while offset < bytes.len() {
        let rest = &bytes[offset..];
        if rest.len() < RECORD_HEAD {
            return Ok(WalReplay { batches, valid_end: offset as u64, torn_tail: Some(offset as u64) });
        }
        let kind = rest[0];
        let klen = u32::from_le_bytes(rest[1..5].try_into().unwrap()) as usize;
        let vlen = u32::from_le_bytes(rest[5..9].try_into().unwrap()) as usize;
        let total = RECORD_HEAD
            .checked_add(klen)
            .and_then(|n| n.checked_add(vlen))
            .and_then(|n| n.checked_add(4))
            .unwrap_or(usize::MAX);
        if total > rest.len() {
            return Ok(WalReplay { batches, valid_end: offset as u64, torn_tail: Some(offset as u64) });
        }
        let body = &rest[..total - 4];
        let stored = u32::from_le_bytes(rest[total - 4..total].try_into().unwrap());
        let corrupt = Error::Corrupt { offset: offset as u64 };
        if crc32(body) != stored || kind != KIND_BATCH || klen != 0 {
            return Err(corrupt);
        }
        match decode_ops(&body[RECORD_HEAD..]) {
            Some(ops) => batches.push(ops),
            None => return Err(corrupt),
        }
        offset += total;
    }
    Ok(WalReplay { batches, valid_end: offset as u64, torn_tail: None })
}

/// Cuts a torn tail (and syncs). A log without a torn tail is left untouched; a damaged log
/// returns its `Corrupt` error and is never modified.
pub fn repair_wal(path: impl AsRef<Path>) -> Result<()> {
    let replay = read_wal(path.as_ref())?;
    if replay.torn_tail.is_some() {
        let f = OpenOptions::new().write(true).open(path.as_ref())?;
        f.set_len(replay.valid_end)?;
        f.sync_all()?;
    }
    Ok(())
}
