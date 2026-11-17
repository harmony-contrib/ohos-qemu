/* SPDX-License-Identifier: Apache-2.0
 * Unexecuted source candidate. This is a clock observation, never onset proof.
 * The fixed caller chooses the mode only AFTER original kernel/profile admission.
 * Original PID/birth/credentials/pidfd/OFD/HW sampling and cleanup stay in place.
 * No PCM open, timestamp-mode change, thread, process or resource Owner is added.
 */
#ifndef ONSET579_CLOCK_DOMAIN_H
#define ONSET579_CLOCK_DOMAIN_H
#include <errno.h>
#include <inttypes.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "onset579_kernel_clock_review.h"

enum m579_clock_mode { M579_TIME_NAMESPACE = 1, M579_KERNEL_GLOBAL = 2 };
struct m579_ns_probe {
    int link_rc, link_errno, stat_rc, stat_errno;
    struct stat value;
};
struct m579_clock_cut {
    uint64_t birth, before_ns, after_ns;
    char boot[40];
    struct stat directory, pid_namespace;
    struct m579_ns_probe time, children;
    int pidfd_poll_rc, pidfd_revents;
};
struct m579_clock_observation {
    enum m579_clock_mode mode;
    pid_t pid, observer_pid;
    uint64_t expected_birth;
    int held_pidfd, error;
    struct m579_clock_cut before, after;
};

