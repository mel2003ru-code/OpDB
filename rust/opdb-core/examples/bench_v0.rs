//! Reproducible, bounded measurement harness for experimental Rust storage v0.
//! This measures process-local calls and full-replay open; it does not prove durability.
use opdb_core::Store;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const SEED: u64 = 2_026_11_23;
const SIZES: [usize; 3] = [10_000, 100_000, 1_000_000];
const VALUE_SIZES: [usize; 2] = [16, 256];
static PEAK_RSS_KIB: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

pub(crate) struct Scratch(PathBuf);
impl Scratch {
    pub(crate) fn new() -> Self {
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = std::env::temp_dir().join(format!("opdb-bench-v0-{}-{stamp}", std::process::id()));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    pub(crate) fn file(&self, label: &str) -> PathBuf { self.0.join(format!("{label}.opdb")) }
}
impl Drop for Scratch {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
}

fn free_bytes(path: &Path) -> u64 {
    let output = std::process::Command::new("df").args(["-Pk", path.to_str().unwrap()])
        .output().expect("df available");
    assert!(output.status.success(), "cannot measure free disk space");
    let text = String::from_utf8(output.stdout).unwrap();
    let kb: u64 = text.lines().nth(1).unwrap().split_whitespace().nth(3).unwrap().parse().unwrap();
    kb * 1024
}

fn available_memory_bytes() -> Option<u64> {
    let text = fs::read_to_string("/proc/meminfo").ok()?;
    let kib: u64 = text.lines().find(|line| line.starts_with("MemAvailable:"))?
        .split_whitespace().nth(1)?.parse().ok()?;
    Some(kib * 1024)
}

fn evict_file_cache_and_count_resident_pages(path: &Path) -> Option<usize> {
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        use std::ffi::c_void;
        #[link(name = "c")]
        unsafe extern "C" {
            fn posix_fadvise(fd: i32, offset: i64, len: i64, advice: i32) -> i32;
            fn mmap(addr: *mut c_void, len: usize, prot: i32, flags: i32, fd: i32, offset: i64) -> *mut c_void;
            fn mincore(addr: *mut c_void, len: usize, vec: *mut u8) -> i32;
            fn munmap(addr: *mut c_void, len: usize) -> i32;
            fn getpagesize() -> i32;
        }
        const POSIX_FADV_DONTNEED: i32 = 4;
        const PROT_READ: i32 = 1;
        const MAP_SHARED: i32 = 1;
        let file = fs::File::open(path).ok()?;
        let len: usize = file.metadata().ok()?.len().try_into().ok()?;
        if len == 0 || unsafe { posix_fadvise(file.as_raw_fd(), 0, 0, POSIX_FADV_DONTNEED) } != 0 {
            return None;
        }
        let mapped = unsafe { mmap(std::ptr::null_mut(), len, PROT_READ, MAP_SHARED, file.as_raw_fd(), 0) };
        if mapped as isize == -1 { return None; }
        let page_size = unsafe { getpagesize() };
        if page_size <= 0 { unsafe { munmap(mapped, len); } return None; }
        let pages = len.div_ceil(page_size as usize);
        let mut residency = vec![0u8; pages];
        let result = unsafe { mincore(mapped, len, residency.as_mut_ptr()) };
        unsafe { munmap(mapped, len); }
        if result != 0 { None } else { Some(residency.iter().filter(|page| **page & 1 != 0).count()) }
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = path; None }
}

fn estimate_bytes(n: usize, value_size: usize) -> u64 {
    // Each key is written once, overwritten once, and half deleted; each record
    // adds 13 bytes plus key/value. Include header and a 1.5x safety margin.
    let records = n as u64 * 2 + n as u64 / 2;
    let average = (13 + 32 + value_size) as u64;
    ((records * average + 12) as f64 * 1.5).ceil() as u64
}

pub(crate) fn key(i: usize) -> Vec<u8> {
    let mut x = (i as u64) ^ SEED;
    x ^= x >> 30; x = x.wrapping_mul(0xbf58_476d_1ce4_e5b9);
    x ^= x >> 27; x = x.wrapping_mul(0x94d0_49bb_1331_11eb); x ^= x >> 31;
    format!("k-{x:016x}-{i:08x}").into_bytes()
}

