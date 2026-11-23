use opdb_core::{Error, Store, FORMAT_VERSION, MAGIC};
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

static NONCE: AtomicU64 = AtomicU64::new(0);

struct Scratch(PathBuf);

impl Scratch {
    fn new() -> Self {
        let n = NONCE.fetch_add(1, Ordering::Relaxed);
        let t = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = std::env::temp_dir().join(format!("opdb-task020-{}-{t}-{n}", std::process::id()));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn file(&self) -> PathBuf { self.0.join("store.log") }
}

impl Drop for Scratch {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
}

fn header() -> Vec<u8> {
    let mut data = MAGIC.to_vec();
    data.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
    data
}

// Test oracle writes records without calling the production serializer or parser.
fn record(op: u8, key: &[u8], value: &[u8]) -> Vec<u8> {
    let mut data = vec![op];
    data.extend_from_slice(&(key.len() as u32).to_le_bytes());
    data.extend_from_slice(&(value.len() as u32).to_le_bytes());
    data.extend_from_slice(key);
    data.extend_from_slice(value);
    let mut crc = !0u32;
    for byte in &data {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    data.extend_from_slice(&(!crc).to_le_bytes());
    data
}

fn write(path: &Path, bytes: &[u8]) { fs::write(path, bytes).unwrap(); }

fn check_map(store: &Store, expected: &HashMap<Vec<u8>, Vec<u8>>, keys: &[Vec<u8>]) {
    assert_eq!(store.len(), expected.len());
    for key in keys {
        assert_eq!(store.get(key), expected.get(key).map(Vec::as_slice), "key {key:?}");
    }
}

#[test]
fn every_short_record_cut_preserves_only_complete_prefix() {
    let cases: Vec<(u8, Vec<u8>, Vec<u8>)> = vec![
        (1, vec![], vec![]), (1, vec![0, 255], vec![0, 10, 255]),
        (1, b"k".to_vec(), b"v".to_vec()), (2, vec![], vec![]),
        (2, vec![0, 255], vec![]),
    ];
    for (op, key, value) in cases {
        let prefix = record(1, &key, b"verified");
        let target = record(op, &key, &value);
        let prefix_end = (header().len() + prefix.len()) as u64;
        for cut in 0..=target.len() {
            let scratch = Scratch::new();
            let mut bytes = header();
            bytes.extend_from_slice(&prefix);
            bytes.extend_from_slice(&target[..cut]);
            write(&scratch.file(), &bytes);
            let mut store = Store::open(scratch.file()).unwrap();
            let mut expected = HashMap::from([(key.clone(), b"verified".to_vec())]);
            if cut == target.len() {
                if op == 1 { expected.insert(key.clone(), value.clone()); }
                else { expected.remove(&key); }
                assert_eq!(store.truncated_tail(), None);
            } else if cut > 0 {
                assert_eq!(store.truncated_tail(), Some(prefix_end), "cut {cut}");
                assert!(matches!(store.put(b"forbidden", b"value"), Err(Error::TailNotRepaired)));
                assert!(matches!(store.delete(&key), Err(Error::TailNotRepaired)));
            } else {
                assert_eq!(store.truncated_tail(), None);
            }
            check_map(&store, &expected, &[key.clone(), b"forbidden".to_vec()]);
            if cut > 0 && cut < target.len() {
                store.repair().unwrap();
                assert_eq!(fs::metadata(scratch.file()).unwrap().len(), prefix_end);
            }
            store.close().unwrap();
            let reopened = Store::open(scratch.file()).unwrap();
            check_map(&reopened, &expected, &[key.clone(), b"forbidden".to_vec()]);
            assert_eq!(reopened.truncated_tail(), None);
        }
    }
}

#[test]
fn large_binary_record_selected_cuts_and_mixed_prefixes() {
    let keys = vec![vec![], vec![0, 255], b"alpha".to_vec(), b"beta".to_vec()];
    for seed in 0..8u8 {
        let mut expected = HashMap::new();
        let mut bytes = header();
        for step in 0..24usize {
            let key = &keys[(step + usize::from(seed)) % keys.len()];
            if step % 5 == 4 {
                bytes.extend_from_slice(&record(2, key, &[]));
                expected.remove(key);
            } else {
                let value = vec![seed, step as u8, 0, 255];
                bytes.extend_from_slice(&record(1, key, &value));
                expected.insert(key.clone(), value);
            }
        }
        let prefix_end = bytes.len() as u64;
        let key = b"large\0key".to_vec();
        let value: Vec<u8> = (0..1024).map(|n| (n as u8).wrapping_add(seed)).collect();
        let target = record(1, &key, &value);
        for cut in [1, 8, 9, 10, 12, 64, 512, target.len() - 5, target.len() - 1] {
            let scratch = Scratch::new();
            let mut damaged = bytes.clone();
            damaged.extend_from_slice(&target[..cut]);
            write(&scratch.file(), &damaged);
            let mut store = Store::open(scratch.file()).unwrap();
            assert_eq!(store.truncated_tail(), Some(prefix_end));
            check_map(&store, &expected, &keys);
            assert_eq!(store.get(&key), None);
            assert!(matches!(store.put(&key, &value), Err(Error::TailNotRepaired)));
            store.repair().unwrap();
            store.close().unwrap();
            let reopened = Store::open(scratch.file()).unwrap();
            check_map(&reopened, &expected, &keys);
            assert_eq!(reopened.get(&key), None);
            assert_eq!(reopened.truncated_tail(), None);
            drop(reopened);
            let mut resumed = Store::open(scratch.file()).unwrap();
            resumed.put(&key, &value).unwrap();
            resumed.close().unwrap();
            expected.insert(key.clone(), value.clone());
            let second_reopen = Store::open(scratch.file()).unwrap();
            check_map(&second_reopen, &expected, &keys);
            assert_eq!(second_reopen.get(&key), Some(value.as_slice()));
            expected.remove(&key);
        }
    }
}

#[test]
fn corrupt_complete_records_are_errors_and_damaged_lengths_are_explicit_tails() {
    let scratch = Scratch::new();
    let path = scratch.file();
    let valid = record(1, b"a", b"value");
    let mut data = header();
    data.extend_from_slice(&valid);
    let start = header().len();

    let mut wrong_magic = data.clone();
    wrong_magic[0] ^= 1;
    write(&path, &wrong_magic);
    assert!(matches!(Store::open(&path), Err(Error::BadMagic)));
    write(&path, &data[..11]);
    assert!(matches!(Store::open(&path), Err(Error::BadMagic)));
    let mut wrong_version = data.clone();
    wrong_version[8] = 1;
    write(&path, &wrong_version);
    assert!(matches!(Store::open(&path), Err(Error::UnsupportedVersion(1))));

    let mut bad_crc = data.clone();
    *bad_crc.last_mut().unwrap() ^= 1;
    write(&path, &bad_crc);
    assert!(matches!(Store::open(&path), Err(Error::Corrupt { offset: 12 })));
    let mut bad_op = header();
    bad_op.extend_from_slice(&record(3, b"a", b"value"));
    write(&path, &bad_op);
    assert!(matches!(Store::open(&path), Err(Error::Corrupt { offset: 12 })));

    for length_byte in [start + 1, start + 5] {
        let mut damaged = data.clone();
        damaged[length_byte] = 255;
        write(&path, &damaged);
        let mut store = Store::open(&path).unwrap();
        assert_eq!(store.truncated_tail(), Some(12));
        assert_eq!(store.get(b"a"), None);
        assert!(matches!(store.put(b"x", b"y"), Err(Error::TailNotRepaired)));
        store.repair().unwrap();
        store.close().unwrap();
        assert_eq!(fs::metadata(&path).unwrap().len(), 12);
    }
    let mut impossible = data.clone();
    impossible[start + 1..start + 5].copy_from_slice(&u32::MAX.to_le_bytes());
    impossible[start + 5..start + 9].copy_from_slice(&u32::MAX.to_le_bytes());
    write(&path, &impossible);
    let mut store = Store::open(&path).unwrap();
    assert_eq!(store.truncated_tail(), Some(12));
    assert!(matches!(store.put(b"x", b"y"), Err(Error::TailNotRepaired)));
    store.close().unwrap();

    let mut extra = data;
    extra.push(0xff);
    write(&path, &extra);
    let mut store = Store::open(&path).unwrap();
    assert_eq!(store.truncated_tail(), Some((12 + valid.len()) as u64));
    assert_eq!(store.get(b"a"), Some(b"value".as_slice()));
    assert!(matches!(store.delete(b"a"), Err(Error::TailNotRepaired)));
    store.repair().unwrap();
    store.close().unwrap();
    assert_eq!(Store::open(&path).unwrap().get(b"a"), Some(b"value".as_slice()));
}

#[test]
fn writer_child() {
    if std::env::var_os("OPDB_TASK020_CHILD").is_none() { return; }
    let path = std::env::var_os("OPDB_TASK020_PATH").unwrap();
    let mut store = Store::create(PathBuf::from(path)).unwrap();
    let mut input = BufReader::new(std::io::stdin());
    for (step, key, value) in [(0, b"a".as_slice(), b"one".as_slice()),
                               (1, b"b".as_slice(), b"two".as_slice()),
                               (2, b"a".as_slice(), b"three".as_slice())] {
        store.put(key, value).unwrap();
        println!("READY:{step}");
        std::io::stdout().flush().unwrap();
        let mut line = String::new();
        input.read_line(&mut line).unwrap();
        if line != "GO\n" { return; }
    }
    store.close().unwrap();
}

#[cfg(target_os = "linux")]
#[test]
fn killed_writer_yields_only_the_confirmed_prefix() {
    use std::sync::mpsc;
    for stop_at in 0..3 {
        let scratch = Scratch::new();
        let mut child = Command::new(std::env::current_exe().unwrap())
            .arg("--exact").arg("writer_child").arg("--nocapture")
            .env("OPDB_TASK020_CHILD", "1")
            .env("OPDB_TASK020_PATH", scratch.file())
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null())
            .spawn().unwrap();
        let stdout = child.stdout.take().unwrap();
        let (send, receive) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let line = line.unwrap_or_default();
                if line.contains("READY:") { let _ = send.send(line); }
            }
        });
        for step in 0..=stop_at {
            let marker = receive.recv_timeout(Duration::from_secs(5)).expect("bounded writer marker");
            assert!(marker.contains(&format!("READY:{step}")), "{marker}");
            if step < stop_at {
                child.stdin.as_mut().unwrap().write_all(b"GO\n").unwrap();
            }
        }
        child.kill().unwrap();
        child.wait().unwrap();
        let store = Store::open(scratch.file()).unwrap();
        assert_eq!(store.truncated_tail(), None);
        let mut expected = HashMap::new();
        expected.insert(b"a".to_vec(), if stop_at == 2 { b"three".to_vec() } else { b"one".to_vec() });
        if stop_at >= 1 { expected.insert(b"b".to_vec(), b"two".to_vec()); }
        check_map(&store, &expected, &[b"a".to_vec(), b"b".to_vec()]);
    }
}
