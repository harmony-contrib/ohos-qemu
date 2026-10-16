# Native client no-op callback warning fix

Fixed project `8c41289750820fb2ddb347b1205cee9a7b527388`, after `always_on_vpn`.
Apply with `apply.sh --source-root OPENHARMONY_ROOT`; the only upstream target is
`interfaces/innerkits/netvpnclient/include/networkvpn_client.h`.

The real supervisor/TUN build's `-Wall -Wextra -Werror` exposed five unused
parameter names in two pre-existing empty `VpnSetUpEventCallback` overrides.
Omit those names while preserving their exact parameter types, virtual
signatures, ABI, callback bodies and return values. No warning flag changes.
The always-on guard accepts only this exact separately checked header successor
inside its otherwise complete known source states.

`test_batch_network_vpn_client_warnings.py` compiles the actual original class
and confirms the same unused-parameter error, then compiles/runs the actual
repaired class under ASan/UBSan and `-Wall -Wextra -Werror`, with compile-time
signature assertions. It replays the complete ancestor/callback/warning stack
and verifies unknown source rejection. Parent must repeat real product helper
TU compilation/linking as helpers02; the host test does not replace that build
or the first new package runtime gate. No audit requirement closes here.
