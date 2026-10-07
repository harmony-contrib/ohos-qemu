# AVC EOS buffer and error propagation

The pinned software wrapper reuses output buffers. Its EOS branch sets only
the flag, leaving stale memory size/PTS, and ignores the backend's return code.
Reset size/PTS from the actual backend result only after success. Report an
actual backend failure through OnError and retain ERROR rather than claiming
EOS completion. No source outside these exact changes is overwritten.

This shared component is applied before software-backend packaging for both
profiles/all native ABIs. The source guard accepts only pristine fixed HEAD
or this exact patch. Compile and new-package callback/packet/EOS tests remain
required; source inspection or a flag alone is not media API acceptance.
