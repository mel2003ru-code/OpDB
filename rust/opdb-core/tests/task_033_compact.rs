use opdb_core::{Error, Store};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-task033-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

#[test]
fn compacts_overwrites_and_deletes() {
    let original = tmp("original");
    let compacted = tmp("compacted");
    let mut model: BTreeMap<Vec<u8>, Vec<u8>> = BTreeMap::new();
    let mut s = Store::create(&original).unwrap();
    for i in 0..20u8 {
        let key = vec![b'k', i];
        for round in 0..50u8 {
            let value = vec![i, round];
            s.put(&key, &value).unwrap();
            model.insert(key.clone(), value);
        }
    }
    for i in 0..10u8 {
        let key = vec![b'k', i];
        s.delete(&key).unwrap();
        model.remove(&key);
    }
    let original_len = fs::metadata(&original).unwrap().len();
    s.compact_to(&compacted).unwrap();
    s.close().unwrap();

    assert!(fs::metadata(&compacted).unwrap().len() < original_len);
    let c = Store::open(&compacted).unwrap();
    assert_eq!(c.truncated_tail(), None);
    assert_eq!(c.len(), model.len());
    for (key, value) in &model {
        assert_eq!(c.get(key), Some(&value[..]), "key {key:?}");
    }
    for i in 0..10u8 {
        assert_eq!(c.get(&vec![b'k', i]), None, "deleted key {i}");
    }

    let mut reopened_original = Store::open(&original).unwrap();
    assert_eq!(fs::metadata(&original).unwrap().len(), original_len);
    assert_eq!(reopened_original.len(), model.len());
    for (key, value) in &model {
        assert_eq!(reopened_original.get(key), Some(&value[..]), "key {key:?}");
    }
    let fresh_value = vec![9u8];
    reopened_original.put(b"fresh", &fresh_value).unwrap();
    assert_eq!(reopened_original.get(b"fresh"), Some(&fresh_value[..]));
    drop(reopened_original);
    drop(c);
    fs::remove_file(original).unwrap();
    fs::remove_file(compacted).unwrap();
}

#[test]
fn original_unchanged_after_compact() {
    let original = tmp("unchanged");
    let compacted = tmp("unchanged_copy");
    let mut s = Store::create(&original).unwrap();
    s.put(b"a", b"1").unwrap();
    s.put(b"b", b"2").unwrap();
    s.put(b"a", b"3").unwrap();
    s.delete(b"b").unwrap();
    let before = fs::metadata(&original).unwrap().len();
    let before_get = s.get(b"a").map(|v| v.to_vec());
    s.compact_to(&compacted).unwrap();
    assert_eq!(fs::metadata(&original).unwrap().len(), before);
    assert_eq!(s.get(b"a"), before_get.as_deref());
    assert_eq!(s.len(), 1);
    s.put(b"c", b"4").unwrap();
    assert_eq!(s.get(b"c"), Some(&b"4"[..]));
    s.close().unwrap();
    fs::remove_file(original).unwrap();
    fs::remove_file(compacted).unwrap();
}

#[test]
fn compact_to_existing_path_fails() {
    let original = tmp("exists_orig");
    let existing = tmp("exists_target");
    let mut s = Store::create(&original).unwrap();
    s.put(b"x", b"y").unwrap();
    s.close().unwrap();
    let mut preexisting = Store::create(&existing).unwrap();
    preexisting.put(b"sentinel", b"value").unwrap();
    preexisting.close().unwrap();
    let before = fs::read(&existing).unwrap();
    let mut s = Store::open(&original).unwrap();
    let result = s.compact_to(&existing);
    assert!(matches!(result, Err(Error::Io(_))));
    assert_eq!(fs::read(&existing).unwrap(), before);
    fs::remove_file(original).unwrap();
    fs::remove_file(existing).unwrap();
}

#[test]
fn empty_store_compacts_to_twelve_bytes() {
    let original = tmp("empty_orig");
    let compacted = tmp("empty_copy");
    let mut s = Store::create(&original).unwrap();
    s.compact_to(&compacted).unwrap();
    s.close().unwrap();
    assert_eq!(fs::metadata(&compacted).unwrap().len(), 12);
    let c = Store::open(&compacted).unwrap();
    assert_eq!(c.len(), 0);
    assert!(c.is_empty());
    assert_eq!(c.get(b"anything"), None);
    drop(s);
    drop(c);
    fs::remove_file(original).unwrap();
    fs::remove_file(compacted).unwrap();
}

#[test]
fn all_deleted_compacts_to_twelve_bytes() {
    let original = tmp("all_del_orig");
    let compacted = tmp("all_del_copy");
    let mut s = Store::create(&original).unwrap();
    s.put(b"a", b"1").unwrap();
    s.put(b"b", b"2").unwrap();
    s.delete(b"a").unwrap();
    s.delete(b"b").unwrap();
    s.compact_to(&compacted).unwrap();
    s.close().unwrap();
    assert_eq!(fs::metadata(&compacted).unwrap().len(), 12);
    let c = Store::open(&compacted).unwrap();
    assert_eq!(c.len(), 0);
    drop(s);
    drop(c);
    fs::remove_file(original).unwrap();
    fs::remove_file(compacted).unwrap();
}
