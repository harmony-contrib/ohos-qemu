# Actual product runtime helper builder

`batch_system_build_runtime_helpers.py` prepares and builds three root-owned,
read-only guest observers against the actual ARM64 product innerkits:

| Selector / output basename | Immutable repository fixture | Actual APIs |
| --- | --- | --- |
| `contact_picker_observer` | `fixtures/batch_apps/contact_picker_seed/observer.cpp` | AppMgrClient GetAllRunningProcesses and AccessTokenKit |
| `wallpaper_default_resolver` | `fixtures/batch_media/wallpaper_runtime/default_resolver.cpp` | config_policy_utils and cJSON, real manifest/fallback file reads |
| `wallpaper_token_query` | `fixtures/batch_media/wallpaper_receipts/token_query.cpp` | Actual AccessToken HAP identity and permission reads |

No fixture, API implementation, product source, SDK interface, permission or guest
process is modified by this task. No helper is executed. The third fixture is the
media batch integrated by root at `9301a95`.

## Root invocation under one resource lease

Freeze the repository including these fixtures and mount it read-only. Mount the
actual source at `/ohos:ro` and its actual output at `/ohos/out:ro`. Supply a new
private output outside both source and repository. The builder checks real
`statvfs(ST_RDONLY)` on source/out and each consumed source/header/tool/library;
it does not change mount or filesystem permissions.

```sh
python3 /work/ci/capability-audit/batch_system_build_runtime_helpers.py \
  --source-root /ohos --product arm64_virt --output /evidence/helpers
```

Default selects all three, sequentially. `--helper contact_picker_observer` may be
repeated to select a subset without duplicates. `--plan-only` performs input and
existing-graph queries only and returns `planned_NOT_compiled`; it never invokes
clang or regenerates/builds a GN target. An existing output is rejected so a failed
attempt cannot be silently overwritten. Root owns the actual compile/link lease.
The diagnostic compilation/link subprocess deadline is180 seconds with a3-second
termination grace for that command's own process group. ThinLTO and linker threads
are capped at2; output/dependency/cache/temp paths are private.

## Actual GN/ABI/CFI handling

The builder asks the real product Ninja only for `-t commands -s` of fixed actual
objects. It records the complete original commands, target graph/source BUILD.gn
hashes and the derived complete compiler/linker argument arrays. It invokes the
actual product clang++ directly and does not run ccache or the product wrappers
that write to product output. Known launcher/source/output/dependency operands
are checked; arbitrary shell/response syntax, unknown launchers, source mismatch,
ABI-namespace defines, unexpected writable effects and missing safety flags fail.

- Contact observer uses the actual AppMgr compile options and public include graph
  plus actual AccessToken include exports. The inspected AppMgr graph selects
  full LTO but no CFI, so the helper explicitly augments CFI/trap/visibility flags
  from the actual AccessToken CFI graph. It preserves AppMgr's LTO choice. This
  augmentation is recorded as a diagnostic configuration.
- Default resolver uses the actual Wallpaper service C++17/CFI command and its
  existing configpolicy/cJSON exported include paths. Its selected CFI-vcall and
  CFI-icall categories are preserved, including the actual preceding flag order.
- Token query uses the actual AccessToken C++17/CFI command and exported headers.

The selected real `ldflags` and runtime `libs`, real system Scrt1/crti/crtn objects,
and actual product DSOs form the private PIE link. The same selected solink
edges supply their actual DSO dependencies and read-only rpath-link directories;
no allow-shlib-undefined relaxation is introduced. System symbol-proxy libc is
excluded in favor of the unchanged actual system runtime library flags. Actual product sanitizers,
LTO, CFI version script and warnings are retained. Only the original component's
DSO-specific export map is removed because it is not a new helper's export
contract. CFI export rules remain. Cache paths and job counts are redirected for
the resource boundary; PIE/export and read-only linker trace flags describe this
new executable. No new warning suppression is added. Source and product output
remain read-only during all commands.

This is **not a fresh GN target selection proof**: these three helpers are new
diagnostics, constructed using the real existing product graph and system tools.
No target or shared BUILD.gn is added. A stale/missing graph or DSO fails rather
than being replaced by a stub or SDK library. The system product musl sysroot is
required; SDK sysroots and ABI namespace substitution are rejected. A compiled
static assertion requires `std::string` to be the actual `std::__h` type and
requires exceptions disabled. This does not define or alias the namespace.

Successful output additionally requires actual ELF64 AArch64 PIE/musl interpreter,
a defined `__cfi_check` symbol, actual `std::__h` symbols and no SDK `std::__n1`
symbols, and the required real product SONAME dependencies. The AccessToken DSO
must retain its selected CFI definition too. Dependency files capture all actual
headers, including the real libc++ headers. The linker trace captures the actual
opened archives/DSOs/runtime libraries. Source, header, compiler, CRT, graph,
blacklist/version-script, actual link inputs and product DSO hashes are recorded,
then all read-only inputs are rechecked. Actual helper/ABI guard copies are also
checked against their initial hashes. Ambient SDK include/library overrides are
removed from the compiler environment.

Every helper starts with a failure row. Its complete command/log/exit/timeout is
saved as it runs. A failed helper does not stop the other two; unavailable inputs
and skipped stages remain explicit failures. `pass_compile_link_ONLY` requires
all selected helpers and unchanged inputs. It cannot mark runtime, permission,
UI, new-package behavior or the representative first-artifact gate passed.

## Completed light evidence

`tests.log`:15 parser/control-flow tests passed without Ninja/clang. They cover
real-option preservation, selected CFI categories, safety-flag rejection, private
link adaptation, variable parsing, dependency escaping, read-only/output overlap,
three-failure collection, command launch log preservation, linker trace and
ELF/defined-symbol parser negatives. Constructed ELF parser bytes are unit data;
they are never recorded as product compilation. Initial macOS `/var` vs `/private`
canonicalization issues were collected and fixed before this passing batch.

`actual-GN-static-preflight.json`: narrow Python-only reads from the read-only
inspector captured and parsed the three actual existing graphs and their flag
choices. It reconstructs the existing cxx rule for parser checking only. Neither
Ninja nor any compiler ran for this evidence. The report freezes all three actual
repository fixture hashes. Real plan queries, compile, link, actual output ELF
checks and guest execution remain pending root's next consolidated resource batch.

The separate `live-sdk39-schema/` small batch records the root-requested
OpenHarmony/API26/Hvigor6 generator correction and its17 light tests. No native
compile or HAP build was started in either delivery by this agent.
