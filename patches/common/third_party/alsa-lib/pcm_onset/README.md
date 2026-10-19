# QEMU PCM presentation observation source component

This component installs the fixed ALSA443 diagnostic sources and a target-local
GN switch. It does not prove a presentation timestamp, a paired haptic event,
a completed runtime trial, or the first-artifact gate.

`alsa_lib_pcm_onset_diagnostic_enable` is declared **false** upstream. Only
`ohos_shared_library("libasound")` gets `MEDIA398_ONSET_DIAGNOSTIC=1` when it is
true. Its false branch introduces no target-local `defines`; the shared
`alsa_lib_config`, `libalsa_midi`, warnings, ABI and source selections are
unchanged. Because the C sources use `#ifdef`, never substitute a macro value
of zero for an undefined macro. Existing product permissions, init, socket and
CONTROL/WRITEI protocol rules are preserved in the exact ALSA443 payloads.

The QEMU build adapter uses `QEMU_PCM_ONSET_COMPONENT=1` by default. `0` and `1`
are the only accepted values. On `1`, the patch plan applies this component and
the actual load/build argv includes:

```text
--gn-args alsa_lib_pcm_onset_diagnostic_enable=true
```

On `0`, the original complete source tuple produces no new GN argument, since
that GN file has no declaration. An already complete patched tuple produces an
explicit `alsa_lib_pcm_onset_diagnostic_enable=false`, replacing any earlier
true value in reused build arguments. Unknown or mixed tuples are rejected in
both modes; textual detection of a declaration is insufficient.

The fixed source identities and sizes are in `source_states.json` and repeated
as constants in `apply.py`. Four files change: `BUILD.gn`, `src/pcm/pcm_hw.c`,
and the two initially absent `media398_*.h` files. `src/pcm/pcm_local.h` is an
unchanged, exact-hash guard. `files/` must contain exactly the four registered
payloads. Unknown bytes, missing required originals, unexpected new-header
bytes, symlinks, and nonregular files at any managed target are refused before
source mutation. Other ALSA source files are outside this finite component.

From this component directory, with the prepared source root supplied by the
resource owner:

```sh
bash apply.sh --source-root /path/to/openharmony
bash apply.sh --source-root /path/to/openharmony --require-patched
bash apply.sh --source-root /path/to/openharmony --gn-arg 1
```

`--check` and `--gn-arg 0|1` are read-only. A normal apply validates all payloads
and the complete original tuple, holds its private component flock, stages all
outputs, rechecks the original tuple, then replaces files. A completed second
application leaves file identities, mtimes and modes unchanged. Interrupted
mixed states are rejected; the component never guesses how to repair them.
The lock is not a build-resource lease and does not authorize using a shared
source tree. Only the root scheduler may run the actual patch/build cycle.

`0001-libasound-target-local-gn.patch` is a reviewable diff for the new GN hunk;
the installation entry uses fixed payload bytes, without invoking Git or GN.
The product C/header payloads are the exact reviewed443 successor, including
the paired fork prepare/parent guard. Source and host-file checks are separate
from target compilation and DSO/image evidence. ARM32 and x86 target TUs/DSOs,
new-image runtime, holder/permission admission, all onset joins and the complete
first representative artifact gate remain pending.
