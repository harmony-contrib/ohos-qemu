# QEMU 2in1 public input Settings navigation

The pinned native Settings route table silently returns without opening the
public input settings/detail APIs on `2in1`. QEMU packages the same real source
Settings provider and installed input method in both profiles. Admit only the
two existing input routes for `2in1`; keep the actual device identity, all other
device route boundaries, parameter validation, permissions, IME identity checks
and session handling unchanged.

Requires the source Settings and `external_input` components. A host routing
test or the ARM64 phone run is not evidence of successful 2in1 presentation;
each 2in1 archive must pass the ordinary-app Settings runtime gate.
