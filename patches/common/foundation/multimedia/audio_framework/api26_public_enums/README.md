# API26 audio public enum contracts

Register AudioDevcieSelectStrategy (the SDK's exact spelling),
SpatialAudioSourceType and VolumeFlag from existing native definitions.
Do not export the internal stream-select value or change native audio state,
permissions, spatial DSP, volume UI or routing. Propagate every new NAPI
registration failure from module initialization.

Export/compile fixtures are not archive or backend acceptance.
