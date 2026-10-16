# Real capture-only ALSA PCM route

Apply after all existing audio driver patches with `apply.sh --source-root ROOT`.
The manifest preflights five complete fixed predecessor/installed source hashes,
including the explicitly delegated device/qemu vendor_capture.c. Unknown/partial
states fail before writing any target. The review diff is normalized LF; the
installer preserves the exact declared payload bytes. Existing audio 0004–0007
capture hunks still reverse-match, allowing repeat predecessor application.

Optional adapter configuration fields are all-or-none:

    "captureCardId": 1,
    "captureCardName": "QemuCapture",
    "captureDevice": 0

Numbers must be integers in actual ALSA card/device range, with a nonempty bounded
card ID. Explicit selection performs a fresh snd_ctl_card_info and capture-only
snd_ctl_pcm_info query for that exact card, device and subdevice0. Missing card,
wrong ID, missing capture PCM or malformed configuration fails. If all three
fields are absent the original selection is retained. Render continues selecting
the existing flat cardId/cardName (ES1370 card0/AudioPCI in QEMU). Shared enumeration
and selection are mutex protected; explicit capture does not reuse a possibly
render-only enumeration.

The actual QemuCapture ALSA card has a PCM cable and no physical mixer. Both
architecture-specific vendor files perform real prepare/start/drop and propagate
errors. Capture open skips mixer initialization for that actual card ID; volume,
gain and mixer mute report HDF_ERR_NOT_SUPPORT without modifying output values.
A stale read cannot restart a stopped/dropped loopback PCM. Nonblocking read
handles bounded no-data waits and returns failure on exhausted retries, errors,
overreported frames or stopped state, rather than claiming empty success. Actual ALSA
frame bytes also bound the allocated capture buffer; the loopback read path uses a
bounded 100ms wait instead of the legacy ARM indefinite wait/implicit prepare.

Parent integration, owned elsewhere: CONFIG_SND_ALOOP=y, ALSA PCM support, aloop
index=1,id=QemuCapture,pcm_substreams=1; ES1370 remains card0. Verify actual guest
/proc/asound/cards and /proc/asound/pcm before testing. The playback endpoint
hw:CARD=QemuCapture,DEV=1,SUBDEV=0 is wired by the real kernel aloop driver to
capture hw:1,0,0. Do not move primary render to loopback.

Diagnostic `ci/capability-audit/batch_media_alsa_inject.c` is a real guest
libasound producer. Build with the actual target sysroot and libasound, then run:

    batch_media_alsa_inject --input /data/local/tmp/challenge.pcm \
      --rate 48000 --channels 2 --repeat 20 --timeout-ms 30000

The input is externally generated, fresh challenge S16LE PCM, <=16MiB and frame
aligned. The tool verifies exact negotiated parameters, writes every source frame
through ALSA, respects interruption/deadline and fails on xruns/error/short drain.
Its success is not an acceptance oracle. The ordinary public Capturer must record
through AudioService/HDI, then an independent host check must locate the fresh
nonce/channel challenge in persisted captured PCM. Use different channel content
and a synchronization preamble, record timing and rate, reject zero/mismatched
captures, test pause/resume/stop/recreate and permission denial/revocation. Decode
actual Recorder outputs and verify audio/video timing/content separately.

Host tests execute actual JSON/capture/read/open methods and both vendor source
files under ASan/UBSan using controlled ALSA dependencies, plus real pinned cJSON.
They are regression evidence only. Product TU/link, kernel cable, mixer capability
handling by AudioService, HAP reads and new representative package remain required.
