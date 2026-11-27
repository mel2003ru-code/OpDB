//! LSM database (L05): memtable + write-ahead log. No SSTables yet (L06..L12).
//!
//! `write_batch` appends ONE WAL record, then applies the batch to the memtable. Opening replays the
//! WAL. A torn WAL tail is reported by `torn_tail()` and never cut automatically: writes return
//! `Error::TailNotRepaired` until `repair()`.

use super::memtable::Memtable;
use super::wal::{read_wal, repair_wal, WalWriter, WAL_HEADER_LEN, WAL_MAGIC};
use super::SyncPolicy;
use crate::{Error, Op, Result};
use std::fs;
use std::path::{Path, PathBuf};

const WAL_NAME: &str = "wal-00000001.log";

pub struct Db {
    policy: SyncPolicy,
    mem: Memtable,
    wal: Option<WalWriter>,
    wal_path: PathBuf,
    torn: Option<u64>,
    closed: bool,
}

impl Db {
    /// Opens (creating when needed) the database directory and replays its WAL.
    pub fn open(dir: impl AsRef<Path>, policy: SyncPolicy) -> Result<Db> {
        let dir = dir.as_ref();
        fs::create_dir_all(dir)?;
        let wal_path = dir.join(WAL_NAME);
        let mut mem = Memtable::new();
        let mut torn = None;
        let mut wal = None;
        if wal_path.exists() {
            // A crash between creating the file and writing its header leaves a header prefix and no data.
            let raw = fs::read(&wal_path)?;
            if raw.len() < WAL_HEADER_LEN as usize && WAL_MAGIC.starts_with(&raw[..raw.len().min(8)]) {
                fs::remove_file(&wal_path)?;
            }
        }
        if wal_path.exists() {
            let replay = read_wal(&wal_path)?;
            for batch in &replay.batches {
                mem.apply(batch);
            }
            torn = replay.torn_tail;
            if torn.is_none() {
                wal = Some(WalWriter::open_append(&wal_path, policy)?);
            }
        } else {
            wal = Some(WalWriter::create(&wal_path, policy)?);
        }
        Ok(Db { policy, mem, wal, wal_path, torn, closed: false })
    }

    /// Offset of an unreplayed damaged WAL tail found at open, until `repair()`.
    pub fn torn_tail(&self) -> Option<u64> {
        self.torn
    }

    /// Cuts the torn tail; the batches replayed at open stay (they are the intact prefix).
    pub fn repair(&mut self) -> Result<()> {
        if self.closed {
            return Err(Error::Closed);
        }
        if self.torn.is_some() {
            repair_wal(&self.wal_path)?;
            self.wal = Some(WalWriter::open_append(&self.wal_path, self.policy)?);
            self.torn = None;
        }
        Ok(())
    }

    /// WAL first, then memtable: a failed append leaves the memtable unchanged.
    pub fn write_batch(&mut self, ops: &[Op]) -> Result<()> {
        if self.closed {
            return Err(Error::Closed);
        }
        if self.torn.is_some() {
            return Err(Error::TailNotRepaired);
        }
        self.wal.as_mut().ok_or(Error::Closed)?.append_batch(ops)?;
        self.mem.apply(ops);
        Ok(())
    }

    pub fn put(&mut self, key: &[u8], value: &[u8]) -> Result<()> {
        self.write_batch(&[Op::Put(key.to_vec(), value.to_vec())])
    }

    pub fn delete(&mut self, key: &[u8]) -> Result<()> {
        self.write_batch(&[Op::Delete(key.to_vec())])
    }

    /// A tombstone gives `None`.
    pub fn get(&self, key: &[u8]) -> Option<Vec<u8>> {
        self.mem.get(key).and_then(|v| v.map(|x| x.to_vec()))
    }

    /// Live entries whose key starts with `prefix`, in byte order. Memtable only for now (SSTables come in L12).
    pub fn scan(&self, prefix: &[u8]) -> Vec<(Vec<u8>, Vec<u8>)> {
        self.mem
            .iter()
            .filter(|(k, _)| k.starts_with(prefix))
            .filter_map(|(k, v)| v.map(|v| (k.to_vec(), v.to_vec())))
            .collect()
    }

    pub fn close(&mut self) -> Result<()> {
        if let Some(w) = self.wal.as_mut() {
            w.close()?;
        }
        self.wal = None;
        self.closed = true;
        Ok(())
    }
}
