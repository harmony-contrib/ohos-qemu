# Communication AccessToken dependency repair

Base: `14db697bae8b7bc855b83679fa63ab3ea963a798`. Root's completed real
communication batch04 compiled 17 complete object variants:14 passed,3 failed.
The failed event_listener_handler/napi_state_registry/observer_ani consumers
include `accesstoken_kit.h` but their actual GN targets did not declare its SDK.
The failed batch remains a failed batch; this source/guard repair is not platform
compile, Rust link, fresh GN, package or runtime success.

The second communication patch changes exactly:

- `base/telephony/state_registry/frameworks/js/napi/BUILD.gn`, target `observer`.
- `base/telephony/state_registry/frameworks/ets/ani/observer/BUILD.gn`, target
  `observer_ani_cxx`.

Both add `access_token:libaccesstoken_sdk` to `external_deps`. No manual include
path or reduced API declaration is added. The existing state-registry service
already declares the same SDK dependency. The fixed provider's published
`libaccesstoken_sdk.public_configs` include `:accesstoken` with literal
`include_dirs = [ "include" ]`, plus its real generated IDL config; the bundle
innerkit maps to the same target. Root may use these actual declared exports in
its explicitly labeled full-TU diagnostic before fresh GN is available.
The new dependency must also propagate into the eventual Rust/native product
link; frozen pre-change Ninja flags alone do not prove that GN propagation.

The component now pins complete44-file original/prefix1/final states over its
three fixed projects. Prefix1 accepts the previously delivered complete42-file
patch plus untouched original GN files, and applies only patch2. Unknown or mixed
states, wrong HEADs, changed patches and symlinks remain rejected before writes.
The original binary patch and CRLF enum bytes remain unchanged. Fixtures and
prefix tests include both complete GN files. Cumulative upstream targets are75
(location27 + communication44 + RTT4), with all22 assigned IDs open and0 closed.

Validation: strict guard2 tests PASS11.532s, covering all three legal states and
reapply plus rejection boundaries. Independently, all44 complete fixed original
files (including raw CRLF) match production hashes; actual patch1 reaches exact
prefix1, and patch2 reaches exact final. Only local Python/Git source application
checks ran; no ninja, compiler, Docker start, package or guest was run.

Root owns the next actual three-TU verification and later the complete Rust
helper execution. The helper is a separate pending batch and is not part of this
commit. Batch04's observer_ani consumer failed and cannot be reused as a passed
archive input; successful object reuse must be independently bound to its exact
source/generated-input evidence.
