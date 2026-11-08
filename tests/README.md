# Independent verification

Quality and Core will submit executable engine tests in separate reviewed PRs. Starter's schema validator tests only handoff metadata and do NOT demonstrate database correctness.

Upcoming suites: independent differential oracle; stale Lens; external writer; concurrent build/cutover; ChangeLog gap; torn tail; crash/reopen; large backlog; prepared-statement invalidation; p50/p95/p99 and total cost.
