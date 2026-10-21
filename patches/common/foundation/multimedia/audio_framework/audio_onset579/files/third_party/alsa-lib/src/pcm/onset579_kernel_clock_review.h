/* SPDX-License-Identifier: Apache-2.0
 * Fixed OH7 implementation review: kernel14c77f1541a53e814d89ad6dea5f7f211f9895a6.
 * The normal source guard verifies all9 actual source hashes before GN/native
 * production. This permits observation only, not any config/package/boot claim.
 * Every actual ARM32 package still needs its generated config, matching kernel
 * and held boot proof plus exact ENOENT/proc/pidfd/OFD/HW raw replay.
 */
#ifndef ONSET579_KERNEL_CLOCK_REVIEW_H
#define ONSET579_KERNEL_CLOCK_REVIEW_H
#if !defined(__arm__) || defined(__aarch64__)
#error The explicit global579 variant is limited to the actual ARM32 target
#endif
static int m579_global_clock_review_gate(void)
{
    /* No environment/build macro authorizes a different implementation. */
    return 0;
}
#endif
