Read-only review of root commit `20b37a9` found the Contacts CLI, stable boot
path and independent `verify_evidence` dispatch consistent with the wrapper.
The stable copy stays beside the real qemu.log; root wake adds top-level power
cycle evidence without changing the core test_environment. The family adapter
compares that environment with the enclosing VM and calls the fixed verifier.
The 13 frozen root host tests passed. They use constructed metadata and mocks,
and do not demonstrate runtime behavior.

One definite integration defect was reported to root: the nested
`capability_health` accepts missing, null, empty-object or empty-string
cleanup_errors when cleanup_complete is true. The actual function was
extracted with Python AST and exercised directly; see root20b-review.json.
The independent family verifier correctly requires cleanup_errors exactly [].
Root owns the shared fix so the failed-child reuse decision also requires the
strict list contract.

The registry closes only the original phone Contacts picker entrypoint ID
after independent Contacts raw verification, and the original Wallpaper
provider ID after full independent Wallpaper verification. `external-inputs`
returns no original closure IDs. It cannot close the broad
msdp-device-status-mock-or-missing-clients finding, whose missing clients and
other modalities remain outside the public still/GNSS/accelerometer subset.
No host green result in this review closes any ledger item.

Root's real helpers-recheck-02 report was also consumed read-only by the actual
integrated Contacts `verify_observer` function. The source SHA
941c352d94079170d495147de4e5373012a357712b81dc2627532b576ec5a3c6,
ELF SHA 7cb824ab95e9323c0794ea47a9386ea6d3ecfa267eb97c18269992edf6799e99,
and recheck report SHA
3d66772f46116d8e07a40826e29d698e0fde0ffc0e1bcc0795d6c309037667f2
match. The two explicit original path mappings were used. The original failed
01 report remains unchanged; no compiler, signer or guest was run.

The authorized wrapper fix adds `--full-boundaries`. First-package root must
pass this fixed flag and require both full_boundaries_requested and the
independently returned full_boundaries_verified. The real driver receives
deadline and navigation-dismiss cases; the strict raw verifier rejects missing
boundary results, shortened deadline timestamps, wrong Home/cancel actions and
missing provider closure. Diagnostic mode remains available but does not
represent complete boundary acceptance. Caller ETS, product NAPI and its
600000ms native timeout are unchanged.

The original Wallpaper finding also contains the !theme_service fallback
target failure, so a renderer PID alone is insufficient. Media confirmed its
actual Settings entry, PhotoPicker, Apply/Cancel/Back/Restore, two random public
desktop challenges and independent pixels/resources. There is currently no
actual guest raw connection sample in this task; the source-derived parser
tests are explicitly synthetic.

The new independent helper interface is:

```python
batch_apps_wallpaper_connection.verify_runtime_connections(
    runtime_path,
    target=actual_enclosing_target,
    user_id=100,
    module_name='phone_wallpaper',
)
```

It reads the frozen media runtime schema without changing it. For both
desktop-1 and desktop-2, it binds the AMS, pidof and renderer BMS raw files to
the actual command label, guest target, exact shell script, GuestUi successful
remote exit marker and output bytes. It requires exactly one genuine
ExtensionRecords SERVICE record with the exact module URI, bundle and
WallpaperExtAbility, valid Connections count and an actual CONNECTED entry.
It cross-checks the BMS system application UID for user100 with a unique
AppRunningRecords renderer PID/UID and pidof result. Plain PID, a normal
same-name PAGE/UIEXTENSION, another module/user/UID/PID, duplicate service or
process record, disconnected state and invented output are rejected.

Fixed framework source confirms this grammar; source-dump-contract.json binds
the actual files and excerpts. Importantly, BaseExtensionRecord only prints
PID/root-host information for UI extensions. A wallpaper SERVICE record has
neither direct service-token→PID nor connection-caller identity. The helper
therefore returns both observation claims false, and leaves GN selection false.
The unique same-user process is a cross-check, not an invented token mapping.
The enclosing image verifier must independently prove the actual HAP has its
single wallpaper extension, excluding an ordinary same-named service.

Root separately owns qemu_wallpaper_build_witness.py and the actual package's
wallpaper-native/inventory.json. The minimum source/build proof is selected GN
theme_service=false (not merely the wallpaper.gni default, which global parts
can override), the real target graph/commands selecting QEMU_WALLPAPER_RENDERER
and no THEME_SERVICE, both service/connection actual objects on the real link
edge, and this build's source/objects/linked/unstripped/staged DSO plus the
identical extracted system.img library. The exact actual target is
//base/theme/wallpaper_mgr/services:wallpaper_service; output is
theme/wallpaper_mgr/libwallpaper_service.z.so. The helper does not accept a
diagnostic TU with forced defines as product proof, nor infer ThemeService
absence from a BMS bundle list. Root combines the real build/image proof with
natural service startup (no manual start/connect), the two public challenges,
and these genuine AMS connection observations before closing the full ID.

An existing native AbilityManagerClient GetExtensionRunningInfos route exists
in the source and could separately observe extension running identity, but no
new native observer or build is introduced in this batch. Full source/header
and product ABI review would be necessary before using that additional API.

All 34 apps IDs and 53 cumulative upstream target paths remain unchanged.
The first artifact is still pending actual package/boot/UI validation; no
remaining five-package matrix is authorized by this review or these host tests.
