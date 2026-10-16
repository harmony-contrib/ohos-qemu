# Internal callback destructor contract

The current full product compilation found an invalid destructor `override` and
`-Wdelete-non-abstract-non-virtual-dtor` in `NetworkVpnService::VpnConnStateCb`.
The parent's failure log remains unchanged at
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-VPN-Knowledge-communication-platform-03/artifacts/vpn_broker/arm64_virt-networkvpn_service-compile.log`.
The other seven current VPN translation units passed, according to the parent.

The fixed upstream interface is
`foundation/communication/netmanager_ext/services/vpnmanager/include/i_vpn_conn_state_cb.h`,
SHA256 `b22e88f6e637dcc5026aa66741d9d1fe4575de0503cd081fe73e063f70ee5686`.
It declares virtual callback methods and an implicit, non-virtual destructor.
The previous host double incorrectly supplied a virtual interface destructor
and therefore masked this product error. Changing the double to the real
non-virtual destructor contract reproduces both original compiler failures;
the before-fix evidence is `callback-destructor-before-fix-host-20261016.txt`.

The internal derived class now declares its own `virtual ~VpnConnStateCb();`,
without `override`, matching the original upstream derived class's own virtual
destructor intent. The existing destructor body still cancels a pending origin
and wakes waiters. The public/shared interface is untouched. The factory still
uses `std::make_shared<VpnConnStateCb>`; conversion to the controller's
`std::shared_ptr<IVpnConnStateCb>` preserves the concrete control block and its
destruction function. No callback state, queue, account, or permission behavior
changes.

The corrected fixture statically requires a non-virtual base destructor and a
virtual concrete destructor. A new regression holds the actual factory result
only through the base-interface shared pointer, proves the pending origin
remains live while that reference exists, releases it, and requires the actual
derived destructor to cancel the origin and wake a blocked waiter. This case is
included in the deterministic host main, asynchronous serial host main, and
generated native FFRT main. Strict warnings and ASan/UBSan remain enabled.

The callback predecessor's repaired header SHA256 becomes
`bec9f609eee2421a3af247a77a938df1feca3b582a7789d27f974fc102b8cc5a`.
The broker's exact input fixture now contains that complete corrected header;
its final header SHA256 becomes
`318cfc99049ecca78d6dc3c5149255b55449f28ccb4c06cd8be572d13e45096a`.
The broker patch text is unchanged because it modifies other parts of this
header. Both manifests enforce the new raw hashes. Complete predecessor/broker
replay remains idempotent, and the tests explicitly reject and preserve the old
incorrect `override` header rather than accepting it as a partial state.

The full network host suite collects 41 tests: 38 pass and the same three
Linux-only process tests skip on macOS. The parent had already run those Linux
tests successfully on the prior source batch. The repaired native callback
fixture's previous real libffrt run also passed, but this round changes its
interface type contract and adds ownership coverage, so regenerate and verify
the current probe as appropriate. Parent full product recompilation is still
required for the corrected header. All nine capability gaps and the first new
package runtime gate remain open.
