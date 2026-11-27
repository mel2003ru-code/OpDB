use opdb_core::lsm::memtable::Memtable;
use opdb_core::Op;
use std::collections::BTreeMap;

struct Lcg(u64);
impl Lcg {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        self.0 >> 33
    }
    fn key(&mut self) -> Vec<u8> {
        let n = self.next() % 12;
        vec![b'k', b'a' + (n % 6) as u8, (n / 6) as u8]
    }
    fn value(&mut self) -> Vec<u8> {
        let len = (self.next() % 6) as usize;
        (0..len).map(|_| (self.next() % 256) as u8).collect()
    }
}

fn model_bytes(model: &BTreeMap<Vec<u8>, Option<Vec<u8>>>) -> usize {
    model.iter().map(|(k, v)| k.len() + v.as_ref().map_or(0, |x| x.len()) + 16).sum()
}

fn check(m: &Memtable, model: &BTreeMap<Vec<u8>, Option<Vec<u8>>>) {
    assert_eq!(m.len(), model.len());
    assert_eq!(m.is_empty(), model.is_empty());
    let got: Vec<(Vec<u8>, Option<Vec<u8>>)> = m.iter().map(|(k, v)| (k.to_vec(), v.map(|x| x.to_vec()))).collect();
    let want: Vec<(Vec<u8>, Option<Vec<u8>>)> = model.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
    assert_eq!(got, want);
    for (k, v) in model {
        assert_eq!(m.get(k), Some(v.as_deref()));
    }
    assert_eq!(m.get(b"never-written"), None);
    assert_eq!(m.approx_bytes(), model_bytes(model));
}

#[test]
fn matches_a_btreemap_model_for_20_seeds() {
    for seed in 1..=20u64 {
        let mut rng = Lcg(seed);
        let mut m = Memtable::new();
        let mut model: BTreeMap<Vec<u8>, Option<Vec<u8>>> = BTreeMap::new();
        for _ in 0..300 {
            let key = rng.key();
            if rng.next() % 3 == 0 {
                m.delete(&key);
                model.insert(key, None);
            } else {
                let v = rng.value();
                m.put(&key, &v);
                model.insert(key, Some(v));
            }
            check(&m, &model);
        }
    }
}

#[test]
fn delete_of_an_unknown_key_creates_a_tombstone() {
    let mut m = Memtable::new();
    m.delete(b"x");
    assert_eq!(m.get(b"x"), Some(None));
    assert_eq!(m.len(), 1);
    assert_eq!(m.approx_bytes(), 1 + 16);
}

#[test]
fn approx_bytes_follows_the_formula_and_shrinks_on_a_shorter_overwrite() {
    let mut m = Memtable::new();
    m.put(b"ab", b"12345");
    assert_eq!(m.approx_bytes(), 2 + 5 + 16);
    m.put(b"ab", b"1");
    assert_eq!(m.approx_bytes(), 2 + 1 + 16);
    m.put(b"c", b"");
    assert_eq!(m.approx_bytes(), (2 + 1 + 16) + (1 + 16));
    m.delete(b"ab");
    assert_eq!(m.approx_bytes(), (2 + 16) + (1 + 16));
}

#[test]
fn apply_equals_the_same_operations_one_by_one() {
    let ops = vec![
        Op::Put(b"a".to_vec(), b"1".to_vec()),
        Op::Put(b"b".to_vec(), b"2".to_vec()),
        Op::Delete(b"a".to_vec()),
        Op::Put(b"a".to_vec(), b"3".to_vec()),
        Op::Delete(b"z".to_vec()),
    ];
    let mut batch = Memtable::new();
    batch.apply(&ops);
    let mut single = Memtable::new();
    for op in &ops {
        match op {
            Op::Put(k, v) => single.put(k, v),
            Op::Delete(k) => single.delete(k),
        }
    }
    let a: Vec<_> = batch.iter().collect();
    let b: Vec<_> = single.iter().collect();
    assert_eq!(a, b);
    assert_eq!(batch.approx_bytes(), single.approx_bytes());
    assert_eq!(batch.get(b"a"), Some(Some(&b"3"[..])));
    assert_eq!(batch.get(b"z"), Some(None));
}

#[test]
fn iteration_is_in_byte_order() {
    let mut m = Memtable::new();
    for k in [&b"b"[..], b"a", b"ab", b"", b"\xff", b"\x00"] {
        m.put(k, b"v");
    }
    let keys: Vec<Vec<u8>> = m.iter().map(|(k, _)| k.to_vec()).collect();
    let mut sorted = keys.clone();
    sorted.sort();
    assert_eq!(keys, sorted);
    assert_eq!(keys.len(), 6);
}
