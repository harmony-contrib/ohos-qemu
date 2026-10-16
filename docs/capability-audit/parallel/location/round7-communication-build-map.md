# Communication full-product build wiring (read only)

Base: `2b085660fc005d7b95ea5bb314809b3603009d71`. All observations come from the fixed read-only inspector `ohos-qemu-parallel-source-20261016-02`, source `/ohos`, product output `/ohos/out/arm64_virt`. The adjacent JSON contains the complete machine-readable commands, Ninja variables, dependency paths, source/metadata hashes and fixed project HEADs. This commit changes only these two documents; no source, compiler helper, ledger or build is changed.

The 15 requested source translation units produce **16 object variants**: `telephony_observer_proxy.cpp` is compiled independently into both `tel_state_registry_api` and `tel_state_registry`. Preserve both product environments. `vendor_report.c` uses the real **cc/C** rule. The generated `wrapper.rs.cc` is an additional complete C++ translation unit.

| Requested source (project relative) | Exact object target (relative to product out) | Rule |
| --- | --- | --- |
| `base/telephony/core_service/frameworks/native/src/telephony_state_registry_client.cpp` | `obj/base/telephony/core_service/frameworks/native/src/tel_core_service_api/telephony_state_registry_client.o` | `cxx` |
| `base/telephony/core_service/frameworks/native/src/telephony_state_registry_proxy.cpp` | `obj/base/telephony/core_service/frameworks/native/src/tel_core_service_api/telephony_state_registry_proxy.o` | `cxx` |
| `base/telephony/core_service/services/tel_ril/src/tel_ril_callback.cpp` | `obj/base/telephony/core_service/services/tel_ril/src/tel_core_service/tel_ril_callback.o` | `cxx` |
| `base/telephony/core_service/services/tel_ril/src/tel_ril_network.cpp` | `obj/base/telephony/core_service/services/tel_ril/src/tel_core_service/tel_ril_network.o` | `cxx` |
| `base/telephony/ril_adapter/services/hril/src/hril_network.cpp` | `obj/base/telephony/ril_adapter/services/hril/src/hril/hril_network.o` | `cxx` |
| `base/telephony/ril_adapter/services/vendor/src/vendor_report.c` | `obj/base/telephony/ril_adapter/services/vendor/src/ril_vendor/vendor_report.o` | `cc` |
| `base/telephony/state_registry/frameworks/ets/ani/observer/src/cxx/observer_ani.cpp` | `obj/base/telephony/state_registry/frameworks/ets/ani/observer/src/cxx/observer_ani_cxx/observer_ani.o` | `cxx` |
| `base/telephony/state_registry/frameworks/js/napi/src/event_listener_handler.cpp` | `obj/base/telephony/state_registry/frameworks/js/napi/src/observer/event_listener_handler.o` | `cxx` |
| `base/telephony/state_registry/frameworks/js/napi/src/event_listener_manager.cpp` | `obj/base/telephony/state_registry/frameworks/js/napi/src/observer/event_listener_manager.o` | `cxx` |
| `base/telephony/state_registry/frameworks/js/napi/src/napi_state_registry.cpp` | `obj/base/telephony/state_registry/frameworks/js/napi/src/observer/napi_state_registry.o` | `cxx` |
| `base/telephony/state_registry/frameworks/js/napi/src/napi_telephony_observer.cpp` | `obj/base/telephony/state_registry/frameworks/js/napi/src/observer/napi_telephony_observer.o` | `cxx` |
| `base/telephony/state_registry/frameworks/native/observer/src/telephony_observer.cpp` | `obj/base/telephony/state_registry/frameworks/native/observer/src/tel_state_registry_api/telephony_observer.o` | `cxx` |
| `base/telephony/state_registry/frameworks/native/observer/src/telephony_observer_proxy.cpp` | `obj/base/telephony/state_registry/frameworks/native/observer/src/tel_state_registry_api/telephony_observer_proxy.o` | `cxx` |
| `base/telephony/state_registry/frameworks/native/observer/src/telephony_observer_proxy.cpp` | `obj/base/telephony/state_registry/frameworks/native/observer/src/tel_state_registry/telephony_observer_proxy.o` | `cxx` |
| `base/telephony/state_registry/services/src/telephony_state_registry_service.cpp` | `obj/base/telephony/state_registry/services/src/tel_state_registry/telephony_state_registry_service.o` | `cxx` |
| `base/telephony/state_registry/services/src/telephony_state_registry_stub.cpp` | `obj/base/telephony/state_registry/services/src/tel_state_registry/telephony_state_registry_stub.o` | `cxx` |

## Rust and cxxbridge chain

The actual GN generation target is `//base/telephony/state_registry/frameworks/ets/ani/observer:observer_ani_cxx_gen`. Its toolchain rule was found by a parent-authorized bounded line scan, at byte `34544524`; the selected block hash is recorded in JSON. No full large graph was loaded or scanned, and ninja was not invoked. From the product output directory, its exact expanded command is:

