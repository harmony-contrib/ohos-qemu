# Real ALSA capture input

Enable the built-in Linux ALSA loopback driver in all three QEMU kernels. Keep
ES1370 at card 0 for playback and select card 1 (`QemuCapture`), capture device 0
explicitly in the HDI adapter configuration. The matching PCM producer writes
to `hw:CARD=QemuCapture,DEV=1,SUBDEV=0`; this is the loopback driver's opposite
device, not ES1370's playback PCM.

The packager adds `snd-ens1370.index=0 snd-aloop.index=1
snd-aloop.id=QemuCapture snd-aloop.pcm_substreams=1` to every supported launcher.
Linux module parameters accept hyphens and underscores equivalently. Fixed card
indices reserve the existing playback route and make capture selection fail
truthfully if its real card or PCM is absent.

The installer checks both pinned source revisions and all four inputs before
writing. It accepts only disabled/enabled loopback selections with real built-in
ALSA/PCI/ES1370 dependencies; all unrelated kernel selections remain untouched.
The vendor JSON accepts only the exact original or complete final bytes. A
failed publication rolls back earlier writes.

This source configuration is not runtime evidence. Acceptance must confirm the
newly packaged kernel, actual `/proc/asound` identity/PCM nodes, a challenged PCM
producer through AudioCapturer/HDI, independent sample correlation, restart and
permission boundaries, and recorder output. Silence or a playback node alone
does not satisfy capture.
