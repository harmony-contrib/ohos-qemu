# Source-built AdminProvisioning

Pinned project: applications/standard/admin_provisioning at
352a226f5c969a14be6f711fb41c8d02fddce2d7. Exact original/final states cover
all 15 files. The patch retains original CRLF hunk bytes and original missing
final-newline markers; the helper must not normalize them a second time.
Unknown/partial source and redirected input fail before mutation.

The real Stage project now builds as a release ohos_app with official API26,
its existing signature/adminprovisioning.p7b, same bundle/install directory,
normal APL, ACLs, names and requested permissions. All three original real
abilities survive, including ByodAdminProvisionAbility from legacy module.json
with START_PROVISIONING_MESSAGE. Obsolete srcEntrance/type=ui become their
current Stage fields/sys/commonUI while retaining visibility and permission.
Hvigor6 scripts use their real appTasks/hapTasks, with no unused old remote
build-tool/hypium production dependencies. Root package.json is retained but
modern OHPM resolves the new exact no-dependency oh-package manifests.

The normal-administrator page snapshots its own Want and enterprise data,
awaits current state, blocks unsupported/super changes and duplicate operations,
executes real enableAdmin/disableAdmin, then queries actual backend state before
closing. Cancel performs no management write. A replacement singleton Want or
page destruction during async work cannot retarget the old operation or close
the replacement page. A backend commit already explicitly authorized by the
user may complete after exit, but it does not report into a replaced page.
MainAbility uses actual loadContent and handles onNewWant; parsed per-page
state is no longer a module global shared between requests.

The existing auto-deploy UIExtension keeps its request/result protocol. It
validates the actual config before loading its UI, allocates per-session
LocalStorage, rejects missing/unsupported config with ENABLE_ADMIN_FAILED,
and cancels session work on destroy. The deploy page waits for real activation
and state confirmation, preserves original result codes (100 next,101 previous,
102 failure), prevents duplicate operations/results and avoids results after
page destruction. Delivery retry queries the actual state rather than activating
again. The existing auto-manager page explicitly rejects an absent Want.

Official API26 Release unsigned HAP compilation succeeded after all known errors
were collected and fixed per compiler pass. All four attempt inputs/logs and
hashes are in docs/capability-audit/parallel/apps/admin-provider-sdk-20261016.json.
Existing deprecation and private-input component warnings are preserved for
real UI acceptance. Host regressions execute actual extracted methods and do
not substitute for system signing, native EDM/backend availability, BMS
registration, caller permission refusal or new ARM64 phone package operation.

Main integration must apply this component and the separate hap/admin_provider
component, bind the unchanged profile's exact platform leaf to preinstall
policy, and grant only its existing declared ACL permissions. Do not expand APL
or permissions to make a caller pass. The provider gap remains open until the
representative newly packaged image completes its real UI/lifecycle cases.
