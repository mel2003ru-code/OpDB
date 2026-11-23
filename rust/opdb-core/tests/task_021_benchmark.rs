#[path = "../examples/bench_v0.rs"]
mod bench;

#[test]
fn bounded_workload_matches_independent_map_after_each_phase() {
    let n=1_000; let scratch=bench::Scratch::new(); let path=scratch.file("test");
    let keys:Vec<Vec<u8>>=(0..n).map(bench::key).collect(); let order=bench::order(n);
    let mut model=std::collections::HashMap::new();
    let mut store=opdb_core::Store::create(&path).unwrap();
    for &i in &order { let v=bench::value(i,16); store.put(&keys[i],&v).unwrap(); model.insert(keys[i].clone(),v); }
    bench::verify(&store,&model,&keys);
    for &i in &order { let v=bench::value(i,16); store.put(&keys[i],&v).unwrap(); }
    for &i in order.iter().step_by(2) { assert!(store.delete(&keys[i]).unwrap()); model.remove(&keys[i]); }
    bench::verify(&store,&model,&keys); store.close().unwrap();
    let reopened=opdb_core::Store::open(&path).unwrap(); bench::verify(&reopened,&model,&keys);
}
