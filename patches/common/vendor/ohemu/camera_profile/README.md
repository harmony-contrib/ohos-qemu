# Camera board inheritance

Move only the known product-local `v4l2_emulator=false` part into shared board
inheritance. Product-local entries replace whole inherited parts, so otherwise
they erase the phone USB VDI/config pair. Preserve the existing board USB=false
default and all other components; the phone contract alone selects USB=true and
its actual matching host config. 2in1's Camera.Core exclusion is unchanged.

Unknown Camera entries, duplicates or source symlinks fail before patching.
This changes configuration, not device existence, frames, application permission
or Camera runtime acceptance. It is excluded from the frozen R6 first package.
