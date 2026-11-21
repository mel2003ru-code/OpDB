use opdb_core::{Error, Store, MAGIC};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545F4914F6CDD1D)
    }
    fn bytes(&mut self, max: usize) -> Vec<u8> {
        let n = (self.next() as usize) % (max + 1);
        (0..n).map(|_| self.next() as u8).collect()
    }
}

#[test]
fn binary_empty_and_large() {
    let p = tmp("binary");
    let mut s = Store::create(&p).unwrap();
    let all: Vec<u8> = (0..=255u8).collect();
    let big = vec![0xABu8; 1 << 20];
    s.put(&all, &[0, 0, 0]).unwrap();
    s.put(b"", b"empty-key").unwrap();
    s.put(b"empty-value", b"").unwrap();
    s.put(b"big", &big).unwrap();
    s.close().unwrap();
    let s = Store::open(&p).unwrap();
    assert_eq!(s.get(&all), Some(&[0u8, 0, 0][..]));
    assert_eq!(s.get(b""), Some(&b"empty-key"[..]));
    assert_eq!(s.get(b"empty-value"), Some(&b""[..]));
    assert_eq!(s.get(b"big"), Some(&big[..]));
    assert_eq!(s.len(), 4);
    fs::remove_file(p).unwrap();
}

#[test]
fn overwrite_delete_missing_and_reopen() {
    let p = tmp("over");
    let mut s = Store::create(&p).unwrap();
    s.put(b"k", b"1").unwrap();
    s.put(b"k", b"2").unwrap();
    assert!(!s.delete(b"missing").unwrap());
    s.put(b"gone", b"x").unwrap();
    assert!(s.delete(b"gone").unwrap());
    s.close().unwrap();
    assert!(matches!(s.put(b"a", b"b"), Err(Error::Closed)));
    let s = Store::open(&p).unwrap();
    assert_eq!(s.get(b"k"), Some(&b"2"[..]));
    assert_eq!(s.get(b"gone"), None);
    assert_eq!(s.len(), 1);
    assert!(Store::create(&p).is_err(), "create must not clobber an existing file");
    fs::remove_file(p).unwrap();
}

#[test]
fn random_ops_match_hashmap_model() {
    for seed in 1..=20u64 {
        let p = tmp(&format!("rand{}", seed));
        let mut rng = Rng(seed.wrapping_mul(0x9E3779B97F4A7C15) | 1);
        let mut s = Store::create(&p).unwrap();
        let mut model: HashMap<Vec<u8>, Vec<u8>> = HashMap::new();
        let mut keys: Vec<Vec<u8>> = Vec::new();
        for i in 0..10_000 {
            let key = if !keys.is_empty() && rng.next() % 3 != 0 {
                keys[(rng.next() as usize) % keys.len()].clone()
            } else {
                let k = rng.bytes(8);
                keys.push(k.clone());
                k
            };
            match rng.next() % 4 {
                0 => {
                    let expect = model.remove(&key).is_some();
                    assert_eq!(s.delete(&key).unwrap(), expect, "seed {} op {}", seed, i);
                }
                _ => {
                    let v = rng.bytes(40);
                    s.put(&key, &v).unwrap();
                    model.insert(key, v);
                }
            }
            if rng.next() % 500 == 0 {
                s.close().unwrap();
                s = Store::open(&p).unwrap();
                assert!(s.truncated_tail().is_none());
                assert_eq!(s.len(), model.len(), "seed {} op {}", seed, i);
                for (k, v) in &model {
                    assert_eq!(s.get(k), Some(&v[..]), "seed {} op {}", seed, i);
                }
                for k in &keys {
                    assert_eq!(s.get(k).is_some(), model.contains_key(k));
                }
            }
        }
        fs::remove_file(p).unwrap();
    }
}

fn two_record_file(name: &str) -> (PathBuf, Vec<u8>) {
    let p = tmp(name);
    let mut s = Store::create(&p).unwrap();
    s.put(b"first", b"one").unwrap();
    s.put(b"second", b"two").unwrap();
    s.close().unwrap();
    let bytes = fs::read(&p).unwrap();
    (p, bytes)
}

#[test]
fn damaged_files() {
    // wrong magic
    let (p, mut b) = two_record_file("magic");
    b[0] ^= 0xFF;
    fs::write(&p, &b).unwrap();
    assert!(matches!(Store::open(&p), Err(Error::BadMagic)));
    // too short to hold a header
    fs::write(&p, &MAGIC[..5]).unwrap();
    assert!(matches!(Store::open(&p), Err(Error::BadMagic)));
    // unknown version
    let (_, mut b) = two_record_file("magic");
    b[8] = 99;
    fs::write(&p, &b).unwrap();
    assert!(matches!(Store::open(&p), Err(Error::UnsupportedVersion(99))));
    // flipped byte in every position of the first record: never wrong data
    let (_, good) = two_record_file("magic");
    let first_end = 12 + 13 + 5 + 3;
    for i in 12..first_end {
        let mut b = good.clone();
        b[i] ^= 0x40;
        fs::write(&p, &b).unwrap();
        match Store::open(&p) {
            Err(Error::Corrupt { .. }) => {}
            Ok(s) => {
                assert!(s.truncated_tail().is_some(), "flip at {} accepted silently", i);
                assert_eq!(s.get(b"first"), None);
                assert_eq!(s.get(b"second"), None);
            }
            Err(e) => panic!("flip at {}: unexpected {:?}", i, e),
        }
    }
    // flipped byte inside the value of the last record
    let mut b = good.clone();
    let n = b.len();
    b[n - 6] ^= 1;
    fs::write(&p, &b).unwrap();
    assert!(matches!(Store::open(&p), Err(Error::Corrupt { .. })));
    // cut at every length inside the second record
    for cut in first_end..good.len() {
        fs::write(&p, &good[..cut]).unwrap();
        let mut s = Store::open(&p).unwrap();
        assert_eq!(s.get(b"first"), Some(&b"one"[..]));
        assert_eq!(s.get(b"second"), None);
        if cut == first_end {
            assert!(s.truncated_tail().is_none());
        } else {
            assert_eq!(s.truncated_tail(), Some(first_end as u64));
            assert!(matches!(s.put(b"x", b"y"), Err(Error::TailNotRepaired)));
            s.repair().unwrap();
            s.put(b"x", b"y").unwrap();
            s.close().unwrap();
            let s = Store::open(&p).unwrap();
            assert!(s.truncated_tail().is_none());
            assert_eq!(s.get(b"x"), Some(&b"y"[..]));
            assert_eq!(s.get(b"first"), Some(&b"one"[..]));
        }
    }
    fs::remove_file(p).unwrap();
}
