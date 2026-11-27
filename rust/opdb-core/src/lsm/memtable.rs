//! LSM memtable (L02): a sorted in-memory map with tombstones. No files.
//! `None` as a value is a tombstone. Keys are compared bytewise.

use crate::Op;
use std::collections::BTreeMap;

const ENTRY_OVERHEAD: usize = 16;

#[derive(Debug, Default, Clone)]
pub struct Memtable {
    map: BTreeMap<Vec<u8>, Option<Vec<u8>>>,
    bytes: usize,
}

fn cost(key: &[u8], value: &Option<Vec<u8>>) -> usize {
    key.len() + value.as_ref().map_or(0, |v| v.len()) + ENTRY_OVERHEAD
}

impl Memtable {
    pub fn new() -> Memtable {
        Memtable::default()
    }

    fn set(&mut self, key: &[u8], value: Option<Vec<u8>>) {
        let added = cost(key, &value);
        if let Some(old) = self.map.insert(key.to_vec(), value) {
            self.bytes -= cost(key, &old);
        }
        self.bytes += added;
    }

    pub fn put(&mut self, key: &[u8], value: &[u8]) {
        self.set(key, Some(value.to_vec()));
    }

    /// Stores a tombstone, also for a key this memtable has not seen.
    pub fn delete(&mut self, key: &[u8]) {
        self.set(key, None);
    }

    /// Applies the operations in order.
    pub fn apply(&mut self, ops: &[Op]) {
        for op in ops {
            match op {
                Op::Put(k, v) => self.put(k, v),
                Op::Delete(k) => self.delete(k),
            }
        }
    }

    /// `None`: unknown here. `Some(None)`: tombstone. `Some(Some(v))`: value.
    pub fn get(&self, key: &[u8]) -> Option<Option<&[u8]>> {
        self.map.get(key).map(|v| v.as_deref())
    }

    /// All entries in key order, tombstones included.
    pub fn iter(&self) -> impl Iterator<Item = (&[u8], Option<&[u8]>)> + '_ {
        self.map.iter().map(|(k, v)| (k.as_slice(), v.as_deref()))
    }

    /// Number of entries, tombstones included.
    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Sum over entries of key length + value length (0 for a tombstone) + 16.
    pub fn approx_bytes(&self) -> usize {
        self.bytes
    }
}
