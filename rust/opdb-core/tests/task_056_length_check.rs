use opdb_core::{check_field_len, encode_ops, try_encode_ops, Error, Op, Store, MAX_FIELD_LEN};
use std::fs;
use std::path::PathBuf;

fn tmp(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("opdb-core-test-{}-{}", std::process::id(), name));
    let _ = fs::remove_file(&p);
    p
}

#[test]
fn limit_is_u32_max() {
    assert_eq!(MAX_FIELD_LEN, u32::MAX as usize);
    assert!(check_field_len(0).is_ok());
    assert!(check_field_len(1).is_ok());
    assert!(check_field_len(MAX_FIELD_LEN).is_ok());
}

#[cfg(target_pointer_width = "64")]
#[test]
fn one_over_the_limit_is_rejected() {
    for extra in [1usize, 2, 1 << 20] {
        match check_field_len(MAX_FIELD_LEN + extra) {
            Err(Error::TooLarge { len }) => assert_eq!(len, MAX_FIELD_LEN + extra),
            other => panic!("expected TooLarge, got {:?}", other),
        }
    }
}

#[test]
fn try_encode_ops_equals_encode_ops() {
    let ops = vec![
        Op::Put(b"a".to_vec(), b"1".to_vec()),
        Op::Put(Vec::new(), Vec::new()),
        Op::Put(b"k".to_vec(), Vec::new()),
        Op::Delete(b"a".to_vec()),
        Op::Delete(Vec::new()),
        Op::Put(vec![0xff; 300], vec![0x00; 70_000]),
    ];
    assert_eq!(try_encode_ops(&ops).unwrap(), encode_ops(&ops));
    assert_eq!(try_encode_ops(&[]).unwrap(), Vec::<u8>::new());
}

#[test]
fn normal_writes_still_work_and_change_the_file_as_before() {
    let p = tmp("task056-normal");
    let mut s = Store::create(&p).unwrap();
    s.put(b"a", b"1").unwrap();
    s.put(b"b", b"").unwrap();
    assert!(s.delete(b"a").unwrap());
    assert_eq!(s.len(), 1);
    assert_eq!(s.get(b"b"), Some(&b""[..]));
    s.close().unwrap();
    // 12 header + 3 records of 13 + key + value bytes each (put a, put b, delete a)
    let expect = 12 + (13 + 1 + 1) + (13 + 1) + 13 + 1;
    assert_eq!(fs::metadata(&p).unwrap().len(), expect as u64);
    let s = Store::open(&p).unwrap();
    assert_eq!(s.len(), 1);
    drop(s);
    fs::remove_file(&p).unwrap();
}

#[test]
fn error_variant_is_debuggable() {
    let e = Error::TooLarge { len: 7 };
    assert!(format!("{:?}", e).contains("TooLarge"));
}