static uint64_t m579_clock_birth(pid_t pid)
{
    char path[80], raw[4096];
    snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    int ok = fgets(raw, sizeof(raw), f) != NULL;
    int closed = fclose(f);
    if (!ok || closed) return 0;
    char *p = strrchr(raw, ')');
    if (!p || p[1] != ' ') return 0;
    p += 2;
    for (int field = 3; field < 22; ++field) {
        p = strchr(p, ' ');
        if (!p) return 0;
        ++p;
    }
    char *end = NULL;
    errno = 0;
    uint64_t value = strtoull(p, &end, 10);
    return errno || !end || *end != ' ' ? 0 : value;
}
static int m579_clock_boot(char out[40])
{
    FILE *f = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (!f) return errno;
    int ok = fgets(out, 40, f) != NULL;
    int closed = fclose(f);
    if (!ok || closed) return EIO;
    out[strcspn(out, "\n")] = 0;
    if (strlen(out) != 36) return EINVAL;
    for (int k = 0; k < 36; ++k) {
        if ((k == 8 || k == 13 || k == 18 || k == 23) ? out[k] != '-' :
                !strchr("0123456789abcdef", out[k])) return EINVAL;
    }
    return 0;
}
static int m579_clock_mono(uint64_t *out)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return errno ? errno : EIO;
    if (value.tv_sec < 0 || value.tv_nsec < 0 || value.tv_nsec >= 1000000000L) return ERANGE;
    *out = (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
    return 0;
}
static void m579_clock_probe(pid_t pid, const char *name, struct m579_ns_probe *out)
{
    char path[96];
    struct stat link;
    snprintf(path, sizeof(path), "/proc/%ld/ns/%s", (long)pid, name);
    errno = 0;
    out->link_rc = lstat(path, &link);
    out->link_errno = out->link_rc ? errno : 0;
    errno = 0;
    out->stat_rc = stat(path, &out->value);
    out->stat_errno = out->stat_rc ? errno : 0;
}
static int m579_clock_cut(pid_t pid, uint64_t expected_birth, int held_pidfd,
    enum m579_clock_mode mode, struct m579_clock_cut *out)
{
    int error = m579_clock_mono(&out->before_ns);
    if (error) return error;
    error = m579_clock_boot(out->boot);
    if (error) return error;
    out->birth = m579_clock_birth(pid);
    if (!out->birth || out->birth != expected_birth) return ESTALE;
    /* A foreign PID must use the already-held original pidfd. We neither
     * substitute pathname liveness for it nor open/close a second pidfd. */
    if (pid != getpid()) {
        if (held_pidfd < 0) return EBADF;
        struct pollfd p = {held_pidfd, POLLIN, 0};
        out->pidfd_poll_rc = poll(&p, 1, 0);
        out->pidfd_revents = p.revents;
        if (out->pidfd_poll_rc != 0 || out->pidfd_revents != 0) return ESTALE;
    } else if (held_pidfd != -1) {
        return EINVAL;
    }
    char path[80];
    snprintf(path, sizeof(path), "/proc/%ld/ns", (long)pid);
    if (stat(path, &out->directory)) return errno;
    if (!S_ISDIR(out->directory.st_mode) || !out->directory.st_ino) return ENOTDIR;
    snprintf(path, sizeof(path), "/proc/%ld/ns/pid", (long)pid);
    if (stat(path, &out->pid_namespace)) return errno;
    if (!out->pid_namespace.st_ino) return EIO;
    m579_clock_probe(pid, "time", &out->time);
    m579_clock_probe(pid, "time_for_children", &out->children);
    const struct m579_ns_probe *p[2] = {&out->time, &out->children};
    for (int i = 0; i < 2; ++i) {
        if (mode == M579_TIME_NAMESPACE) {
            if (p[i]->link_rc || p[i]->stat_rc || !p[i]->value.st_ino) return EIO;
        } else if (mode == M579_KERNEL_GLOBAL) {
            /* ENOENT is only a recorded consistency check. The original
             * installed-kernel/config/source proof MUST authorize this mode.
             * EACCES/ESRCH/unknown failures never become a global-clock proof. */
            if (p[i]->link_rc != -1 || p[i]->link_errno != ENOENT ||
                    p[i]->stat_rc != -1 || p[i]->stat_errno != ENOENT) return EPROTO;
        } else return EINVAL;
    }
    if (m579_clock_birth(pid) != expected_birth) return ESTALE;
    error = m579_clock_mono(&out->after_ns);
    return error ? error : out->after_ns < out->before_ns ? ERANGE : 0;
}
static int m579_clock_same_stat(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_mode == b->st_mode;
}
static int m579_clock_observe(pid_t pid, uint64_t birth, int held_pidfd,
    enum m579_clock_mode mode, struct m579_clock_observation *out)
{
    memset(out, 0, sizeof(*out));
    out->mode = mode; out->pid = pid; out->observer_pid = getpid();
    out->expected_birth = birth; out->held_pidfd = held_pidfd;
    out->error = pid <= 1 || !birth ? EINVAL :
        m579_clock_cut(pid, birth, held_pidfd, mode, &out->before);
    if (!out->error) out->error = m579_clock_cut(pid, birth, held_pidfd, mode, &out->after);
    if (!out->error && (strcmp(out->before.boot, out->after.boot) ||
            out->before.after_ns > out->after.before_ns ||
            !m579_clock_same_stat(&out->before.directory, &out->after.directory) ||
            !m579_clock_same_stat(&out->before.pid_namespace, &out->after.pid_namespace) ||
            (mode == M579_TIME_NAMESPACE &&
                (!m579_clock_same_stat(&out->before.time.value, &out->after.time.value) ||
                 !m579_clock_same_stat(&out->before.children.value, &out->after.children.value)))))
        out->error = ESTALE;
    return out->error;
}
static void m579_clock_stat_json(FILE *f, const struct stat *s)
{
    fprintf(f, "{\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"mode\":%u}",
        (uint64_t)s->st_dev, (uint64_t)s->st_ino, (unsigned)s->st_mode);
}
static void m579_clock_probe_json(FILE *f, const struct m579_ns_probe *p)
{
    fprintf(f, "{\"link_rc\":%d,\"link_errno\":%d,\"stat_rc\":%d,\"stat_errno\":%d,\"stat\":",
        p->link_rc, p->link_errno, p->stat_rc, p->stat_errno);
    if (!p->stat_rc && p->value.st_ino) m579_clock_stat_json(f, &p->value);
    else fputs("null", f);
    fputc('}', f);
}
static void m579_clock_cut_json(FILE *f, const struct m579_clock_cut *c)
{
    fprintf(f, "{\"birth\":%"PRIu64",\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64
        ",\"boot\":\"%s\",\"pidfd_poll_rc\":%d,\"pidfd_revents\":%d,\"directory\":",
        c->birth, c->before_ns, c->after_ns, c->boot, c->pidfd_poll_rc, c->pidfd_revents);
    m579_clock_stat_json(f, &c->directory); fputs(",\"pid_namespace\":", f);
    m579_clock_stat_json(f, &c->pid_namespace); fputs(",\"time\":", f);
    m579_clock_probe_json(f, &c->time); fputs(",\"time_for_children\":", f);
    m579_clock_probe_json(f, &c->children); fputc('}', f);
}
static int m579_clock_json(FILE *f, const char *run, const char *role,
    const struct m579_clock_observation *o)
{
    /* Role/run are the caller's finite source constants/current nonce, not
     * externally selectable paths. Reject JSON control characters anyway. */
    if (strlen(run) != 32 || strspn(run, "0123456789abcdef") != 32 ||
            !*role || strlen(role) > 48 || strspn(role, "abcdefghijklmnopqrstuvwxyz_") != strlen(role)) return EINVAL;
    fprintf(f, "{\"schema\":\"onset579-clock-domain/v1\",\"kind\":\"clock_domain579\",\"run\":\"%s\","
        "\"role\":\"%s\",\"mode\":\"%s\",\"pid\":%ld,\"expected_birth\":%"PRIu64
        ",\"observer_pid\":%ld,\"held_pidfd\":%d,\"error\":%d,\"before\":",
        run, role, o->mode == M579_TIME_NAMESPACE ? "time_namespace" :
            o->mode == M579_KERNEL_GLOBAL ? "kernel_global_monotonic" : "invalid",
        (long)o->pid, o->expected_birth, (long)o->observer_pid, o->held_pidfd, o->error);
    m579_clock_cut_json(f, &o->before); fputs(",\"after\":", f);
    m579_clock_cut_json(f, &o->after); fputs("}\n", f);
    return ferror(f) ? EIO : 0;
}

