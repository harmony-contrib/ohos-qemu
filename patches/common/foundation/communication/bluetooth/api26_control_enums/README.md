# API26 Bluetooth control enum contracts

Register ControlObject, ControlType and ControlTypeValue directly from the
existing native Bluetooth protocol constants. Preserve all control-method,
pairing, service and permission checks. Every new NAPI registration error
fails module initialization. This does not provide a radio, peer, OOB pairing
or successful Bluetooth state transition.

Compile/export checks are not actual controller or new-package acceptance.
