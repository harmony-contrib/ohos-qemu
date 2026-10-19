# Root-owned peer execution candidates, round 375

This batch implements command construction and ledger production, rather than
declaring a pure protocol fixture resource-ready. The two peer types remain
different: original15 uses a Docker OpenVPN TLS peer; peer_lan stages two actual
QEMU guests on a stream Ethernet link. No Docker, QEMU, HDC, SDK/signing or actual
product source/out operation was performed by this agent. All nine ledger IDs
remain open until sufficient new-package behavior evidence is collected.

## Root command admission and held handles

`ci/capability-audit/batch_network375_root_entry.py` provides `RootExecutor`.
Root must pass actual callbacks, complete environment, literal Python executable
and the exact recorded trampoline descriptor:

```python
owner = RootExecutor(
    fresh_constructor_output,
    admit=live_root_admission,       # raises on denial, returns None on success
    register=register_held_popen,    # returns actual {pid, pgid, uid}
    stop_held=stop_that_held_popen,
    python=literal_python,
    trampoline=actual_trampoline_descriptor,  # path, sha256, bytes
    environment=actual_environment,
)
```

`admit(stage, payload)` must check the same live root lease, both unresolved
markers (including dangling links), current source/tool/daemon/context/environment
and stage-specific complete argv before returning. `before-popen` is a separate
check after durable intent. The root callbacks and default real constructor must
themselves be source-admitted; a synthetic test callback/factory is not evidence
of IO. JSON flags and boolean callback returns are refused.

The producer records intent, blocks INT/TERM, constructs the exact trampoline
argv, registers the still-held Popen, then restores the original signal mask.
Registration failure, pending cancellation at unmask, timeout and unknown
construction preserve evidence and quarantine the instance. Only the actual
held handle is passed to root termination; historical PID/PGID observations never
grant signal authority. Original stdout/stderr are retained as bytes. The root
lease is never acquired, released or declared settled by this helper. Its
`resource_cleanup_verified` and process-group cleanup fields stay false; actual
root final independent cuts are still required.

The exact process query is `/usr/bin/env LC_ALL=C /bin/ps -axo
pid=,ppid=,pgid=,uid=,lstart=`. Before/after descriptor and nine stat fields determine
the one expected EUID, including macOS setuid ps. Registration can observe the
Python trampoline's UID before exec, so the final query UID is only recorded
after the query's own complete census proves its live owner, direct child,
session and EUID. A non-query command has no setuid exception. Aliases, boolean
IDs, changed tools, partial/duplicate rows and omitted owner/query are rejected.

## Original OpenVPN controller integration

`batch_network375_peer_protocol.py` is a source-provenanced successor of frozen
267. Its Docker names/flags, source contract, genuine `verified_built_case` return
shape, complete nine-row immutable build prefix, original runtime suffix,
per-invocation Counter, resource identity and two-cut absence rules remain.
The extensions bind current constructor source and query tools, and require the
complete live owner/query census. It remains a pure verifier: `closed` is
conditional on actual root observations, not permission to release a lease.

`batch_network375_openvpn_peer.py` produces the dedicated constructor ledger from
`RootExecutor`'s actual rows. Root supplies the original raw prefix bytes,
source/config/anchor/binding, the actual actor, and two callbacks:

- `reserve_operation(op)` durably persists the complete operation before returning
  its globally ordered positive sequence. The root guardian must serialize this
  across start/stop actors and native witness/final-query actors.
- `resource_registry(nonce, anchor_id)` returns only IDs derived from this run's
  actual create results and full observed resource identity. A declaration in an
  old state file or a bare supplied CID is insufficient authority.

Within the genuine controlled original15 worker, use
`producer.controller_class(original_controller_class, mode=...)` through that
worker's private controller factory. The wrapper preserves original command and
absence writers, including the cap-ng stop10→actual stop35 transformation. It
intercepts only source-pinned private module globals and restores them in
`finally`; it never replaces global stdlib subprocess. Guardian witness and
final queries use `with producer.operation(origin=..., mode=...)` followed by
`producer.run(actual_argv, timeout=...)`.

Root still owns bootstrap/IPC wiring to the actual original CLI actor, genuine
original15 config/SDK/Linux/backend/Git verification and unchanged TLS/TUN/public
guest verifier. There is no standalone resource CLI or manufactured ready config.
The original root entry/source/preflight must actually execute; a boolean or
re-encoded prefix is refused. Actual constructor source must be the current
root_entry implementation, and Python/trampoline/private Docker environment must
match the binding. Do not edit frozen 267/287/332 packets to wire this in; create
a root-owned successor with the new actual source pins and observations.

## Two-QEMU link and service window

`batch_network_peer_lan.prepare(args, owner=owner)` sends QEMU help through the
same root constructor and requires admission for port probes and disk staging.
It never boots a guest. Standalone `prepare`/`observe` CLI execution is disabled.

Root boots and registers both independent guests under its actual two-VM budget,
then calls:

```python
result = observe(args, owner=owner, exercise=actual_root_service_case)
```

The `peer-existing-guests` admission must bind the plan/archive and both actual
owned VM processes, HDC targets, boot IDs, QMP and independent disks. The helper
first verifies distinct actual UDIDs/boot IDs and both actual NIC MACs; configured
serials/UUIDs alone are never device identity evidence. It configures only the
data NIC, rejects management-NAT routes, and observes ping plus real neighbor MAC.

The optional root `exercise(plan=..., identities=..., owner=..., output=...)`
callback runs while the verified pair's link is live. This is the place for the
actual signed ordinary-caller discovery/authentication, fresh bidirectional
nonce data, permission/revoke, cancellation, peer-offline and session teardown
case. It must return an actual fresh receipt descriptor below the supplied
output, not a success boolean. The helper binds the regular file bytes/hash but
does not reinterpret a child receipt as broad capability closure; root must run
the unchanged independent service verifier.

In `finally`, partial configuration failures and inner-case failures still
restore only the added IPv4 address and changed link flag after fresh identity
checks. A guest identity swap or unknown newly acquired address preserves unknown
state and fails cleanup. The narrowly named `owned_ipv4_and_link_restored` does
not prove neighbor caches, all networking, VM/HDC or process-group cleanup.
Root must settle the full owned resources under the same lease. All first-artifact
gate fields remain false in these scoped helpers.

## Validation and remaining work

The UNIT suites use explicit held-Popen, guest, session and transport doubles plus
tiny host-file launcher fixtures; they execute no real peer. The portable
source-shaped fixture embeds frozen original source bytes only for AST/protocol
checks and does not read or run historical producers. The failed first combined
attempt and all later receipts are preserved under
`.tmp/parallel-capability-20261016/round375-network/`; `result.json` identifies the
final successful source-bound batch.

Required root integration touches the root-owned actor bootstrap, durable
operation reservation/resource registry, current source/stage admission and
two-VM resource allocation. Existing shared owner/policy/creator/stage files,
packager, component patches and validators were read-only in this agent's work.
The original 47-check same-boot/281-ID full gate is not replaced or relaxed.

This batch does not claim support for persist-tun updates, split/encrypted DNS,
nonzero route metrics, Bluetooth alias/local OOB generation or a real controller.
Those need genuine backend/data-flow work; accepting their parameters without
implementing the route/provider would be incorrect. Follow-up component edits
must first receive exact file/upstream-target ownership from root. Real TLS/TUN,
two-device authenticated service data and controller/radio/USB behavior remain
actual first-new-package acceptance tasks, not host-test conclusions.
