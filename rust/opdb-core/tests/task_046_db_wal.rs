use opdb_core::lsm::db::Db;
use opdb_core::lsm::SyncPolicy;
use opdb_core::{Error, Op};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

fn dir(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_dir_all(&p);
    p
}

struct Lcg(u64);
impl Lcg {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        self.0 >> 33
    }
    fn key(&mut self) -> Vec<u8> {
        vec![b'k', b'a' + (self.next() % 8) as u8, (self.next() % 3) as u8]
    }
    fn batch(&mut self) -> Vec<Op> {
        (0..1 + self.next() % 4)
            .map(|_| {
                if self.next() % 3 == 0 {
                    Op::Delete(self.key())
                } else {
                    Op::Put(self.key(), (0..self.next() % 5).map(|_| (self.next() % 256) as u8).collect())
                }
            })
            .collect()
    }
}

type Model = BTreeMap<Vec<u8>, Vec<u8>>;

fn apply(model: &mut Model, ops: &[Op]) {
    for op in ops {
        match op {
            Op::Put(k, v) => {
                model.insert(k.clone(), v.clone());
            }
            Op::Delete(k) => {
                model.remove(k);
            }
        }
    }
}

fn check(db: &Db, model: &Model) {
    assert_eq!(db.scan(b""), model.iter().map(|(k, v)| (k.clone(), v.clone())).collect::<Vec<_>>());
    for (k, v) in model {
        assert_eq!(db.get(k).as_deref(), Some(v.as_slice()));
    }
    assert_eq!(db.get(b"never-written"), None);
    for first in b'a'..=b'h' {
        let prefix = [b'k', first];
        let want: Vec<_> = model.iter().filter(|(k, _)| k.starts_with(&prefix)).map(|(k, v)| (k.clone(), v.clone())).collect();
        assert_eq!(db.scan(&prefix), want);
    }
}

#[test]
fn matches_a_model_across_reopens_for_20_seeds() {
    for seed in 1..=20u64 {
        let d = dir(&format!("t046-model-{seed}"));
        let mut rng = Lcg(seed);
        let mut model = Model::new();
        let mut db = Db::open(&d, SyncPolicy::Never).unwrap();
        for step in 0..120 {
            let batch = rng.batch();
            db.write_batch(&batch).unwrap();
            apply(&mut model, &batch);
            check(&db, &model);
            if rng.next() % 15 == 0 || step == 119 {
                db.close().unwrap();
                db = Db::open(&d, SyncPolicy::Never).unwrap();
                assert_eq!(db.torn_tail(), None);
                check(&db, &model);
            }
        }
        db.close().unwrap();
        fs::remove_dir_all(&d).unwrap();
    }
}

#[test]
fn torn_wal_tail_blocks_writes_until_repair_and_keeps_the_intact_prefix() {
    let wal_name = "wal-00000001.log";
    let d0 = dir("t046-torn-src");
    let mut rng = Lcg(77);
    let batches: Vec<Vec<Op>> = (0..6).map(|_| rng.batch()).collect();
    let mut db = Db::open(&d0, SyncPolicy::EveryBatch).unwrap();
    let mut sizes = vec![fs::metadata(d0.join(wal_name)).unwrap().len()];
    for b in &batches {
        db.write_batch(b).unwrap();
        sizes.push(fs::metadata(d0.join(wal_name)).unwrap().len());
    }
    db.close().unwrap();
    let full = fs::read(d0.join(wal_name)).unwrap();
    let last_start = sizes[sizes.len() - 2];
    let mut before_last = Model::new();
    for b in &batches[..batches.len() - 1] {
        apply(&mut before_last, b);
    }
    let mut all = before_last.clone();
    apply(&mut all, &batches[batches.len() - 1]);
    for cut in [last_start + 1, last_start + 5, last_start + 9, sizes[sizes.len() - 1] - 1] {
        let d = dir(&format!("t046-torn-{cut}"));
        fs::create_dir_all(&d).unwrap();
        fs::write(d.join(wal_name), &full[..cut as usize]).unwrap();
        let mut db = Db::open(&d, SyncPolicy::EveryBatch).unwrap();
        assert_eq!(db.torn_tail(), Some(last_start), "cut {cut}");
        check(&db, &before_last);
        assert!(matches!(db.write_batch(&[Op::Put(b"x".to_vec(), b"1".to_vec())]), Err(Error::TailNotRepaired)));
        db.repair().unwrap();
        assert_eq!(db.torn_tail(), None);
        check(&db, &before_last);
        let extra = vec![Op::Put(b"x".to_vec(), b"1".to_vec())];
        db.write_batch(&extra).unwrap();
        let mut expect = before_last.clone();
        apply(&mut expect, &extra);
        check(&db, &expect);
        db.close().unwrap();
        let db = Db::open(&d, SyncPolicy::EveryBatch).unwrap();
        assert_eq!(db.torn_tail(), None);
        check(&db, &expect);
        drop(db);
        fs::remove_dir_all(&d).unwrap();
    }
    let db = Db::open(&d0, SyncPolicy::Never).unwrap();
    check(&db, &all);
    drop(db);
    fs::remove_dir_all(&d0).unwrap();
}

#[test]
fn a_directory_path_that_is_a_file_is_an_io_error() {
    let p = dir("t046-file");
    fs::write(&p, b"x").unwrap();
    assert!(matches!(Db::open(&p, SyncPolicy::Never), Err(Error::Io(_))));
    fs::remove_file(&p).unwrap();
}

#[test]
fn a_crash_before_the_wal_header_was_written_is_recovered() {
    let d = dir("t046-empty-wal");
    fs::create_dir_all(&d).unwrap();
    fs::write(d.join("wal-00000001.log"), b"OPDB").unwrap();
    let mut db = Db::open(&d, SyncPolicy::Never).unwrap();
    assert_eq!(db.scan(b""), vec![]);
    db.put(b"a", b"1").unwrap();
    db.close().unwrap();
    let db = Db::open(&d, SyncPolicy::Never).unwrap();
    assert_eq!(db.get(b"a"), Some(b"1".to_vec()));
    drop(db);
    fs::remove_dir_all(&d).unwrap();
}

#[test]
fn a_damaged_wal_is_an_error_not_a_silent_loss() {
    let d = dir("t046-damaged");
    let mut db = Db::open(&d, SyncPolicy::Never).unwrap();
    db.put(b"a", b"1").unwrap();
    db.put(b"b", b"2").unwrap();
    db.close().unwrap();
    let p = d.join("wal-00000001.log");
    let mut bytes = fs::read(&p).unwrap();
    bytes[22] ^= 0xFF; // inside the first record payload: a complete record with a wrong checksum
    fs::write(&p, &bytes).unwrap();
    assert!(matches!(Db::open(&d, SyncPolicy::Never), Err(Error::Corrupt { .. })));
    fs::remove_dir_all(&d).unwrap();
}
