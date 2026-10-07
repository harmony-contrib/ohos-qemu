# Fixed-source CalendarData provider

Build `CalendarData.hap` from `applications/standard/calendardata` at the fixed
7.0 manifest, rather than the unrelated phone/PC prebuilt HAP. The native part
and provider therefore use the same source revision. Keep the five real local
HAR dependencies, lower/whole-calendar permissions, token checks, proxy scopes,
and reminder service authorization unchanged.

API 26 requires model 6. The standard OHOS build already maps this model to its
6.x Hvigor and Node 18.20.1. The IDE signing config points at a missing project
keystore; compile unsigned and let the standard GN app_sign target use the
existing `Calendardata.p7b` OS-integration/system-core profile and platform key.
The separate vendor component pins its matching certificate fingerprint; it
does not disable signature checking or add ACLs.

The production provider does not import Hypium. Drop this test-only registry
dependency from this QEMU build project, keeping all five runtime HARs local;
the normal HAP build must not depend on a registry download of an unused test
runner. Runtime acceptance uses the separate capability/bindings test HAPs,
not the upstream ohosTest target.

Both QEMU profiles use this ArkTS 1.1 source HAP. It contains no native ELF
libraries, but API/bytecode compatibility and provider behavior must still be
tested in each newly packaged architecture/profile. Compile-only results do
not satisfy the first-package gate.

Keep the fixed source's `default`/`tablet` module device types. Forcing a
`phone`/`2in1` pair produced an empty SysCap intersection in the real Linux
SDK, and is not a valid build fix. QEMU's already explicit
`const.bms.supportAppTypes=2in1,phone,default,tablet` compatibility profile is
required; actual BMS activation on both profiles remains runtime validation.

This restores the candidate whole-calendar and reminder provider inputs only.
The Stage HAP is assembled by Hvigor, including its resources and five local
HARs. Do not add `ohos_resources`/`ohos_js_assets` to this app's dependencies:
that routes Stage `module.json5` through the legacy resource compiler, which
requires an FA `distro` object and fails in the actual full image build.
`EditorUIExtensionAbility` remains missing, and calendar UI/reminder lifecycle,
CRUD/ownership, denied permissions, cancellation and restart behavior are not
declared repaired until real guest tests pass.
