# Contacts / Wallpaper lifetime candidates and pickerSheet review

The batch owns eight business targets: Contacts UIExtension, new PickerSession,
picker presenter, picker page, extension root page and WorkerWrapper; Theme's
phone and pad renderer files. It changes no build metadata, manifest, shared
HAP graph, profile, signing, preinstall, runner or Settings/MMS file. Fixed source
revisions remain Contacts `65de33df8d6d7aaa5797a5625ed0e5938e5cb050` and
Theme `a436a43f1c0948fa12df6d520ec695ae4388a057`.

Contacts now binds selected data, query/task generations, terminal results and
cleanup to the original content session. Original 100-item batching, single
Want URI/contact IDs and default-selection cancellation are retained. Query
rejection produces nonzero failure; official product caller error mapping still
needs verification. Optional worker scopes preserve the existing unscoped call
path and never close shared workers. Scope disposal unregisters owned callbacks,
timers and display/window listeners before closing owned windows. Page, item
reuse and account-query races are fenced. A terminal retry repeats no data
chunks. The legacy unaddressed import broadcast cannot close public picker
sessions; its publisher is ContactList.ets:268, after an ordinary Vcard import.

Theme's original undefined error identifiers are removed. Each creation owns a
generation and window; destroy/recreate invalidates pending creation/load/show
and PixelMap callbacks. Late creation closes its own window. Repeated destroy
or an old failure does not close a new window. This still renders the existing
wallpaper image and does not provide selection/settings UI.

Three host tests pass, including 38 actual-source scenarios. They execute the
real extracted scope/session/worker/presenter/extension/renderer classes and
non-DSL page methods with deferred host adapters; they do not duplicate those
implementations or run ArkUI/NAPI/database/product behavior. Exact metadata →
business application plus two whole-stack replays pass, all prior eight metadata
hashes remain unchanged, manifests/profiles remain byte-identical and unknown
business edits are rejected without mutation. No SDK/HAP/Docker build or QEMU
ran in this batch. Full official system SDK, ABC dependency inspection and newly
packaged representative phone runtime acceptance are still mandatory. The
source repair does not close any of the 34 assigned requirements.

## pickerSheet is an apparently unused declaration, not a proven private dependency

The earlier packaging report treated the manifest's remote HSP as an external
payload requirement. Fixed source review narrows that conclusion: 1,074 tracked
files were inspected. `provider_lifecycle/inspection.json` records exact hashes
and every pickerSheet/PickerMaskLayer/PickerShieldAnimate/AppLockManager text
reference, including comments and test manifests. There are no tracked native
sources/binaries or HAR/HSP/HAP/ABC inputs in this Contacts project. All relevant
imports, PickerSheet/PickerMaskLayer/PickerShieldAnimate invocations and
AppLockManager calls are commented out. Remaining active isShowPickerMaskLayer
state and ordinary ArkUI bindSheet calls do not import or invoke that HSP.

The only active module identity references are the historical
`com.ohos.security.pickersheet` / `pickersheetlibrary` manifest dependency in
entry/src/main/module.json5 and repeated test-manifest dependency entries.
`entry/oh-package.json5` comments out @hw-hmos/pickersheet. The generic
entry/lib/share-plugin.ts function can scan @hw-hmos shared modules when invoked,
but root and entry hvigorfile.ts only export standard appTasks/hapTasks: they do
not import or register sharePlugin. Its reviewed source and build-task hashes
are included in the fixture. No source execution dependency was found. This
does not establish the imports of a not-yet-built ABC, and no manifest was changed.

The root can make a narrow, separately reviewable declaration cleanup after
official SDK compilation: inspect every generated ABC's actual module request /
import tables with the matching Ark disassembler, as well as produced HAP/HSP
metadata, for pickerSheet identities and the generic plugin's activation. Plain
strings absence alone is insufficient. If no executed import exists, remove only
the exact historical bundle/module dependency tuple from the main manifest;
handle matching test entries separately if that target is built. Preserve all
other dependencies, abilities, sys/commonUI type, permissions, APL/ACL, app lock
behavior and bundle identity. Recompile, repeat compiled dependency inspection,
and verify BMS installation and true picker runtime behavior without that HSP.
If an actual import is found, stop the deletion and resolve its real source
dependency. No private HSP is requested merely to satisfy a dead declaration.

The root still owns shared HAP source selection, signed profile preparation,
preinstall authorization, API26 caller/provider validation, native Wallpaper
Launcher fallback and the missing wallpaper settings UI. Contact save/edit and
MeeTime flows outside this selection path require their own runtime review.
