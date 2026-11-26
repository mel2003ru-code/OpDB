use opdb_core::Store;
use std::collections::BTreeMap;
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

fn expected_sorted(model: &BTreeMap<Vec<u8>, Vec<u8>>) -> Vec<(Vec<u8>, Vec<u8>)> {
    model.iter().map(|(k, v)| (k.clone(), v.clone())).collect()
}

#[test]
fn empty_store_gives_empty_entries() {
    let p = tmp("task031_empty");
    let mut s = Store::create(&p).unwrap();
    assert_eq!(s.entries(), Vec::new());
    s.close().unwrap();
    fs::remove_file(p).unwrap();
}

#[test]
fn random_ops_match_model_every_step() {
    for seed in 1..=20u64 {
        let p = tmp(&format!("task031_rand{}", seed));
        let mut rng = Rng(seed.wrapping_mul(0x9E3779B97F4A7C15) | 1);
        let mut s = Store::create(&p).unwrap();
        let mut model: BTreeMap<Vec<u8>, Vec<u8>> = BTreeMap::new();
        assert_eq!(s.entries(), expected_sorted(&model));
        for i in 0..300 {
            let key = rng.bytes(3);
            match rng.next() % 2 {
                0 => {
                    let value = rng.bytes(10);
                    model.insert(key.clone(), value.clone());
                    s.put(&key, &value).unwrap();
                }
                _ => {
                    model.remove(&key);
                    s.delete(&key).unwrap();
                }
            }
            assert_eq!(s.entries(), expected_sorted(&model), "seed {} op {}", seed, i);
        }
        s.close().unwrap();
        let reopened = Store::open(&p).unwrap();
        assert_eq!(reopened.entries(), expected_sorted(&model));
        let entries = reopened.entries();
        for pair in entries.windows(2) {
            assert!(pair[0].0 < pair[1].0, "entries not strictly increasing by key");
        }
        drop(reopened);
        fs::remove_file(p).unwrap();
    }
}
