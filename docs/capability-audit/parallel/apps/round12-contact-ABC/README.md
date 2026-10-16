# Contacts public JS → ABC → image review

The existing source GN has a real route from `contact.js` to the installed
`libcontact.z.so`. A full build with freshly generated GN and missing generated
outputs can reproduce this route. The existing out directory does **not** prove
that the new picker JS was compiled: the actual old library still contains the
old JS and old ABC. No new ABC, image, guest or runtime proof is claimed here.

This batch adds only a pure Python payload checker, its host tests and this
read-only report. Product patches, the shared suite/coordinator and all root
build/package scripts remain untouched. All 34 apps requirements and 53
cumulative upstream target paths remain in the report; no ledger entry closes.

## Actual fixed source and old graph

The narrow source/out query used read-only container
`ohos-qemu-parallel-source-20261016-02`. `readonly-snapshot.json` contains exact
source/output hashes, old graph/action/link/install rows, mtime and container
filesystem inode observations. `collect_readonly.py` reproduces that query with
the same pure Python ELF reader passed through stdin. It neither writes into the
container nor executes a compiler, GN, Ninja, HDC, native helper or guest.
Container filesystem inode numbers are not system.img inode evidence.

The source project is `applications/standard/contacts_data`, fixed revision
`c73bd27daa3fcd8ed6099b17cbffbd7021e3873e`. Its `bundle.json` includes
`//applications/standard/contacts_data/contacts:contact` in `build.group_type.fwk_group`.
The concrete ARM64 target is
`//applications/standard/contacts_data/contacts:contact(//build/toolchain/ohos:ohos_clang_arm64)`.
`contacts/BUILD.gn` defines:

1. `gen_contact_abc`: explicit `src/contact.js` input, actual product-host
   `ets_frontend:es2panda` compiler dependency, and `contact.abc` output.
2. `contact_js` and `contact_abc`: real `gen_js_obj` actions from the source JS
   and generated ABC, respectively. Both depend on `gen_contact_abc`.
3. The `contact` shared library: both blob objects plus 12 native objects are
   actual link inputs. `relative_install_dir="module"` installs the library.

The action is in `out/arm64_virt/toolchain.ninja`, rather than a standalone
`gen_contact_abc.ninja`. The old graph's ABC action and **both** objcopy actions
contain `/Volumes/PSSD/qemu/openharmony/...` absolute host paths. The native link
also contains an old absolute version-script path. Reusing that graph while
only deleting ABC is insufficient; a new GN graph must refer to the current
source, current out and actual product tool binaries.

The root runner invokes `./build.sh --build-target images`; it does a load-only
prepass and then explicitly sets `--build-only-load=false`. Real hb
`modules/ohos_build_module.py:111–115` calls GN only if `build_only_load` and
`fast_rebuild` are both false. `fast_rebuild` defaults false, but hb arguments
persist in `/ohos/out/hb_args/buildargs.json`. The read-only snapshot has no such
file. There is no observed skip-GN failure in this snapshot; the narrow hardening
request is to explicitly pass `--fast-rebuild=false` and retain actual GN and
new Ninja evidence for the representative build. Root owns that change.

The old install metadata selects source
`applications/contacts_data/libcontact.z.so`, destination
`system/lib64/module/libcontact.z.so`, with install enabled. Its staged file
equals the linked DSO, but this is old out metadata, not a freshly extracted
image. The native module embeds ABC; a separate installed `contact.abc` is not
expected. The image verifier must resolve `/lib64/module/libcontact.z.so` and
`/system/lib64/module/libcontact.z.so` to exactly one real inode (aliases may name
that same inode), extract it and compare its bytes. Looking for a filename or
matching only a diagnostic library cannot substitute for that operation.

## What is actually in the old output

| Input / output | Actual SHA256 | Bytes |
| --- | --- | ---: |
| Fixed snapshot `contact.js` | `37a2627df3602a73c71b0568c0b163333f6db404a7aa9dd2ffa3015353f434f2` | 21507 |
| Old generated `contact.abc` | `08d3d2c9d9c1b91235a7935bbe9e50ef2c35310c02e6fce7bad9e4a1fb474d49` | 18932 |
| Old linked/staged `libcontact.z.so` | `ae8655b101e5d3c4a9424e894f3e41771007f3652797344a6940c29f855502bd` | 476960 |
| Delivered picker JS candidate | `ae22907681082d8f7ccdaeaa81ee80d3da31114353bf2b167a060c2cf946b759` | Not present in that snapshot |

The actual old unstripped library's `_binary_contact_js_start/end/size`
addresses cover 21507 bytes at VA 449828; its ABC symbols cover 18932 bytes at
VA 430896. The parser checked the source/generated inputs, both ELF blob
objects, unstripped file-backed sections, and linked/staged PT_LOAD bytes.
They match the two **old** hashes above. The native library has a later mtime
than the ABC; that timestamp cannot establish that new JS was regenerated.