```sh
/usr/bin/env ../../build/templates/rust/rust_cxxbridge.py --cxxbridge clang_x64/thirdparty/rust_cxx/cxxbridge --cc gen/base/telephony/state_registry/frameworks/ets/ani/observer/src/wrapper.rs.cc --header gen/base/telephony/state_registry/frameworks/ets/ani/observer/src/wrapper.rs.h -- ../../base/telephony/state_registry/frameworks/ets/ani/observer/src/wrapper.rs
```

The script runs the matching fixed `cxxbridge` binary on the complete patched `src/wrapper.rs`, first with `--header`, then without it, and atomically writes both outputs. The binary is the real host Rust target `clang_x64/thirdparty/rust_cxx/cxxbridge`; its small Ninja, host Rust command, dependencies and binary SHA256 are recorded. The fixed cxx crate is version `1.0.130`, revision `b5b9ba474068c480dfff89176f539c6de2de12f2`. No generator was executed for this task.

The two generated outputs are `gen/base/telephony/state_registry/frameworks/ets/ani/observer/src/wrapper.rs.h` and `wrapper.rs.cc`. The patched bridge namespace is `OHOS::ObserverAni`; the new Rust callback is `on_communication_state_updated(slot_id: i32, is5a: bool)`, and the new C++ export is `HasCommunicationPermission() -> bool`. The generator must see the full patched wrapper, not an extracted declaration.

The generated C++ source object is `obj/out/arm64_virt/gen/base/telephony/state_registry/frameworks/ets/ani/observer/src/observer_ani_cxx/wrapper.rs.o`. It and the actual `observer_ani.cpp` object form `obj/base/telephony/state_registry/frameworks/ets/ani/observer/libobserver_ani_cxx.a`. Its exact compile and archive recipes are included. Shell recipes such as the archive `rm ... && llvm-ar ...` are retained as shell commands, rather than mislabeled executable argv.

The real product Rust target is `//base/telephony/state_registry/frameworks/ets/ani/observer:telephony_observer_ani`, **crate_type=dylib**. Its outputs are `telephony/state_registry/libtelephony_observer_ani.so` and `lib.unstripped/telephony/state_registry/libtelephony_observer_ani.so`. Compile/link from the full `src/lib.rs` and modules `observer.rs`, `register.rs`, `bridge.rs`, `wrapper.rs`, and `log.rs`. JSON preserves the actual `rust_dylib` wrapper command, Rust flags/environment, extern aliases, native link dependencies and response-file contents. A Rust syntax/parser check or C++ wrapper compile cannot substitute for this actual Rust target.

The actual externs include `hilog_rust`, `cxx`, `serde` and `ani_rs`; native product dependencies include the C++ bridge archive, ANI runtime, registry API, core service API/common library, IPC, NAPI, eventhandler and their recorded product libraries. Keep the actual prebuilt/target artifacts named by the Ninja edges. The frozen Rust wrapper commands contain an original build-host absolute clang prefix under `/Volumes/PSSD/qemu/openharmony`; root must map that observed prefix to its private execution environment using its existing staging/compiler support. This task makes no tool change.

## Full headers and generation prerequisites

Using each object variant's ordered real `-I` paths, the read-only inspection resolved the complete textual include files inside the three telephony projects and generated RIL/state-registry headers. The inventory contains **166 headers: 145 unmodified full files and 21 modified headers**. Of the unmodified files, 72 belong to telephony projects. Each path is listed with its fixed raw SHA256; modified files also carry their component final SHA256. Full source files, every per-variant direct include and the relationship to required headers are in JSON. Do not replace class interfaces with reduced declarations when staging.

No `.o.d` file exists for the 16 object variants. Therefore this static inspection is **not a compiler-produced complete transitive dependency closure**. External platform headers are recorded at the full-file boundary; their own transitive headers, the compiler built-ins and complete product sysroot/include trees must remain available. Conditional includes are conservatively recorded. The map preserves unresolved standard/conditional names rather than pretending a header slice proves a platform build.

The fixed out contains original, pre-patch generated `wrapper.rs.h/.cc` and RIL headers. Their hashes identify existing inputs only. Parent must regenerate both wrapper files from the complete patched Rust source and use its real inherited RIL callback162 declarations/proxy/stub before compiling the new methods. Retain all inherited v1_1 through v1_5 type/interface headers, including the unchanged ones; the actual product include path is `gen/drivers/interface/ril`.

Parent order: stage the exact guarded 42-file communication component and complete headers; stage actual regenerated RIL inputs; regenerate the wrapper; compile all 16 source-object variants plus the generated wrapper object; build the bridge archive; compile/link the Rust dylib and affected native modules. Root alone performs real platform builds, module links and representative-package/runtime acceptance.

## Verification performed

Only bounded read-only metadata queries and local JSON/coverage/hash/command-expansion consistency checks ran. Nine relevant module Ninja files were streamed (largest 241608 bytes); the host generator Ninja is 8844 bytes. A parent-authorized targeted stream located the exact cxx generation action and stopped without loading the 96.8 MB toolchain graph. No ninja, compiler, cxxbridge, package, VM, HDC, Docker start/restart or runtime validation was run. All 22 assigned IDs remain open and this documentation closes 0 behavior gaps.