/* NON-RT only. All native role/identity proofs remain actual observations. */
static int m579_global_clock_observe(pid_t pid, uint64_t birth, int held_pidfd,
    struct m579_clock_observation *out)
{
    int error = m579_clock_observe(pid, birth, held_pidfd, M579_KERNEL_GLOBAL, out);
    int review = m579_global_clock_review_gate();
    if (!error && review) out->error = error = review;
    return error;
}
static int m579_global_clock_pair(const struct m579_clock_observation *a,
    const struct m579_clock_observation *b)
{
    if (a->mode != M579_KERNEL_GLOBAL || b->mode != M579_KERNEL_GLOBAL || a->error || b->error ||
        strcmp(a->after.boot,b->after.boot) ||
        !m579_clock_same_stat(&a->after.pid_namespace,&b->after.pid_namespace)) return ESTALE;
    return 0;
}
static int m579_clock_buffer(char *out,size_t capacity,const char *run,const char *role,
    const struct m579_clock_observation *observation)
{
    char *raw = NULL;size_t length = 0;
    FILE *stream = open_memstream(&raw,&length);
    if (!stream) return errno ? errno : EIO;
    int error = m579_clock_json(stream,run,role,observation);
    if (fclose(stream) && !error) error = EIO;
    if (!error && (!length || raw[length-1] != '\n' || length >= capacity)) error = EOVERFLOW;
    if (!error) {memcpy(out,raw,length-1);out[length-1] = 0;}
    free(raw);return error;
}
#endif
