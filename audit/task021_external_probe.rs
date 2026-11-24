use opdb_core::Store;
use std::collections::HashMap;
use std::fs;

#[test]
fn audit_mixed_updates_reopen_and_exclusive_handle() {
    let path = std::env::temp_dir().join(format!("opdb-audit-{}", std::process::id()));
    let mut store = Store::create(&path).unwrap();
    let mut model = HashMap::<Vec<u8>, Vec<u8>>::new();
    let mut x = 0x645a_9612_01bcu64;
    for i in 0..4096u32 {
        x = x.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        let key = ((x >> 24) as u16 % 313).to_le_bytes().to_vec();
        if x & 3 == 0 {
            assert_eq!(store.delete(&key).unwrap(), model.remove(&key).is_some());
        } else {
            let value = [i.to_le_bytes().as_slice(), &x.to_le_bytes()].concat();
            store.put(&key, &value).unwrap();
            model.insert(key, value);
        }
        if i % 257 == 0 {
            assert!(Store::open(&path).is_err());
            store.close().unwrap();
            store = Store::open(&path).unwrap();
            assert_eq!(store.len(), model.len());
            for (k, v) in &model { assert_eq!(store.get(k), Some(v.as_slice())); }
        }
    }
    store.close().unwrap();
    let check = Store::open(&path).unwrap();
    assert_eq!(check.len(), model.len());
    for (k, v) in &model { assert_eq!(check.get(k), Some(v.as_slice())); }
    drop(check);
    fs::remove_file(path).unwrap();
}
