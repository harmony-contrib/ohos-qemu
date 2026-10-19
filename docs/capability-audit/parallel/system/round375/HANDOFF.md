# Calendar round375 first-batch handoff

The component and dedicated host tools are frozen for root integration. No Git staging/commit, SDK/native compilation, signing, Docker, VM/HDC/QMP or source/out writes were performed by this agent. Root must apply the separate builder increment before this native source change becomes active. General Calendar CRUD remains a separate successor task after the first native gate.

Exact upstream targets: `applications/standard/calendardata @ f922427ca0dc20895a0e254ae41382e5b03299a4`, only `calendarmanager/napi/src/calendar_napi.cpp` and `calendarmanager/napi/src/napi_queue.cpp`. All eight native dependencies remain exact whole-file guards; no UI/provider/permission/signing source was changed.

Changes:

- Retain JS-thread native Calendar/EventFilter shared_ptr snapshots for GetEvents; the worker uses no wrapper or filter napi_ref. Propagate both actual GetEvents napi_typeof failures and the shared callback-type failure before using their out-parameters.
- Accept only complete original, complete previous source-only candidate, or complete final native pairs. A previous/final mixture still fails; final guards never accept the older candidate as patched.
- Record publication attempts before replace, including a replacement that published then raised. Verify published bytes. Rollback never overwrites an unknown concurrent edit; failed restoration preserves the transaction and exact predecessor backups for root recovery instead of deleting them.
- Source composition works with current source_provider → event_editor → editor_callback_dispatch → filter → main_ui → calendar_owner, and also filter after the viewer. The current READ-only MainAbility permission scene, shared LocalStorage, full source guards and installed notification owner are retained.

Validation actually performed:

- First isolated batch: 19 tests passed, 3.732s (tool transcript only).
- Final batch after backup-restoration failure coverage: 20 tests passed, exit0, 3.879s. Raw stdout/stderr/argv/SHA are in `H/round375-system/host-validation-final.json`.
- Sealed `r60-source-vector-375-01` actual source composition: exit0, 1.552s. Five actual original NAPI files match the pinned project/revision and component preimages; nine source-only apply/verify/replay steps passed in a private temp fixture. Five remaining native dependencies were fixture-only inputs. Actual evidence was neither changed nor reinterpreted as native acceptance.

These are host model, patch publication and source composition checks. No C++/OHOS engine behavior, product ABI/CFI/LTO/link, SDK build or guest behavior passed here. In particular the environment-hook/async-work shutdown ordering across all 13 NapiQueue callers still needs real engine/native validation; model scheduling is not its proof.

Root integration: `BUILDER-INTEGRATION.diff` declares the component and applies plus require-patched verifies it immediately after editor_callback_dispatch and before current main_ui. It does not replace the existing Calendar stack or widen provider guards. The exact shared builder preimage/candidate postimage SHA is in the private BUILDER-PREIMAGE.json. Agent has not modified the shared builder. Refresh actual build-input pins and source preparation after applying this increment.

Root remaining gate:

1. Compile both real native TUs with actual headers, no relaxed warnings/CFI or copied dummy APIs; check all 13 queue callers and native snapshot/error/callback/env cleanup behavior under the real engine. Root should supply the needed NAPI/Calendar native compile infrastructure and run sanitizer/lifecycle cases.
2. Run the shared source guards against the actual complete prepared CalendarData and notification owner, then the actual source HAP/SDK/signing/profile path.
3. Batch with other known fixes before one new representative package. Boot that exact package and validate normal API/notification/viewer, grant/deny, temporary filter GC, concurrent requests, queue/error/cancel/env destruction, cold/warm/reopen/delete and cleanup. No full lifecycle/reboot or capability closure is claimed; other five packages wait for the first-artifact behavior gate.

CRUD is assessed in CRUD-SUCCESSOR.md. No external provider or secret is needed for this two-TU source repair. Ads OEM/service provider, DeviceAttest real product credentials/trust, and SecurityGuard actual models remain external configuration/implementation dependencies in the broader system11 scope; no fake source or pass result was added for them.
