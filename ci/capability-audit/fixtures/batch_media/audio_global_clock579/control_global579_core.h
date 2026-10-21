/* SPDX-License-Identifier: Apache-2.0
 * Native CONTROL state validation only. No audio/onset acceptance is implied. */
#ifndef CONTROL404_CORE_H
#define CONTROL404_CORE_H
#include "media598_wire.h"
#include <errno.h>
#include <limits.h>
#include <stddef.h>
#include <string.h>
_Static_assert(offsetof(struct m398_request, magic)==24 && offsetof(struct m398_request, boot)==40 &&
    offsetof(struct m398_request, run)==80, "real request ABI");
_Static_assert(offsetof(struct m398_ack, error)==40 && offsetof(struct m398_ack, magic)==52 &&
    offsetof(struct m398_ack, failed)==60, "real ACK ABI");
struct c404_state { uint64_t ticks, epoch, instance; int pid, fd, stage; };
static int c404_hex(const char *s, size_t n)
{
    if(!s || strlen(s)!=n)return EINVAL;
    for(size_t i=0;i<n;++i)if(!strchr("0123456789abcdef",s[i]))return EINVAL;
    return 0;
}
static int c404_boot(const char *s)
{
    if(!s || strlen(s)!=36)return EINVAL;
    for(unsigned i=0;i<36;++i)if((i==8 || i==13 || i==18 || i==23)?s[i]!='-':!strchr("0123456789abcdef",s[i]))return EINVAL;
    return 0;
}
static int c404_ack(struct c404_state *s, const struct m398_ack *a, unsigned op)
{
    if(a->magic!=M398_MAGIC || a->error || a->failed || a->holder_pid!=s->pid ||
        a->holder_ticks!=s->ticks || a->hw_fd!=s->fd || !a->instance ||
        a->rows>M398_ROWS_MAX || a->tap_bytes>M398_TAP_MAX)return EPROTO;
    if(op==M398_HELLO) {
        if(s->stage || a->state || a->epoch>=M398_RUN_MAX)return ESTALE;
        s->epoch=a->epoch+1;s->instance=a->instance;s->stage=1;return 0;
    }
    if(a->epoch!=s->epoch || a->instance!=s->instance)return ESTALE;
    if(op==M398_ARM) {
        if(s->stage!=1 || a->state!=1 || a->rows || a->tap_bytes)return ESTALE;
        s->stage=2;return 0;
    }
    if(op==M398_DISARM) {
        if(s->stage!=2 || a->state)return ESTALE;
        s->stage=3;return 0;
    }
    return EPROTO;
}
#endif
