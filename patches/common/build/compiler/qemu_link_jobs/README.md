The outer Ninja job count and concurrent_links=1 do not bound the original
hardcoded 16 ThinLTO backends. The running representative attempt has retained
its original settings. Its actual ld.lld process reached the 14 GiB container
limit and used over 12 GiB of swap, without an OOM kill.

This whole-source delta adds qemu_link_jobs. Zero keeps the original non-QEMU
16-backend flags and default LLD worker behavior. The QEMU build explicitly
sets two workers for the LTO backend and LLD internal pool. LTO, CFI, target ABI,
optimization, image features and concurrent_links remain enabled as before.
The alternative gold path receives the same selected backend budget.

The component rejects unknown source bytes and stages its one-file patch
before atomic replacement. It has not been applied, compiled or tested here.
Only the next actual newly packaged QEMU image can provide runtime acceptance.
