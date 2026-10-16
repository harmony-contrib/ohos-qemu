# Contacts / Theme packaging preparation, 2026-10-16

This bounded batch changes eight build metadata files. It does not change the
previous Settings/MMS business candidates or any shared HAP GN, signing,
preinstall, native service or runtime acceptance script. `inspection.json`
contains SHA256-pinned compressed source inputs read from container
`ohos-qemu-parallel-source-20261016-02`; no container source or out was modified.
`candidate-hashes.json` identifies the eight final metadata files.

Contacts revision `65de33df8d6d7aaa5797a5625ed0e5938e5cb050` already provides
the public bundle/extension identity `com.ohos.contacts/ContactUiExtentionAbility`
and real picker pages. Rebuilding its actual `entry` module can replace the
old phone payload that lacks that entrypoint. The provider's existing ordinary
and picker request paths, `pickerData/index/total` chunks, single-selection
`contactObjects/selectContactIds` result, default-selection return and cancel
result 1 remain untouched. The fixed native source also contains an older
`ContactsPickerSelect` targetUrl flow; final API26 caller/provider alignment,
all overloads, malformed filter/selection limits and callback settlement need
joint runtime verification. Source contains an un-cleared setInterval, a global
session reference and display listeners; onSessionDestroy only logs. Source
packaging does not establish that repeated or overlapping sessions exit safely.

Contacts retains the original seven module graph, 38 request permissions and
`com.ohos.security.pickersheet/pickersheetlibrary` external HSP dependency.
The root Hypium dependency is 1.0.16. The external HSP availability and compatible
signature must be checked rather than deleting its declaration. The original
profile is APL `normal` plus `hos_system_app`, with its original ACLs; the root
must preserve that policy while integrating its exact OS signer and preinstall.

Theme revision `a436a43f1c0948fa12df6d520ec695ae4388a057` has two real source
modules: phone-wallpaper (`phone`) and pad-wallpaper (`tablet`). These are
feature modules with wallpaper rendering extensions, not setting UI. The
candidate exposes two GN targets without choosing either in the shared graph.
The root must select at most one target, verify feature-only BMS installation
and actual device compatibility, and keep the `com.ohos.wallpaper` identity.
Theme retains its original runtime-compatible/target 9 while compiling with
API26, and adds dependency-free model6 metadata. Existing Hvigor task files and
legacy package files remain intact. Their compatibility needs an actual official
SDK run; host project-schema validation does not validate module API types.

The expired Theme OS profile retains APL `system_basic` and restricted
GET_WALLPAPER/READ_USER_STORAGE. Renewal is a root task. Native
`base/theme/wallpaper_mgr/services/src/wallpaper_service.cpp` hardcodes
`com.ohos.launcher/WallpaperExtAbility` when ThemeService is absent; the Theme
bundle cannot satisfy that distinct target. Renderer error handling still uses
undefined Log/TAG identifiers and onDestroy does not dispose its created window.
No business/UI behavior is claimed repaired here.

Four host checks pass: full exact apply plus two complete replays; rejection of
unknown, mixed and symlink states before mutation; actual seven-module/dependency,
identity, permission and full API26 project-schema checks; and source assertions
distinguishing real contact selection/results from wallpaper rendering. All
non-target fixture bytes, including module manifests, business source and both
signing profiles, remain identical after applying the candidates. These checks
do not prove HAP execution. All 34 requirements remain unclosed pending the
parent's system-signed representative ARM64 phone package and runtime gate.
