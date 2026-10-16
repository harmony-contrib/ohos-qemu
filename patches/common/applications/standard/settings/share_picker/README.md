# Real modal share picker candidate in the existing Settings HAP

Fixed Settings project 0aba461c750fda71977c2f5186ca0e756ecfc6ca. Five exact
upstream targets add a real sysPicker/share UIExtension to the current phone
module and page graph, without new permissions, profiles or a fabricated bundle.
The original Settings GET_BUNDLE_INFO permission is already declared. All
unknown/partial file states fail before component mutation; replay is tested.

startAbilityByType('share', WantParams, callback) is resolved by the real AMS
SetPickerElementNameAndParams query for sysPicker/share. This candidate provides
SharePickerExtensionAbility in com.ohos.settings. It does not implement the
separate legacy ACTION_CHOOSE route, whose system parameters still name absent
com.ohos.sharepickerdialog/PickerDialog. Do not alias that UIAbility route to this
UIExtension or report the configured bundle as now installed.

The view queries actual enabled/exported UIAbility sendData targets matching
MIME/URI, resolves readable labels, waits for an explicit user choice, then
requeries the original action/MIME/URI before selecting the exact component.
A stale, disabled or no-longer-matching target does not launch. Empty/denied
queries remain an honest empty/error view with Cancel. There is no fixed target,
forced recipient, auto-send or receiveData callback that can authorize a launch.

Supported flat WantParams are type (MIME), uri, ability.params.stream and
ability.subject. Text streams may be one string or a single plain-text array;
file streams are a bounded array of file URIs and must agree with any top URI.
An empty payload can open the picker and cancel, but cannot launch a target.
Malformed URI, MIME, count and text are rejected. The actual ohos.uri parser
validates URI syntax. Files require the incoming Want's READ flag, populated by
StartAbilityByType from ability.want.params.uriPermissionFlag. Only READ is
forwarded, even if the caller requested WRITE as well.

Dispatch uses UIExtensionContentSession.startAbilityAsCaller. The pinned native
implementation uses sessionInfo->callerToken; AMS overwrites reserved identity
from the native caller record; SceneBoard and AbilityRecord use that caller token
for URI grants. The controller never reads/copies files or calls a grant API
with Settings' authority, and never forwards caller-provided reserved identity,
account, component or launch-option parameters. Real caller-owned/unauthorized
URI behavior and caller exit still require packaged-image verification.

ResultCode0/outcome=launched means the native start call actually succeeded;
it does not assert that the receiver sent, saved or consumed the content.
ResultCode1/outcome=cancelled starts nothing. After a successful launch and
failed return, retry returns the same outcome without a second launch or a false
cancellation. Constructor errors return401; page-load failures return16000050.
Each content session owns its own controller/storage and immediate destroy token;
late queries, revalidation, launches and errors do not report to a dead session.

Stable UI IDs: system-share-title, -error, -empty, -refresh, -cancel and
system-share-target-<bundle/module/ability>. Cancellation remains available while
a target-list query is pending; a chosen launch/result operation is serialized.

No SDK build was run for this batch. Main owns exact Settings final guard,
component ordering, system signing/preinstall, unique picker registration, and
new ARM64 phone UI/permission/lifetime validation. This is a phone source
candidate, not proof for the 2in1 module or remaining packages. Native
ShareExtension/Bluetooth HMS data protocols and legacy ACTION_CHOOSE remain
separate unclosed dependencies.