pub(crate) fn value(i: usize, size: usize) -> Vec<u8> {
    (0..size).map(|j| ((i.wrapping_mul(31) + j * 17 + SEED as usize) & 255) as u8).collect()
}

pub(crate) fn order(n: usize) -> Vec<usize> {
    let mut values: Vec<usize> = (0..n).collect();
    let mut state = SEED;
    for i in (1..n).rev() {
        state ^= state << 13; state ^= state >> 7; state ^= state << 17;
        values.swap(i, (state as usize) % (i + 1));
    }
    values
}

fn peak_rss_kib() -> Option<u64> {
    let text = fs::read_to_string("/proc/self/status").ok()?;
    text.lines().find(|line| line.starts_with("VmHWM:"))?.split_whitespace().nth(1)?.parse().ok()
}

fn reset_peak_rss() -> bool {
    #[cfg(target_os = "linux")]
    { return fs::write("/proc/self/clear_refs", "5\n").is_ok(); }
    #[cfg(not(target_os = "linux"))]
    { false }
}

fn sample_peak_rss() {
    if let Some(kib)=peak_rss_kib() {
        PEAK_RSS_KIB.fetch_max(kib, std::sync::atomic::Ordering::Relaxed);
    }
}

fn percentile(sorted: &[u128], p: usize) -> u128 {
    sorted[((sorted.len() - 1) * p + 99) / 100]
}

fn sample_stride(n: usize) -> usize { (n / 100_000).max(1) }

fn stats(label: &str, times: &mut [u128], elapsed: u128) {
    times.sort_unstable();
    println!("  {label}: total_ms={:.3} sampled_op_us_median={:.3} p95={:.3} p99={:.3}",
        elapsed as f64 / 1e6, times[times.len()/2] as f64 / 1e3,
        percentile(times,95) as f64 / 1e3, percentile(times,99) as f64 / 1e3);
}

