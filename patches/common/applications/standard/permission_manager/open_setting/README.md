# Manual permission settings UI

The pinned AccessToken client launches
`com.ohos.permissionmanager.OpenSettingAbility`, not PermissionStateSheetAbility.
This component installs a separate `sys/commonUI` entry/page and implements the
single `ohos.open.setting.permission` / `ohos.open.setting.result_code` protocol.
The old array-result user_grant dialog remains unchanged.

Only the pinned release's four PC/tablet manual_settings permissions are handled.
Caller UID/token/bundle injected by AbilityManager must agree with the real BMS
record in that account, and the permission must be declared. Display never
grants a permission. The Allow action revalidates the request, calls the real
`grantPermission` API and verifies the resulting AccessToken state. Cancel/back
does not grant/revoke. Already-granted returns 1; unsupported/undeclared return
3/2; internal failures return -2, never the success-default 0.

The window is parented/modal and hides non-system floating windows; failure to
create/load it is an error, not an unparented grant-dialog fallback. Lifecycle
cleanup invalidates the request and restores floating-window visibility.

This is a source candidate. Host model tests and ArkTS compilation do not prove
the PC/2in1 UI, real permission changes or denial boundaries. New packaged guest
validation is still required; phone manual-settings permissions are not enabled.
