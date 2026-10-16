# Native communication contracts after full-TU diagnostics

The complete batch04 evidence contains11 passing and6 failing object rows. Its
three AccessToken include failures were repaired by the GN dependency patch;
batch05 passes those three consumers plus the generated wrapper, with explicit
selected-only coverage. The other three batch04 failures must remain open until
compiled again.

Patch3 marks all14 actual proxy callbacks as overrides of the current broker.
Adding the new callback with `override` exposed13 old missing specifiers through
`-Winconsistent-missing-override`; no diagnostic is disabled and no signature,
virtual ordering or IPC transaction changes. The service now explicitly includes
`ipc_skeleton.h` for its real identity checks. Both are existing owned targets.

The host test compiles both complete actual broker/proxy class declarations,
using doubles only for platform boundary types. With `-Werror` and the real
missing-override warning enabled, the previous prefix independently fails and
the final declaration passes. The producer/NAPI boundary regressions also pass.
The complete44 raw files pass actual original → prefix1 → prefix2 → final byte
checks, including the original binary enum/CRLF bytes; all legal-state forward
applications and rejected unknown/mixed/HEAD/symlink/patch cases pass.

Next actual units are `telephony_observer_proxy__tel_state_registry_api`,
`telephony_observer_proxy__tel_state_registry` and
`telephony_state_registry_service__tel_state_registry`. Failed batch04 proxy
objects cannot be reused. The first full Rust attempt correctly reaches the
linker and fails against the old product API library's missing new virtual
method; its evidence is preserved. A private API solink with current successful
objects and a complete Rust dylib link remain separate required gates.

No new package/runtime proof or behavior closure is claimed. All22 location and
communication requirements still await the parent's new representative package.
Exact hashes, test results and requested units are in the adjacent JSON report.
