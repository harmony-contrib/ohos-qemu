# ALSA accepted-byte prefix repair

This fixed source component repairs the community primary → ALSA adapter normal
WRITE path. `snd_pcm_writei` positive frame returns advance only the accepted
prefix. EAGAIN exhaustion and zero progress no longer imply a full packet write.
Every no-progress recovery path has a finite budget, including repeated EPIPE or
ESTRPIPE with successful recovery. Only the unaccepted tail is submitted again.

The existing `AlsaRender.Write` vtable, shared const `AudioOutputRenderWrite`
declaration/function, other commands, vendor overrides, mmap and presentation
functions retain their original interfaces. A private helper and private WRITE
dispatch carry `writeAcceptedBytes` and a confirmed `writeRetryable` result in a
tail extension of the existing internal parameter. Both adapter and primary
must be rebuilt from the matching header; this is not binary compatibility with
an old adapter. The non-ALSA public function body is preserved.

The generated HDI stub/proxy serialize replyBytes only on success. Accordingly:

- A valid positive accepted prefix returns public success with that exact count,
  including a partial prefix followed by a backend error. Raw backend errors are
  retained by the existing primary error logging path.
- Confirmed retryable zero (EAGAIN exhaustion or zero write progress) returns
  public success/zero. The sink retains the packet and may retry on another tick.
- Fatal zero returns public error/zero. No public status is a byte count.
- An absent, oversized or unaligned internal response returns error/zero and
  poisons the real primary render instance under its existing mutex. Subsequent
  calls cannot reach the backend. Only Release and a newly allocated instance
  clear this uncertainty; Stop/Flush do not clear it.

The caller must initialize its output count before invoking the generated proxy.
Any front-end error may represent failed RPC/marshalling after acceptance; it is
not proof of zero acceptance. The matching sink fix must stop replaying this
backend epoch until it releases and recreates the backend/node. This component
alone cannot make transport failure lossless or establish the sink policy.

Run this component **after** both the existing numbered QEMU audio component and
capture_loopback `--require-patched`. Its five managed paths are disjoint from
both components. The captured soundcard header is the capture component's exact
final state, so applying this component earlier intentionally fails preflight.
The parent must add the call after capture verification in
`apply_qemu_audio_component`; this candidate does not edit the shared builder.

```sh
bash patches/common/drivers/peripheral/audio/accepted_write/apply.sh \
  --source-root /path/to/openharmony
bash patches/common/drivers/peripheral/audio/accepted_write/apply.sh \
  --source-root /path/to/openharmony --require-patched
```

The pinned manifest accepts only the complete five-file before or complete final
vector plus eight exact read-only prerequisites. Partial states, drift, aliases
and hardlinks fail before writes. Repeat application of the complete final
vector is a no-op. It uses exact byte hunks, retains line endings and file modes,
and does not use the old generic patch marker as evidence of source state.

Source-only host evidence: 40 extracted C boundary cases and 10 actual generated
stub/proxy branch models passed ASan/UBSan; 12 exact component/source-state groups
passed. Transport failure quarantine in those models is a caller policy model,
not execution of the separate sink fix or real IPC. Target compilation, final
DSO/route binding, package/guest validation, software-to-source attribution,
same-OFD HW crossing, onset and the original 47 checks remain pending. Positive
ALSA acceptance does not prove eventual playback, especially across recovery.
