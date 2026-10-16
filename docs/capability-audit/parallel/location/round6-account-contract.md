# Fusion owner account contract repair

Base: `94d765b83b6c06058f32b67c9ad5637fa8e139af`. Parent finished its actual
regenerated-IPC/full-platform batch: 14 of 15 full translation units passed;
`locator_ability.cpp` alone failed because a const AppIdentity was passed to
`CommonUtils::IsAppBelongCurrentAccount(AppIdentity&)`. Parent also confirmed
both new GNSS translation units passed. The original compilation failure is
preserved in the parent evidence path recorded by `round6-freeze-inputs.json`.

The sixth incremental patch changes only the already owned
`base/location/location/services/location_locator/locator/source/locator_ability.cpp`.
`FusionOwnerAvailable` keeps its const registered owner and copies it to an owned
local value for the legacy mutable-reference helper. Shared utility interfaces
and implementations are unchanged; no driver or new upstream target is added.
The cumulative target count stays 73 (location27 + communication42 + RTT4).

The actual fixed helper was examined, including its full call chain:
`IsAppBelongCurrentAccount` obtains active accounts,
`IsAppBelongActiveAccounts` reads UID/bundle/token, and `CheckAppForUsers` resolves
the OS account from UID and compares it to active account IDs. These functions
only read the identity; the system-SA allowance is preserved. AppIdentity has
its ordinary member copy, preserving UID, PID, token, extended/delegated token
and bundle. The copy does not change which owner/account is evaluated and the
registered object remains unchanged.

The previous host boundary used a const-friendly template, which masked the
real platform declaration. The fusion fixture now freezes the exact declarations
from the fixed `common_utils.h` and actual three source functions. The host test
executes that account call chain with explicit OS-account/system-SA boundaries.
Icon helper declarations are also corrected to mutable AppIdentity references.
The pre-fix fusion owner function is compiled against the real declaration and
must fail with its const mismatch. The patched evaluator executes under
ASan/UBSan, including active/inactive account checks and an unchanged registered
identity assertion. Existing provider/permission/account/death/expiry/queue cases
remain in the full regression. These host tests do not replace the complete
platform translation unit or packaged-runtime gates.

The strict whole-source guard now accepts original, complete prefixes1..5, and
final bytes at the same fixed project HEAD. Original raw hashes, six real patch
applications, and every complete state are checked on all 27 location targets.
The integrating parent owns the next actual locator TU/module verification and
all new representative package/runtime work. No compilation result here closes
behavior gaps: all 22 assigned requirements remain open, with 0 closures.
