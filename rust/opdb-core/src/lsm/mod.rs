//! Experimental LSM module. Design in docs/LSM_DESIGN.md; on-disk format is
//! EXPERIMENTAL and unstable.
//!
//! Later tasks fill in memtable, WAL, SSTable, flush, compaction, and reads.

/// Sync policy for LSM writes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncPolicy {
    EveryBatch,
    OnClose,
    Never,
}

/// Human-readable name for a sync policy.
pub fn sync_policy_name(p: SyncPolicy) -> &'static str {
    match p {
        SyncPolicy::EveryBatch => "every_batch",
        SyncPolicy::OnClose => "on_close",
        SyncPolicy::Never => "never",
    }
}
