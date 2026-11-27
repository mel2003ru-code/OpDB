use opdb_core::lsm::wal::{WalWriter, WAL_HEADER_LEN, WAL_MAGIC};
use opdb_core::lsm::SyncPolicy;
use opdb_core::{encode_ops, Error, Op};
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

// An independent CRC-32 (IEEE) written for this test, not taken from the code under test.
fn crc32(data: &[u8]) -> u32 {
    let mut table = [0u32; 256];
    for i in 0..256u32 {
        let mut c = i;
        for _ in 0..8 {
            c = if c & 1 == 1 { 0xEDB8_8320 ^ (c >> 1) } else { c >> 1 };
        }
        table[i as usize] = c;
    }
    let mut crc = 0xFFFF_FFFFu32;
    for &b in data {
        crc = table[((crc ^ b as u32) & 0xFF) as usize] ^ (crc >> 8);
    }
    !crc
}

fn expected_record(payload: &[u8]) -> Vec<u8> {
    let mut rec = vec![3u8];
    rec.extend_from_slice(&0u32.to_le_bytes());
    rec.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    rec.extend_from_slice(payload);
    let crc = crc32(&rec);
    rec.extend_from_slice(&crc.to_le_bytes());
    rec
}

fn batches() -> Vec<Vec<Op>> {
    vec![
        vec![Op::Put(b"a".to_vec(), b"1".to_vec()), Op::Delete(b"b".to_vec())],
        vec![Op::Put(b"key".to_vec(), Vec::new())],
        Vec::new(),
    ]
}

#[test]
fn file_bytes_are_exactly_the_documented_layout() {
    let p = tmp("t044-bytes");
    let mut w = WalWriter::create(&p, SyncPolicy::EveryBatch).unwrap();
    let mut expected = WAL_MAGIC.to_vec();
    expected.extend_from_slice(&0u32.to_le_bytes());
    assert_eq!(expected.len() as u64, WAL_HEADER_LEN);
    for b in batches() {
        w.append_batch(&b).unwrap();
        expected.extend_from_slice(&expected_record(&encode_ops(&b)));
        assert_eq!(w.bytes_written(), expected.len() as u64);
    }
    w.close().unwrap();
    assert_eq!(fs::read(&p).unwrap(), expected);
    assert_eq!(fs::metadata(&p).unwrap().len(), w.bytes_written());
    fs::remove_file(&p).unwrap();
}

#[test]
fn all_policies_write_identical_bytes() {
    let mut files = Vec::new();
    for (i, policy) in [SyncPolicy::EveryBatch, SyncPolicy::OnClose, SyncPolicy::Never].into_iter().enumerate() {
        let p = tmp(&format!("t044-policy{i}"));
        let mut w = WalWriter::create(&p, policy).unwrap();
        for b in batches() {
            w.append_batch(&b).unwrap();
        }
        w.close().unwrap();
        files.push(fs::read(&p).unwrap());
        fs::remove_file(&p).unwrap();
    }
    assert_eq!(files[0], files[1]);
    assert_eq!(files[1], files[2]);
}

#[test]
fn create_on_an_existing_path_fails_and_leaves_it_alone() {
    let p = tmp("t044-exists");
    fs::write(&p, b"precious").unwrap();
    match WalWriter::create(&p, SyncPolicy::Never) {
        Err(Error::Io(_)) => {}
        other => panic!("expected Io error, got {:?}", other.map(|_| ())),
    }
    assert_eq!(fs::read(&p).unwrap(), b"precious");
    fs::remove_file(&p).unwrap();
}

#[test]
fn append_after_close_is_closed_and_close_is_repeatable() {
    let p = tmp("t044-closed");
    let mut w = WalWriter::create(&p, SyncPolicy::OnClose).unwrap();
    w.append_batch(&batches()[0]).unwrap();
    w.close().unwrap();
    w.close().unwrap();
    assert!(matches!(w.append_batch(&batches()[0]), Err(Error::Closed)));
    fs::remove_file(&p).unwrap();
}
