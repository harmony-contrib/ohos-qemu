# Always-on VPN policy

Pinned netmanager_ext revision: `8c41289750820fb2ddb347b1205cee9a7b527388`.
Requires `netmanager_base/optional_settings_read` before compilation.

The two SDK-declared Promise APIs call the real NetworkVpnClient and the
permission-checked NetworkVpnService. New IPC methods are appended after the
existing methods. The service preserves system-caller and MANAGE_VPN checks;
there is no client-supplied identity or permission bypass.

The policy setter uses the existing SettingsData provider and activation path,
checks persisted readback, and releases the policy mutex before activation.
The getter distinguishes an absent setting from a provider/query failure.
Missing providers must reject, not report a fabricated disabled/success state.
Each request owns its async work through completion or cancellation. Business
errors carry numeric codes; invalid arguments do not submit IPC work.
Before publishing a Promise, a strongly referenced internal BusinessError is
reserved. If constructing a later error fails, completion clears a pending
engine exception or uses that reserve rather than leaving the Promise pending.
The reference is released on setup failure, completion, and cancellation.

Apply with `bash apply.sh --source-root <root>`. Both pristine and already
patched states are checked byte-for-byte. Existing system-VPN and dialog
patches remain required; this component does not provide a VPN server.

Validation is staged: actual patched host boundary tests, regenerated real
product IPC and translation-unit compilation for three ABIs, then newly
packaged guest tests. Host compilation does **not** close either public API
or VPN behavior in the capability ledger. Guest acceptance must include
system-authorized persistence/readback/restoration, ordinary-app and
system-without-permission denial, malformed arguments, process restart and
existing VPN configuration/connection regression.
