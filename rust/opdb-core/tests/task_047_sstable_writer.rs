use opdb_core::lsm::sstable::write_sstable;
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static ID: AtomicU64 = AtomicU64::new(0);
struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!("opdb-l06-{}-{}", std::process::id(), ID.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir(&p).unwrap();
        Self(p)
    }
}
impl Drop for Temp {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
}

type Entry = (Vec<u8>, Option<Vec<u8>>);

// Independent reference CRC-32/ISO-HDLC, reflected polynomial.
fn checksum(bytes: &[u8]) -> u32 {
    let mut state = 0xffff_ffffu32;
    for byte in bytes {
        state ^= u32::from(*byte);
        for _ in 0..8 {
            state = if state & 1 == 1 { (state >> 1) ^ 0xedb8_8320 } else { state >> 1 };
        }
    }
    !state
}
fn take<'a>(s: &mut &'a [u8], n: usize) -> &'a [u8] {
    let (a,b) = s.split_at(n);
    *s = b;
    a
}
fn read32(s: &mut &[u8]) -> u32 { u32::from_le_bytes(take(s, 4).try_into().unwrap()) }
fn read64(s: &mut &[u8]) -> u64 { u64::from_le_bytes(take(s, 8).try_into().unwrap()) }
fn checked(data: &[u8]) -> &[u8] {
    let (body, tail) = data.split_at(data.len() - 4);
    assert_eq!(checksum(body), u32::from_le_bytes(tail.try_into().unwrap()));
    body
}
fn parse(bytes: &[u8]) -> (Vec<Entry>, usize) {
    let (data, footer) = bytes.split_at(bytes.len() - 36);
    let mut f = checked(footer);
    assert_eq!(take(&mut f, 8), b"OPDBSST\0");
    assert_eq!(read32(&mut f), 0);
    let index_offset = read64(&mut f) as usize;
    let index_len = read32(&mut f) as usize;
    let entry_count = read64(&mut f);
    assert!(f.is_empty());
    assert_eq!(index_offset + index_len, data.len());
    let mut index = checked(&data[index_offset..]);
    let blocks = read32(&mut index) as usize;
    let mut expected_offset = 0;
    let mut result = Vec::new();
    for _ in 0..blocks {
        let n = read32(&mut index) as usize;
        let first = take(&mut index, n);
        let offset = read64(&mut index) as usize;
        let size = read32(&mut index) as usize;
        assert_eq!(offset, expected_offset);
        expected_offset += size;
        assert!(expected_offset <= index_offset);
        let mut block = checked(&data[offset..expected_offset]);
        let start = result.len();
        while !block.is_empty() {
            let flag = take(&mut block, 1)[0];
            let klen = read32(&mut block) as usize;
            let vlen = read32(&mut block) as usize;
            let key = take(&mut block, klen).to_vec();
            let value = take(&mut block, vlen).to_vec();
            let entry = match flag {
                0 => { assert!(value.is_empty()); (key, None) }
                1 => (key, Some(value)),
                _ => panic!("bad flag"),
            };
            result.push(entry);
        }
        assert_eq!(result[start].0.as_slice(), first);
    }
    assert!(index.is_empty());
    assert_eq!(expected_offset, index_offset);
    assert_eq!(result.len() as u64, entry_count);
    assert!(result.windows(2).all(|w| w[0].0 < w[1].0));
    (result, blocks)
}

#[test]
fn independent_parser_recovers_300_entries() {
    assert_eq!(checksum(b"123456789"), 0xcbf4_3926);
    let dir = Temp::new();
    let path = dir.0.join("table.sst");
    let mut model = BTreeMap::new();
    let mut state = 731u64;
    for i in 0..300u32 {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let mut key = (state >> 32).to_be_bytes().to_vec();
        key.extend_from_slice(&i.to_be_bytes());
        let value = match i % 7 {
            0 => None,
            1 => Some(Vec::new()),
            _ => Some(vec![state as u8; (state % 400) as usize]),
        };
        model.insert(key, value);
    }
    let entries: Vec<_> = model.into_iter().collect();
    let len = write_sstable(&path, &entries).unwrap();
    let raw = fs::read(&path).unwrap();
    assert_eq!(len, raw.len() as u64);
    let (actual, blocks) = parse(&raw);
    assert_eq!(actual, entries);
    assert!(blocks > 1);
    assert!(!dir.0.join("table.sst.tmp").exists());
}

#[test]
fn empty_and_oversized_entry_and_replacement() {
    let dir = Temp::new();
    let path = dir.0.join("table.sst");
    assert_eq!(write_sstable(&path, &[]).unwrap(), 44);
    assert_eq!(parse(&fs::read(&path).unwrap()), (vec![], 0));
    let entries = vec![(vec![], Some(vec![9; 12_000])), (vec![1], None)];
    write_sstable(&path, &entries).unwrap();
    assert_eq!(parse(&fs::read(&path).unwrap()), (entries, 2));
    assert!(!dir.0.join("table.sst.tmp").exists());
}

#[test]
fn rejects_disordered_or_duplicate_keys_without_touching_target() {
    let dir = Temp::new();
    let path = dir.0.join("table.sst");
    for entries in [
        vec![(vec![2], None), (vec![1], None)],
        vec![(vec![1], None), (vec![1], Some(vec![]))],
    ] {
        assert!(write_sstable(&path, &entries).is_err());
        assert!(!path.exists());
        assert!(!dir.0.join("table.sst.tmp").exists());
    }
    fs::write(&path, b"old").unwrap();
    assert!(write_sstable(&path, &[(vec![2], None), (vec![1], None)]).is_err());
    assert_eq!(fs::read(&path).unwrap(), b"old");
}

#[test]
fn does_not_take_over_existing_temporary_file() {
    let dir = Temp::new();
    let path = dir.0.join("table.sst");
    let tmp = dir.0.join("table.sst.tmp");
    fs::write(&tmp, b"foreign").unwrap();
    assert!(write_sstable(&path, &[]).is_err());
    assert_eq!(fs::read(&tmp).unwrap(), b"foreign");
    assert!(!path.exists());
}
