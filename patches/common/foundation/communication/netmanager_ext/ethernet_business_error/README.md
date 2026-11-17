# Numeric synchronous Ethernet BusinessError

Fresh R39 normal-app validation got the correct denied code as the string
"202", while the SDK requires a number. Use the existing native business-error
helper for this one synchronous entrypoint. Preserve error mapping/message,
service calls, permissions, signatures and the positive boolean return.

Requires the exact earlier Ethernet API26 prepared source. Both device
profiles/all ABIs apply this component before GN/traversal. New-package normal
and denied-system errors plus authorized real interface control remain required.
