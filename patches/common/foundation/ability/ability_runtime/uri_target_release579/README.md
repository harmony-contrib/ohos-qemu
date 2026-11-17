# URI target-exit observation only

This delivery is complete and will receive no further writes. It changes only
`UriPermissionManagerStubImpl::RevokeFileUriPermission` in the actual ability
runtime project `6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`.

The before source was copied from the closed RO06 export, whose SOURCE.json is
`1358c533909f5a5090a8797a009aac4dc51368ad1d2700467899eb04496be344`:
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r65-readonly-source-579-06/source/foundation/ability/ability_runtime/`.

The method retains its lock, authorization at the existing caller, policy
revocation order, error return, erase, and success return. It records the actual
`UnSetAllPolicyByToken` result and the actual erase count; successful sandbox
records also include the real policy cutoff and map count while the same lock
is held. Failed revocation records have `erased:0` because the original early
return is preserved. A non-sandbox build says `unset_result:unavailable` and is
not evidence of sandbox policy removal. The cutoff comes from the original
high_resolution_clock; it is not asserted to be monotonic or a guest uptime.

The preexisting no-map early return remains unchanged and emits no success
record. New QEMU verification must require an actual sandbox:1 unset_result:0
erased:1 remaining:0 record for the actual target BMS token, in a new raw hilog
window tied to the held guest and service process. It must also observe the
target exit, preserve the grantor's file/inode/content through the check, and
replay the actual recipient FileIO observations. Root-running URI permission
client false values are not a valid permission oracle.

No API, permissions, grant, revoke, or lifecycle behavior is added. No candidate
code, parser, test, SDK, compiler, resource, or QEMU execution was performed.
Diff production and SHA/byte inventory are source preparation only. Initial
portable diff/hash invocations were incompatible with this host; the recorded
patch was subsequently produced by /usr/bin/diff and hashes with LC_ALL=C.
Target compilation and runtime verification are pending. The root agent owns
the final source component and integration with other disjoint method changes.
