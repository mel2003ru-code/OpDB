use opdb_core::lsm::SyncPolicy;

#[test]
fn variants_are_exact_and_distinct() {
    let all = [
        SyncPolicy::EveryBatch,
        SyncPolicy::OnClose,
        SyncPolicy::Never,
    ];
    assert_ne!(SyncPolicy::EveryBatch, SyncPolicy::OnClose);
    assert_ne!(SyncPolicy::EveryBatch, SyncPolicy::Never);
    assert_ne!(SyncPolicy::OnClose, SyncPolicy::Never);
    assert_eq!(all.len(), 3);
}

#[test]
fn sync_policy_is_copy_and_comparable() {
    let p = SyncPolicy::EveryBatch;
    let q = p; // Copy: p still usable here
    assert_eq!(p, q);
    assert!(p != SyncPolicy::Never);
}

#[test]
fn sync_policy_names_are_exact() {
    assert_eq!(opdb_core::lsm::sync_policy_name(SyncPolicy::EveryBatch), "every_batch");
    assert_eq!(opdb_core::lsm::sync_policy_name(SyncPolicy::OnClose), "on_close");
    assert_eq!(opdb_core::lsm::sync_policy_name(SyncPolicy::Never), "never");
}
