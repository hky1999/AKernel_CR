# Storage and lifecycle boundaries

## Control and metadata

The public AKernel SDK calls the ADX Environment API. The API Server and Coordinator schedule work on adxlet, and adxlet drives sandboxd. The Coordinator's task Redis state records Environment ownership, snapshot references, checkpoint-reader reservations and shared-volume attachments. It is not the JuiceFS inode/block database.

Reader protection is persisted before runtime start. A returned delete request is not sufficient to release a checkpoint reader: release requires a positive, execution-bound retirement proof. A timeout, missing process, elapsed lease or a restarted controller alone is not that proof. The gVisor retirement implementation waits for the relevant namespace holders and descendants; sandboxd retains the operation journal and identity needed after restart.

## JuiceFS

Each logical node has its own JuiceFS client and mount namespace, both mounting the same format UUID. The functional lab uses PostgreSQL metadata plus a Ceph RGW S3 endpoint; an S3-compatible service may replace that endpoint only after its durability and failure behavior are validated.

An immutable checkpoint is published after the required writes and synchronization barriers. Publication/READY is not simply the presence of an intermediate directory. The restored runtime may still retain references to the shared files; reader retirement protects their lifetime. Do not enable automatic deletion based solely on an age threshold.

JuiceFS upload behavior is controlled by the client and its synchronization semantics. The accepted lab disables writeback. This is not a separate AKernel background-publish queue and does not make an object PUT count equivalent to checkpoint durability.

## Filesystems

- Read-only root image: preserve the existing EROFS / Nydus / virtio-fs routes supported by the selected runtime.
- gVisor private writable layer: file-descriptor-backed filestore, with checkpoint handling and background restore configured explicitly.
- Firecracker private writable layer: per-instance ext4 image backed by the accepted local XFS layout. Its checkpoint copy is a different object from the live disk.
- Shared application volume: controlled JuiceFS directory admission, owner/grantee permissions and RW/RO runtime mounts. A live shared directory is not a private checkpoint branch.
- Memory: retain each runtime's existing checkpoint and restore implementation. Integrity checks can cause reads before lazy-memory faults; do not infer cold-S3 read volume from a fast API response.

## Accepted optimization

The sandboxd integrity path hashes independent components with concurrency bounded to two, while retaining full SHA-256 verification. It does not skip integrity, relax synchronization, or claim that a size/mtime cache proves immutable generation identity.

See the source manifest and paired samples for the actual accepted version combination. Unaccepted Coordinator shutdown changes are deliberately absent.