fn run(n: usize, vsize: usize, repeat: usize, free: u64) {
    let estimate = estimate_bytes(n, vsize);
    let estimated_memory = (n as u64).saturating_mul((vsize as u64 + 1024) * 5) / 2;
    let available_memory = available_memory_bytes();
    println!("RUN n={n} value_bytes={vsize} repeat={repeat} seed={SEED} estimated_peak_bytes={estimate} free_bytes={free} estimated_memory_bytes={estimated_memory} available_memory_bytes={available_memory:?}");
    if free < estimate {
        println!("RESULT SKIPPED_INSUFFICIENT_DISK");
        return;
    }
    if available_memory.is_some_and(|available| available < estimated_memory) {
        println!("RESULT SKIPPED_INSUFFICIENT_MEMORY");
        return;
    }
    if available_memory.is_none() && n > 100_000 {
        println!("RESULT SKIPPED_MEMORY_UNKNOWN");
        return;
    }
    let rss_reset = reset_peak_rss();
    PEAK_RSS_KIB.store(0, std::sync::atomic::Ordering::Relaxed);
    let scratch = Scratch::new();
    let path = scratch.file("rust");
    let keys: Vec<Vec<u8>> = (0..n).map(key).collect();
    let values: Vec<Vec<u8>> = (0..n).map(|i| value(i, vsize)).collect();
    let overwrite_values: Vec<Vec<u8>> = (0..n).map(|i| value(i.wrapping_add(n), vsize)).collect();
    let order = order(n);
    let mut model = std::collections::HashMap::<Vec<u8>, Vec<u8>>::new();
    let mut store = Store::create(&path).unwrap();
    let mut samples = Vec::with_capacity(n.div_ceil(sample_stride(n)));
    let start = Instant::now();
    for &i in &order {
        let k = &keys[i]; let v = &values[i]; let t = Instant::now();
        store.put(k, v).unwrap();
        let elapsed = t.elapsed().as_nanos();
        if i % sample_stride(n) == 0 { samples.push(elapsed); }
    }
    let put_elapsed = start.elapsed().as_nanos();
    for &i in &order { model.insert(keys[i].clone(), values[i].clone()); }
    sample_peak_rss();
    stats("put", &mut samples, put_elapsed);
    verify(&store, &model, &keys);
    store.close().unwrap();
    let size_put = fs::metadata(&path).unwrap().len();
    let put_resident_pages = evict_file_cache_and_count_resident_pages(&path);
    let put_cold = put_resident_pages == Some(0);
    let start = Instant::now();
    let mut store = Store::open(&path).unwrap();
    let open_put = start.elapsed().as_nanos();
    verify(&store, &model, &keys);
    sample_peak_rss();
    println!("  {}_after_put_ms={:.3} file_bytes={size_put} resident_pages_before_open={put_resident_pages:?}",
        if put_cold { "cold_open" } else { "replay_open" }, open_put as f64/1e6);

    let start = Instant::now();
    for &i in &order {
        assert_eq!(store.get(&keys[i]), Some(values[i].as_slice()));
    }
    println!("  get_existing_total_ms={:.3}", start.elapsed().as_secs_f64()*1e3);
    let missing: Vec<Vec<u8>> = (n..2*n).map(key).collect();
    let start = Instant::now();
    for k in &missing { assert_eq!(store.get(k), None); }
    println!("  get_missing_total_ms={:.3}", start.elapsed().as_secs_f64()*1e3);

    for &i in &order {
        let v = &overwrite_values[i];
        store.put(&keys[i], v).unwrap();
        model.insert(keys[i].clone(), v.clone());
        if i % sample_stride(n) == 0 { sample_peak_rss(); }
    }
    verify(&store, &model, &keys);
    for &i in order.iter().step_by(2) {
        assert!(store.delete(&keys[i]).unwrap()); model.remove(&keys[i]);
        if i % sample_stride(n) == 0 { sample_peak_rss(); }
    }
    verify(&store, &model, &keys);
    store.close().unwrap();
    let size_after = fs::metadata(&path).unwrap().len();
    let final_resident_pages = evict_file_cache_and_count_resident_pages(&path);
    let final_cold = final_resident_pages == Some(0);
    let start = Instant::now();
    let store = Store::open(&path).unwrap();
    sample_peak_rss();
    println!("  {}_after_overwrite_delete_ms={:.3} file_bytes={size_after} resident_pages_before_open={final_resident_pages:?} peak_rss_kib={:?} peak_rss_reset={rss_reset}",
        if final_cold { "cold_open" } else { "replay_open" }, start.elapsed().as_secs_f64()*1e3,
        (PEAK_RSS_KIB.load(std::sync::atomic::Ordering::Relaxed) != 0)
            .then(|| PEAK_RSS_KIB.load(std::sync::atomic::Ordering::Relaxed)));
    verify(&store, &model, &keys);
    drop(store);
    println!("RESULT PASS correctness checked after put, overwrite/delete, close/reopen");
}

pub(crate) fn verify(store: &Store, model: &std::collections::HashMap<Vec<u8>,Vec<u8>>, keys: &[Vec<u8>]) {
    for k in keys { assert_eq!(store.get(k), model.get(k).map(Vec::as_slice), "oracle mismatch {k:?}"); }
    assert_eq!(store.len(), model.len());
}

fn main() {
    let temp=std::env::temp_dir();
    println!("os={} arch={} temp={} rust={} seed={SEED}", std::env::consts::OS,
        std::env::consts::ARCH, temp.display(), option_env!("RUSTC_VERSION").unwrap_or("see rustc --version"));
    for n in SIZES { for vsize in VALUE_SIZES { for repeat in 1..=3 {
        let free=free_bytes(&temp);
        run(n,vsize,repeat,free);
    }}}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_workload_matches_independent_map_after_each_phase() {
        let n=1_000; let scratch=Scratch::new(); let path=scratch.file("unit");
        let keys:Vec<Vec<u8>>=(0..n).map(key).collect(); let order=order(n);
        let mut model=std::collections::HashMap::new(); let mut store=Store::create(&path).unwrap();
        for &i in &order { let v=value(i,16); store.put(&keys[i],&v).unwrap(); model.insert(keys[i].clone(),v); }
        verify(&store,&model,&keys);
        for &i in &order { let v=value(i+n,16); store.put(&keys[i],&v).unwrap(); model.insert(keys[i].clone(),v); }
        verify(&store,&model,&keys);
        for &i in order.iter().step_by(2) { store.delete(&keys[i]).unwrap(); model.remove(&keys[i]); }
        verify(&store,&model,&keys); store.close().unwrap();
        let reopened=Store::open(&path).unwrap(); verify(&reopened,&model,&keys);
    }
}
