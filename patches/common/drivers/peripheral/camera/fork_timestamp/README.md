# QEMU Vivid photo frame timestamp

The USB Camera fork creates a separate output buffer for an ordinary JPEG
photo. The source frame has a timestamp from the real V4L2 dequeue callback,
but the fork did not copy it. The JPEG encoder then sets an encoded size; the
surface publishes the fork buffer's default timestamp of `-1`. The framework
delivers a Photo whose `main.timestamp` is invalid even though JPEG encoding
and the native callback succeeded.

For the QEMU Vivid opt-in only, copy the source frame's existing timestamp to
the fork buffer. Do not invent a clock value at the sink. Non-QEMU USB behavior
is unchanged. Apply after the Camera Vivid/JPEG components. Real acceptance
requires a newly packaged ordinary Camera app to receive two distinct valid
photos across session recreation, with JPEG bytes and pixels checked.
