# QEMU AV panel product wiring

The selected official MediaController HAP uses com.hmos.mediacontroller,
UIExtAbility and sys/commonUI. Adapt the public NAPI request to that actual
provider, preserve Back cancellation and use its real state notifications.
Each modal generation owns its events; delayed old callbacks cannot mutate a
newer generation and a terminal close cannot emit twice. Queued NAPI events
recheck their generation and registered callback reference.

Also repair AVVolumePanel cleanup to use its actual element-id parameter.
All three sources are staged and atomically replaced with guarded rollback.
This component neither activates the provider nor proves any UI behavior.
The shared root preinstall component owns activation and exact signer policy;
the newly packaged QEMU must prove panels, consumers, cancellation and cleanup.
