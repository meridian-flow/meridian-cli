# Spec: File Locking (R1, R2)

## R1: Cross-Platform File Locking

### LOCK-01: Blocking exclusive lock acquisition
When `FileLock::acquire` is called with a lock path,
the system shall block the calling thread until the advisory lock is acquired,
then return a `FileLock` guard that holds the lock.

### LOCK-02: Non-blocking try-acquire
When `FileLock::try_acquire` is called with a lock path,
the system shall attempt to acquire the advisory lock without blocking.
If the lock is held by another process, the system shall return `Ok(None)`.
If the lock is available, the system shall return `Ok(Some(FileLock))`.

### LOCK-03: RAII release
When a `FileLock` is dropped,
the system shall release the advisory lock automatically.

### LOCK-04: Parent directory creation
When `FileLock::acquire` or `try_acquire` is called with a lock path whose parent directories do not exist,
the system shall create the parent directories before attempting to acquire the lock.

### LOCK-05: Cross-platform compilation
The `FileLock` implementation shall compile and function on both Unix and Windows targets without requiring elevated privileges or developer mode on Windows.

### LOCK-06: No Unix-only dependencies in lock path
The `FileLock` implementation shall not use `libc::flock`, `AsRawFd`, or any `#[cfg(unix)]`-only API.

## R2: Resolve Command Lock Acquisition

### LOCK-07: Resolve acquires sync lock
When `mars resolve` executes,
the system shall acquire the sync advisory lock (`sync.lock`) before reading or writing `mars.lock`.

### LOCK-08: Resolve holds lock through completion
When `mars resolve` has acquired the sync lock,
the system shall hold the lock until all lock file reads and writes are complete.

### LOCK-09: Concurrent resolve + sync safety
When `mars resolve` and `mars sync` execute concurrently,
the system shall serialize their access to `mars.lock` via the sync advisory lock,
so that no concurrent corruption occurs.
