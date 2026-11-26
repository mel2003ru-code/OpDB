//! Experimental LSM module. Design in docs/LSM_DESIGN.md; on-disk format is
//! EXPERIMENTAL and unstable.
//!
//! Later tasks fill in memtable, WAL, SSTable, flush, compaction, and reads.

// All modules are declared here once; later tasks fill their own file and never rewrite this one.
pub mod compaction;
pub mod db;
pub mod manifest;
pub mod memtable;
pub mod sstable;
pub mod wal;

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
