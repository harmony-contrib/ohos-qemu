# Historical QEMU Mesa mapping synchronization

Apply this component through the single common build plan. It installs the
numbered patch and guarded source helper for the **actual Mesa 21.3.3 QEMU
build source**, commit `995d2506d18924b48db0cf40e6ad7de04fc4e558`; it does not
apply the historical patch to the release checkout's Mesa 25 source.

Based on upstream Mesa `d318d65b798275bd62bfab41f57a7d03d13852da` (map/unmap
mutex). Initialize the mutex for both newly created and PRIME-imported targets,
handle mutex-init failure, and destroy it on the applicable failure/final
cleanup paths. Mapping counts, pointers and all unmap branches are serialized;
the returned offset pointer is captured before releasing the lock.

No drawing is skipped on map failure and no identity, permission, protocol,
render backend or public API checks are bypassed. Complete original/repaired
file hashes protect cached extracted sources. Fresh and repeated builds use
the same helper, including all three ABIs and both profiles.

The extracted historical tree can be nested in the release Git checkout.
Apply in an isolated scratch tree, verify the complete repaired file, then
atomically replace only the historical KMS source. Do not let Git discover the
outer Mesa 25 repository and silently filter out the patch. The installer can
upgrade the exact previous helper payload; unknown installed assets still fail
before any sibling is changed.

The exact native functions have a deterministic host interleaving regression:
the original returns an invalid mapping after concurrent unmap; the repaired
version retains the mapping until the final owner releases it. Error and
read-only/read-write/duplicate-unmap boundaries run under ASAN/UBSAN. This is
not proof that the independent RS null-transfer crash is fixed; newly packaged
guest rendering and stability validation are still required.
