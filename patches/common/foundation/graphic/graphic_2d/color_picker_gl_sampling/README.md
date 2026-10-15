# Color picker on the QEMU GL renderer

The fixed Release fallback only schedules work through Vulkan semaphores.
QEMU's GL render context now samples its actual surface snapshot with the
existing bounded-scale, pixel-readback and average-color implementation, then
uses the existing manager callback. It preserves regions, thresholds, sampling
intervals, the Vulkan path and listener ownership. No declared background color
or canned luminance is substituted for rendered pixels.

RuntimeShaderBuilder bindings are mutable. Keep the immutable RuntimeEffect
cached and construct a local builder so parallel render threads cannot replace
each other's image shader. Apply before GN/traversal for both device profiles.
The new package still requires real black/white callbacks and unsubscribe tests.