Both real NAPI exports exist in dynsym and executable PT_LOAD ranges. Their
eight-byte CFI jump-table stubs are legitimate; an arbitrary minimum function
length would wrongly reject the product. The static getter implementation in
`native_module.cpp` returns the actual blob start/end range. A full native
source/link witness still has to bind that implementation to the installed DSO.

## What the first full build must retain and regenerate

`fresh-build-contract.json` enumerates the exact 18 ARM64 phone outputs relative
to `out/arm64_virt`: the ABC, two blob objects, all 12 contact native objects,
linked DSO, unstripped DSO and staged DSO. Preserve the previous files, then make
these outputs absent before the actual full build. This is deliberately a
small explicit set, rather than deleting the source tree or shared compiler
outputs. Stamps alone do not prove regeneration; missing real data/object/link
outputs force traversal even with `restat=1`.

Root assigned the shared `qemu_contacts_build_witness.py` implementation to the
system agent. The contract includes the nine delivered final source/header
hashes and component composition: attribute_mapping, record_classes,
sync_mode → picker_result_protocol. In particular, the JS final hash must be
the candidate hash above, and the full native request, callback header, protocol
header and native registration source must be present. Reusing this read-only
snapshot's predecessor JS is a real failure.

The full build proof must retain the actual GN graph, compiler/wrapper input
hashes, source-to-output arguments and execution logs, one ABC action, two blob
actions, 12 CXX edges, the actual contact SOLINK and completed image build.
`generate_js_bytecode.py` prints its real es2abc argv and `execution_path`, uses
the actual tool, waits and returns failure on nonzero exit. Under the inspected
GN it invokes:

```text
cwd=<current out>/clang_x64/arkcompiler
./ets_frontend/es2abc --output <current ABC> --module <current contact.js> --target-api-sub-version=beta3
```

The current GN supplies neither `--merge-abc`, `--module-record-field-name` nor
`--source-file`. The wrapper defaults the latter names to the input path.
`run_objcopy.py` uses the input basename from its real parent directory, which
explains `_binary_contact_js_*` and `_binary_contact_abc_*`. A fresh successful
ABC SHA is not predicted or hand-filled here.

## New independent payload check

```python
batch_apps_contact_payload.verify_payloads(
    source_js=current_js,
    abc=fresh_actual_abc,
    js_object=current_contact_o,
    abc_object=current_contact_abc_o,
    unstripped=current_unstripped_library,
    linked=current_linked_library,
    staged=current_staged_library,
    image_dso=independently_extracted_unique_image_library,
    arch='arm64',
)
```

The exact CLI is:

```text
python3 ci/capability-audit/batch_apps_contact_payload.py
  --source-js FILE --abc FILE --js-object FILE --abc-object FILE
  --unstripped FILE --linked FILE --staged FILE --image-dso FILE
  [--arch arm64|x86_64|armv7a] --output NEW_JSON
```

The bounded ELF32/ELF64 reader verifies architecture/type/header and table
ranges, real symbol-section boundaries, unique PT_LOAD mappings, exact blob
bytes, defined public executable NAPI exports, and complete linked/staged/image
DSO byte identity. It reads blob boundaries from unstripped `.symtab`; stripped
product libraries need not export those internal symbols. It checks the Panda
header size and Adler32, following the fixed `libpandafile/file.h`/`file.cpp`
contract. It records the ABC version but does not claim to validate its complete
semantic format. No ELF or external executable is invoked.

The result is intentionally `pass_payload_identity_ONLY`. Build/compiler
execution, unique image extraction, module-record/literal binding, public
runtime, first artifact and ledger claims are all explicitly false. The
enclosing root witness/image extractor/runtime acceptance must establish those
separate facts. Passing a staged file as the image argument cannot provide
image-extraction evidence; the helper explicitly leaves that claim false.

`loader-source-contract.json` preserves the actual framework chain:
NativeModuleManager finds `NAPI_contact_GetABCCode`, obtains its buffer/length,
and ArkNativeEngine calls `LoadArkModule`, `ExecuteModuleFromBuffer`, then
`GetExportObjectFromBuffer(...,"default")` with runtime filename
`libcontact.z.so/contact.js`. The source implements that route. No new actual
ABC has yet been decoded for `moduleRecordIdx`/literal-array relationships or
executed by that loader. A source dependency scan of 1074 files and zero HSP
imports, by itself, cannot prove any such ABC property.

The 20 lightweight tests pass: 17 synthetic payload/parser checks and three
existing exact-component/public JS checks, the latter executing 86 actual JS
wrapper scenarios with explicit host doubles. Counterexamples reject a changed
current JS/ABC, foreign blob object, changed image, consistent but wrong
installed payload, stripped file substituted for symbol evidence, conflicting
symbols, non-executable/undefined export, wrong machine, truncated tables,
unbacked/ambiguous VA ranges and invalid Panda header/size/checksum. All three
ABI ELF classes are covered synthetically. `host-checks.log/json` retain the
command, exit, input tool hash and scope. These are neither compiler output nor
fresh product runtime evidence. No remaining package matrix is released.
