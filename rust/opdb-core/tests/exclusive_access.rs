use opdb_core::{Error, Store};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn path(name: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    path.push(format!("opdb-exclusive-{}-{name}", std::process::id()));
    let _ = fs::remove_file(&path);
    path
}

#[test]
fn second_handle_is_busy_and_replay_matches_model() {
    let path = path("handles");
    let mut first = Store::create(&path).unwrap();
    let mut model = HashMap::new();
    for (key, value) in [(&b""[..], &b"zero"[..]), (&b"\0\xff"[..], &b"\xff\0"[..])] {
        first.put(key, value).unwrap();
        model.insert(key.to_vec(), value.to_vec());
    }
    let bytes = fs::read(&path).unwrap();
    assert!(matches!(Store::open(&path), Err(Error::Busy)));
    assert_eq!(fs::read(&path).unwrap(), bytes);
    first.put(b"", b"overwritten").unwrap();
    model.insert(b"".to_vec(), b"overwritten".to_vec());
    assert!(first.delete(b"\0\xff").unwrap());
    model.remove(&b"\0\xff"[..]);
    first.close().unwrap();
    let second = Store::open(&path).unwrap();
    assert_eq!(second.len(), model.len());
    for (key, value) in model {
        assert_eq!(second.get(&key), Some(value.as_slice()));
    }
    drop(second);
    fs::remove_file(path).unwrap();
}

#[test]
fn lock_child_probe() {
    let Some(path) = std::env::var_os("OPDB_LOCK_CHILD_PATH") else { return };
    assert!(matches!(Store::open(PathBuf::from(path)), Err(Error::Busy)));
}

#[test]
fn second_process_and_hard_link_alias_are_busy() {
    let path = path("process");
    let alias = path.with_extension("alias");
    let mut first = Store::create(&path).unwrap();
    first.put(b"stable", b"value").unwrap();
    let output = Command::new(std::env::current_exe().unwrap())
        .arg("--exact").arg("lock_child_probe")
        .env("OPDB_LOCK_CHILD_PATH", &path)
        .output().unwrap();
    assert!(output.status.success(), "child output: {}", String::from_utf8_lossy(&output.stdout));
    fs::hard_link(&path, &alias).unwrap();
    assert!(matches!(Store::open(&alias), Err(Error::Busy)));
    drop(first);
    let reopened = Store::open(&alias).unwrap();
    assert_eq!(reopened.get(b"stable"), Some(&b"value"[..]));
    drop(reopened);
    fs::remove_file(alias).unwrap();
    fs::remove_file(path).unwrap();
}

#[test]
fn failed_open_does_not_create_or_modify_a_file() {
    let path = path("missing");
    assert!(Store::open(&path).is_err());
    assert!(!path.exists());
    let first = Store::create(&path).unwrap();
    let bytes = fs::read(&path).unwrap();
    assert!(Store::create(&path).is_err());
    assert_eq!(fs::read(&path).unwrap(), bytes);
    drop(first);
    fs::remove_file(path).unwrap();
}
