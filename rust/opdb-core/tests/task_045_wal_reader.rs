use opdb_core::lsm::wal::{read_wal, repair_wal, WalWriter, WAL_HEADER_LEN};
use opdb_core::lsm::SyncPolicy;
use opdb_core::{Error, Op};
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

struct Lcg(u64);
impl Lcg {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        self.0 >> 33
    }
    fn bytes(&mut self, max: u64) -> Vec<u8> {
        let n = self.next() % (max + 1);
        (0..n).map(|_| (self.next() % 256) as u8).collect()
    }
    fn batch(&mut self) -> Vec<Op> {
        (0..self.next() % 5)
            .map(|_| {
                if self.next() % 4 == 0 {
                    Op::Delete(self.bytes(6))
                } else {
                    Op::Put(self.bytes(6), self.bytes(20))
                }
            })
            .collect()
    }
}

fn write_log(path: &PathBuf, batches: &[Vec<Op>]) -> Vec<u64> {
    let mut w = WalWriter::create(path, SyncPolicy::Never).unwrap();
    let mut ends = vec![w.bytes_written()];
    for b in batches {
        w.append_batch(b).unwrap();
        ends.push(w.bytes_written());
    }
    w.close().unwrap();
    ends
}

#[test]
fn round_trip_of_random_batches() {
    let p = tmp("t045-round");
    let mut rng = Lcg(11);
    let batches: Vec<Vec<Op>> = (0..50).map(|_| rng.batch()).collect();
    let ends = write_log(&p, &batches);
    let r = read_wal(&p).unwrap();
    assert_eq!(r.batches, batches);
    assert_eq!(r.valid_end, *ends.last().unwrap());
    assert_eq!(r.torn_tail, None);
    fs::remove_file(&p).unwrap();
}

#[test]
fn empty_log_has_valid_end_12() {
    let p = tmp("t045-empty");
    write_log(&p, &[]);
    let r = read_wal(&p).unwrap();
    assert_eq!((r.batches.len(), r.valid_end, r.torn_tail), (0, WAL_HEADER_LEN, None));
    fs::remove_file(&p).unwrap();
}

#[test]
fn every_cut_of_the_last_record_is_a_torn_tail_and_repair_makes_the_log_writable() {
    let mut rng = Lcg(5);
    let batches: Vec<Vec<Op>> = (0..4).map(|_| rng.batch()).chain(std::iter::once(vec![Op::Put(b"last".to_vec(), vec![7; 30])])).collect();
    let src = tmp("t045-cut-src");
    let ends = write_log(&src, &batches);
    let full = fs::read(&src).unwrap();
    let start_of_last = ends[ends.len() - 2];
    for cut in (start_of_last + 1)..*ends.last().unwrap() {
        let p = tmp(&format!("t045-cut-{cut}"));
        fs::write(&p, &full[..cut as usize]).unwrap();
        let r = read_wal(&p).unwrap();
        assert_eq!(r.torn_tail, Some(start_of_last), "cut {cut}");
        assert_eq!(r.valid_end, start_of_last);
        assert_eq!(r.batches, batches[..batches.len() - 1].to_vec());
        assert!(matches!(WalWriter::open_append(&p, SyncPolicy::Never), Err(Error::TailNotRepaired)));
        repair_wal(&p).unwrap();
        assert_eq!(fs::read(&p).unwrap(), full[..start_of_last as usize].to_vec());
        let mut w = WalWriter::open_append(&p, SyncPolicy::Never).unwrap();
        w.append_batch(&batches[batches.len() - 1]).unwrap();
        w.close().unwrap();
        assert_eq!(fs::read(&p).unwrap(), full, "cut {cut}");
        fs::remove_file(&p).unwrap();
    }
    fs::remove_file(&src).unwrap();
}

#[test]
fn flipping_any_single_byte_is_never_a_silently_different_answer() {
    let src = tmp("t045-flip-src");
    let batches = vec![
        vec![Op::Put(b"alpha".to_vec(), b"one".to_vec())],
        vec![Op::Delete(b"beta".to_vec()), Op::Put(b"gamma".to_vec(), vec![9; 12])],
        vec![Op::Put(b"delta".to_vec(), Vec::new())],
    ];
    write_log(&src, &batches);
    let good = fs::read(&src).unwrap();
    for i in 0..good.len() {
        let mut bad = good.clone();
        bad[i] ^= 0xFF;
        let p = tmp(&format!("t045-flip-{i}"));
        fs::write(&p, &bad).unwrap();
        match read_wal(&p) {
            Err(Error::Corrupt { .. }) | Err(Error::BadMagic) | Err(Error::UnsupportedVersion(_)) => {}
            Ok(r) => {
                assert!(r.torn_tail.is_some(), "byte {i}: silently accepted");
                assert!(batches.starts_with(&r.batches), "byte {i}: returned a non-prefix");
            }
            Err(e) => panic!("byte {i}: unexpected error {:?}", e),
        }
        fs::remove_file(&p).unwrap();
    }
    fs::remove_file(&src).unwrap();
}

#[test]
fn repair_never_touches_a_damaged_log() {
    let p = tmp("t045-repair-damaged");
    write_log(&p, &[vec![Op::Put(b"k".to_vec(), b"v".to_vec())], vec![Op::Put(b"k2".to_vec(), b"v2".to_vec())]]);
    let mut bytes = fs::read(&p).unwrap();
    let flip = WAL_HEADER_LEN as usize + 12;
    bytes[flip] ^= 0xFF;
    fs::write(&p, &bytes).unwrap();
    assert!(matches!(repair_wal(&p), Err(Error::Corrupt { offset }) if offset == WAL_HEADER_LEN));
    assert_eq!(fs::read(&p).unwrap(), bytes);
    fs::remove_file(&p).unwrap();
}

#[test]
fn header_errors_are_explicit() {
    let p = tmp("t045-header");
    fs::write(&p, b"NOTAWAL\0\0\0\0\0").unwrap();
    assert!(matches!(read_wal(&p), Err(Error::BadMagic)));
    let mut h = b"OPDBWAL\0".to_vec();
    h.extend_from_slice(&7u32.to_le_bytes());
    fs::write(&p, &h).unwrap();
    assert!(matches!(read_wal(&p), Err(Error::UnsupportedVersion(7))));
    fs::remove_file(&p).unwrap();
}
