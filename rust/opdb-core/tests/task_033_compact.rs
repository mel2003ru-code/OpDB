use opdb_core::{Error, Store};
use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

#[test]
fn compact_keeps_exactly_the_live_data_and_is_smaller() {
    let src = tmp("t033-src");
    let dst = tmp("t033-dst");
    let mut s = Store::create(&src).unwrap();
    let mut model: BTreeMap<Vec<u8>, Vec<u8>> = BTreeMap::new();
    for round in 0..50u32 {
        for k in 0..20u32 {
            let key = format!("key{k:02}").into_bytes();
            let val = format!("value-{round}-{k}").into_bytes();
            s.put(&key, &val).unwrap();
            model.insert(key, val);
        }
    }
    for k in 0..10u32 {
        let key = format!("key{k:02}").into_bytes();
        assert!(s.delete(&key).unwrap());
        model.remove(&key);
    }
    let before = fs::metadata(&src).unwrap().len();
    s.compact_to(&dst).unwrap();
    assert_eq!(fs::metadata(&src).unwrap().len(), before);
    let new_len = fs::metadata(&dst).unwrap().len();
    assert!(new_len < before, "{new_len} !< {before}");
    let c = Store::open(&dst).unwrap();
    assert_eq!(c.truncated_tail(), None);
    assert_eq!(c.len(), model.len());
    for (k, v) in &model {
        assert_eq!(c.get(k), Some(v.as_slice()));
    }
    assert_eq!(c.get(b"key00"), None);
    drop(c);
    // the original is unchanged and still writable
    assert_eq!(s.len(), model.len());
    s.put(b"after", b"1").unwrap();
    assert_eq!(s.get(b"after"), Some(&b"1"[..]));
    s.close().unwrap();
    fs::remove_file(&src).unwrap();
    fs::remove_file(&dst).unwrap();
}

#[test]
fn existing_target_is_an_error_and_is_left_alone() {
    let src = tmp("t033-exist-src");
    let dst = tmp("t033-exist-dst");
    fs::write(&dst, b"precious").unwrap();
    let mut s = Store::create(&src).unwrap();
    s.put(b"a", b"1").unwrap();
    match s.compact_to(&dst) {
        Err(Error::Io(_)) => {}
        other => panic!("expected Io error, got {:?}", other),
    }
    assert_eq!(fs::read(&dst).unwrap(), b"precious");
    s.close().unwrap();
    fs::remove_file(&src).unwrap();
    fs::remove_file(&dst).unwrap();
}

#[test]
fn empty_or_fully_deleted_store_compacts_to_header_only() {
    for (name, delete_all) in [("empty", false), ("deleted", true)] {
        let src = tmp(&format!("t033-{name}-src"));
        let dst = tmp(&format!("t033-{name}-dst"));
        let mut s = Store::create(&src).unwrap();
        if delete_all {
            s.put(b"x", b"1").unwrap();
            s.put(b"y", b"2").unwrap();
            s.delete(b"x").unwrap();
            s.delete(b"y").unwrap();
        }
        s.compact_to(&dst).unwrap();
        assert_eq!(fs::metadata(&dst).unwrap().len(), 12);
        let c = Store::open(&dst).unwrap();
        assert_eq!(c.len(), 0);
        drop(c);
        s.close().unwrap();
        fs::remove_file(&src).unwrap();
        fs::remove_file(&dst).unwrap();
    }
}
