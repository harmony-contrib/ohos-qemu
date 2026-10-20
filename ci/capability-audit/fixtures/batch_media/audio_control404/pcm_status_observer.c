/* SPDX-License-Identifier: Apache-2.0
 * Source-only proposal. Root owns compilation/launch and the inherited parent lease.
 * Queries one already-open HW playback file description. Never opens a PCM device,
 * changes params, STARTs, PREPAREs, RESETs, DROPs, or changes timestamp mode.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <dirent.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <sound/asound.h>
#if !defined(SYS_pidfd_open) || !defined(SYS_pidfd_getfd) || !defined(SYS_kcmp)
#error Actual target syscall headers must provide pidfd_open, pidfd_getfd and kcmp
#endif
/* Linux UAPI KCMP_FILE = 0; no fabricated architecture syscall numbers. */
#define MEDIA375_KCMP_FILE 0

static void fail(const char *what)
{
    fprintf(stderr, "media375 observer failed: %s: %s\n", what, strerror(errno));
    exit(1);
}
static uint64_t number(const char *s, uint64_t max)
{
    char *end = NULL;
    errno = 0;
    if (!s || !*s || *s == '-') { errno = EINVAL; fail("integer"); }
    unsigned long long n = strtoull(s, &end, 10);
    if (errno || !end || *end || n > max) { errno = EINVAL; fail("integer range"); }
    return (uint64_t)n;
}
static uint64_t ns(clockid_t id)
{
    struct timespec t;
    if (clock_gettime(id, &t)) fail("clock_gettime");
    if (t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000L) {
        errno = EINVAL; fail("invalid clock");
    }
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static uint64_t start_ticks(pid_t pid)
{
    char path[80], buf[4096];
    snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
    FILE *f = fopen(path, "r");
    if (!f) fail("open proc stat");
    if (!fgets(buf, sizeof(buf), f)) fail("read proc stat");
    if (fclose(f)) fail("close proc stat");
    char *p = strrchr(buf, ')');
    if (!p || p[1] != ' ') { errno = EINVAL; fail("proc stat comm"); }
    p += 2; /* token 3 (state); starttime is token 22. */
    for (int field = 3; field < 22; ++field) {
        p = strchr(p, ' ');
        if (!p) { errno = EINVAL; fail("short proc stat"); }
        ++p;
    }
    char *end = strchr(p, ' ');
    if (!end) { errno = EINVAL; fail("short proc starttime"); }
    *end = 0;
    return number(p, UINT64_MAX);
}
static void identity(pid_t pid, uint64_t ticks, int target, int borrowed)
{
    if (start_ticks(pid) != ticks) { errno = ESTALE; fail("producer incarnation"); }
    long same = syscall(SYS_kcmp, pid, getpid(), MEDIA375_KCMP_FILE,
                        (unsigned long)target, (unsigned long)borrowed);
    if (same != 0) { if (same > 0) errno = ESTALE; fail("file description identity"); }
}

/* Inventory is a read-only readiness query on an EXISTING holder/OFD. It never
 * opens a PCM pathname and never connects, HELLOs or ARMs the CONTROL socket.
 * A unique pathname is not proof: INFO, pidfd_getfd, kcmp and two stable raw
 * process/namespace/descriptor cuts are mandatory before returning facts. */
#define INVENTORY_SCHEMA "audio404-holder-inventory/v1"
#define INV_RAW 65536
/* The raw replay consumes only these four actual target UAPI fields. Refuse a
 * target layout mismatch at compilation; never decode guessed host offsets. */
_Static_assert(sizeof(unsigned int)==4 && sizeof(int)==4 &&
               offsetof(struct snd_pcm_info, device)==0 &&
               offsetof(struct snd_pcm_info, subdevice)==4 &&
               offsetof(struct snd_pcm_info, stream)==8 &&
               offsetof(struct snd_pcm_info, card)==12, "actual target PCM INFO field layout");
struct inventory_cut {
    char proc_stat[4096], status[16384], fdinfo[16384], unix_table[INV_RAW];
    char link[PATH_MAX], exe[PATH_MAX], boot[80];
    struct stat descriptor, proc_fd, time_ns;
    struct snd_pcm_info info;
    unsigned uids[4], gids[4];
    uint64_t ticks, before_ns, after_ns;
    long kcmp_rc;
};
static void inventory_fail(const char *reason)
{
    int error = errno ? errno : EINVAL;
    printf("{\"kind\":\"inventory_failure\",\"schema\":\"%s\","
           "\"reason\":\"%s\",\"errno\":%d,\"ready\":false}\n",
           INVENTORY_SCHEMA, reason, error);
    fflush(stdout);
    errno = error; fail(reason);
}
static void inventory_read(const char *path, char *out, size_t capacity)
{
    FILE *f = fopen(path, "r");
    if (!f) inventory_fail("readiness_proc_open");
    size_t size = fread(out, 1, capacity - 1, f);
    if (ferror(f)) inventory_fail("readiness_proc_read");
    if (size == capacity - 1 && fgetc(f) != EOF) { errno = EOVERFLOW; inventory_fail("bounded_proc_raw"); }
    if (fclose(f)) inventory_fail("readiness_proc_close");
    if (memchr(out, 0, size)) { errno = EINVAL; inventory_fail("proc_embedded_nul"); }
    out[size] = 0;
}
static void inventory_link(const char *path, char *out, size_t capacity)
{
    ssize_t n = readlink(path, out, capacity - 1);
    if (n < 0 || (size_t)n == capacity - 1) inventory_fail("readiness_fd_or_exe_link");
    out[n] = 0;
}
static void inventory_boot(char out[80])
{
    inventory_read("/proc/sys/kernel/random/boot_id", out, 80);
    out[strcspn(out, "\n")] = 0;
    if (strlen(out) != 36 || strspn(out, "0123456789abcdef-") != 36 ||
        out[8] != '-' || out[13] != '-' || out[18] != '-' || out[23] != '-') {
        errno = EINVAL; inventory_fail("actual_boot_id_shape");
    }
}
static void inventory_json_string(const char *s)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
        else if (*p < 32 || *p >= 127) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}
static void inventory_stat_json(const struct stat *s)
{
    printf("{\"dev\":%" PRIu64 ",\"ino\":%" PRIu64 ",\"rdev\":%" PRIu64
           ",\"mode\":%u,\"uid\":%u,\"gid\":%u,\"nlink\":%" PRIu64 "}",
           (uint64_t)s->st_dev, (uint64_t)s->st_ino, (uint64_t)s->st_rdev,
           (unsigned)s->st_mode, (unsigned)s->st_uid, (unsigned)s->st_gid, (uint64_t)s->st_nlink);
}
static int inventory_same_stat(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_rdev == b->st_rdev &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid && a->st_gid == b->st_gid && a->st_nlink == b->st_nlink;
}
static void inventory_ids(struct inventory_cut *cut)
{
    unsigned found = 0;
    for (const char *p = cut->status; *p;) {
        if (!strncmp(p, "Uid:", 4) && sscanf(p, "Uid: %u %u %u %u", cut->uids, cut->uids+1, cut->uids+2, cut->uids+3) == 4) found |= 1;
        if (!strncmp(p, "Gid:", 4) && sscanf(p, "Gid: %u %u %u %u", cut->gids, cut->gids+1, cut->gids+2, cut->gids+3) == 4) found |= 2;
        const char *next = strchr(p, '\n');
        if (!next) break;
        p = next + 1;
    }
    if (found != 3) { errno = EINVAL; inventory_fail("actual_four_uid_gid_rows"); }
}
static unsigned inventory_listener_count(const char *unix_table, pid_t pid, uint64_t ticks)
{
    char expected[128];
    snprintf(expected, sizeof(expected), "@ohos-audio398/%ld/%" PRIu64, (long)pid, ticks);
    unsigned matches = 0;
    for (const char *p = unix_table; *p;) {
        char line[1024], address[128], tail; unsigned long flags, type;
        const char *end = strchr(p, '\n'); size_t n = end ? (size_t)(end-p) : strlen(p);
        if (n >= sizeof(line)) { errno = EOVERFLOW; inventory_fail("unix_table_line_bound"); }
        memcpy(line, p, n); line[n] = 0;
        if (sscanf(line, "%*s %*s %*s %lx %lx %*s %*s %127s %c", &flags, &type, address, &tail) == 3 &&
            !strcmp(address, expected) && type == 5 && (flags & 0x10000UL)) ++matches;
        if (!end) break;
        p = end + 1;
    }
    return matches;
}
static void inventory_snapshot(pid_t pid, uint64_t ticks, int target, int borrowed, struct inventory_cut *cut)
{
    char path[96]; memset(cut, 0, sizeof(*cut));
    cut->before_ns = ns(CLOCK_MONOTONIC);
    cut->ticks = start_ticks(pid);
    if (cut->ticks != ticks) { errno = ESTALE; inventory_fail("holder_birth_changed"); }
    snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid); inventory_read(path, cut->proc_stat, sizeof(cut->proc_stat));
    snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid); inventory_read(path, cut->status, sizeof(cut->status));
    inventory_ids(cut);
    snprintf(path, sizeof(path), "/proc/%ld/exe", (long)pid); inventory_link(path, cut->exe, sizeof(cut->exe));
    snprintf(path, sizeof(path), "/proc/%ld/fd/%d", (long)pid, target);
    inventory_link(path, cut->link, sizeof(cut->link));
    if (stat(path, &cut->proc_fd) || fstat(borrowed, &cut->descriptor)) inventory_fail("actual_proc_fd_fstat");
    if (!S_ISCHR(cut->descriptor.st_mode) || !inventory_same_stat(&cut->proc_fd, &cut->descriptor)) {
        errno = ESTALE; inventory_fail("original_and_borrowed_descriptor_stat");
    }
    snprintf(path, sizeof(path), "/proc/%ld/fdinfo/%d", (long)pid, target); inventory_read(path, cut->fdinfo, sizeof(cut->fdinfo));
    snprintf(path, sizeof(path), "/proc/%ld/ns/time", (long)pid);
    if (stat(path, &cut->time_ns)) inventory_fail("actual_holder_time_namespace");
    snprintf(path, sizeof(path), "/proc/%ld/net/unix", (long)pid); inventory_read(path, cut->unix_table, sizeof(cut->unix_table));
    if (inventory_listener_count(cut->unix_table, pid, ticks) != 1) {
        errno = EAGAIN; inventory_fail("original_CONTROL_listener_not_ready_or_ambiguous");
    }
    if (ioctl(borrowed, SNDRV_PCM_IOCTL_INFO, &cut->info)) inventory_fail("actual_existing_OFD_PCM_INFO");
    if (cut->info.stream != SNDRV_PCM_STREAM_PLAYBACK || cut->info.card < 0) {
        errno = EINVAL; inventory_fail("existing_OFD_not_HW_playback");
    }
    cut->kcmp_rc = syscall(SYS_kcmp, pid, getpid(), MEDIA375_KCMP_FILE,
                            (unsigned long)target, (unsigned long)borrowed);
    if (cut->kcmp_rc || start_ticks(pid) != ticks) { errno = ESTALE; inventory_fail("same_OFD_and_birth_required"); }
    inventory_boot(cut->boot); cut->after_ns = ns(CLOCK_MONOTONIC);
}
static void inventory_cut_json(const char *kind, pid_t pid, int target, int borrowed, const struct inventory_cut *cut)
{
    printf("{\"kind\":\"%s\",\"pid\":%ld,\"ticks\":%" PRIu64 ",\"fd\":%d,\"borrowed_fd\":%d,"
           "\"before_ns\":%" PRIu64 ",\"after_ns\":%" PRIu64 ",\"kcmp_rc\":%ld,\"uids\":[%u,%u,%u,%u],\"gids\":[%u,%u,%u,%u],",
           kind, (long)pid, cut->ticks, target, borrowed, cut->before_ns, cut->after_ns, cut->kcmp_rc,
           cut->uids[0], cut->uids[1], cut->uids[2], cut->uids[3], cut->gids[0], cut->gids[1], cut->gids[2], cut->gids[3]);
    printf("\"descriptor_stat\":"); inventory_stat_json(&cut->descriptor);
    printf(",\"proc_fd_stat\":"); inventory_stat_json(&cut->proc_fd);
    printf(",\"time_ns_stat\":"); inventory_stat_json(&cut->time_ns);
    printf(",\"pcm_info_bytes\":%zu,\"pcm_info_hex\":\"", sizeof(cut->info));
    const unsigned char *info = (const unsigned char *)&cut->info;
    for (size_t i = 0; i < sizeof(cut->info); ++i) printf("%02x", info[i]);
    printf("\",\"boot\":"); inventory_json_string(cut->boot);
    printf(",\"fd_link\":"); inventory_json_string(cut->link);
    printf(",\"exe\":"); inventory_json_string(cut->exe);
    printf(",\"proc_stat_raw\":"); inventory_json_string(cut->proc_stat);
    printf(",\"proc_status_raw\":"); inventory_json_string(cut->status);
    printf(",\"fdinfo_raw\":"); inventory_json_string(cut->fdinfo);
    printf(",\"proc_net_unix_raw\":"); inventory_json_string(cut->unix_table);
    puts("}"); if (fflush(stdout)) inventory_fail("raw_inventory_flush");
}
static int inventory_main(int argc, char **argv)
{
    if (argc != 4 || getuid() || geteuid() || strlen(argv[2]) != 36 ||
        strlen(argv[3]) != 32 || strspn(argv[3], "0123456789abcdef") != 32) {
        fprintf(stderr, "usage(root): %s --inventory CURRENT_BOOT RUN32\n", argv[0]); return 2;
    }
    char boot[80]; inventory_boot(boot);
    if (strcmp(boot, argv[2])) { errno = ESTALE; inventory_fail("fresh_guest_boot_mismatch"); }
    struct stat own_time;
    if (stat("/proc/self/ns/time", &own_time)) inventory_fail("inventory_time_namespace");
    uint64_t begin = ns(CLOCK_MONOTONIC), producer_ticks = start_ticks(getpid());
    printf("{\"kind\":\"inventory_begin\",\"schema\":\"%s\",\"run\":\"%s\",\"boot\":\"%s\","
           "\"producer_pid\":%ld,\"producer_ticks\":%" PRIu64 ",\"before_ns\":%" PRIu64 ",\"producer_time_ns\":",
           INVENTORY_SCHEMA, argv[3], boot, (long)getpid(), producer_ticks, begin);
    inventory_stat_json(&own_time); puts("}"); fflush(stdout);
    DIR *processes = opendir("/proc"); if (!processes) inventory_fail("proc_inventory_unavailable");
    unsigned process_count = 0, fd_count = 0, candidate_count = 0;
    pid_t selected_pid = 0; int selected_target = -1, selected_borrowed = -1, selected_pidfd = -1;
    struct inventory_cut before, after;
    struct dirent *process;
    for (;;) {
        errno = 0; process = readdir(processes);
        if (!process) { if (errno) inventory_fail("complete_proc_directory_read"); break; }
        if (!*process->d_name || strspn(process->d_name, "0123456789") != strlen(process->d_name)) continue;
        pid_t pid = (pid_t)number(process->d_name, INT_MAX);
        if (pid <= 1 || pid == getpid()) continue;
        if (++process_count > 32768 || ns(CLOCK_MONOTONIC) - begin > UINT64_C(10000000000)) {
            errno = EAGAIN; inventory_fail("bounded_inventory_not_ready");
        }
        char directory[80]; snprintf(directory, sizeof(directory), "/proc/%ld/fd", (long)pid);
        DIR *fds = opendir(directory);
        if (!fds) { if (errno == ENOENT || errno == ESRCH) continue; inventory_fail("incomplete_proc_fd_visibility"); }
        struct dirent *entry;
        for (;;) {
            errno = 0; entry = readdir(fds);
            if (!entry) { if (errno) inventory_fail("complete_fd_directory_read"); break; }
            if (!*entry->d_name || strspn(entry->d_name, "0123456789") != strlen(entry->d_name)) continue;
            if (++fd_count > 262144 || ns(CLOCK_MONOTONIC) - begin > UINT64_C(10000000000)) {
                errno = EAGAIN; inventory_fail("bounded_inventory_not_ready");
            }
            int target = (int)number(entry->d_name, INT_MAX); char path[96], link[PATH_MAX];
            snprintf(path, sizeof(path), "/proc/%ld/fd/%d", (long)pid, target);
            ssize_t n = readlink(path, link, sizeof(link)-1);
            if (n < 0) { if (errno == ENOENT || errno == ESRCH) continue; inventory_fail("incomplete_fd_link_visibility"); }
            if ((size_t)n == sizeof(link)-1) { errno = EOVERFLOW; inventory_fail("fd_link_bound"); }
            link[n] = 0;
            unsigned card, device; int used = 0;
            if (sscanf(link, "/dev/snd/pcmC%uD%up%n", &card, &device, &used) != 2 || !used || link[used]) continue;
            uint64_t ticks = start_ticks(pid);
            /* Only the original CONTROL endpoint's actual current holder is
             * eligible. Unrelated playback devices do not select this owner. */
            char unix_table[INV_RAW];
            snprintf(path, sizeof(path), "/proc/%ld/net/unix", (long)pid);
            inventory_read(path, unix_table, sizeof(unix_table));
            unsigned listeners = inventory_listener_count(unix_table, pid, ticks);
            if (!listeners) continue;
            if (listeners != 1) { errno = EAGAIN; inventory_fail("ambiguous_original_CONTROL_listener"); }
            if (++candidate_count != 1) { errno = EAGAIN; inventory_fail("multiple_existing_CONTROL_playback_PCM_descriptors"); }
            selected_pidfd = (int)syscall(SYS_pidfd_open, pid, 0);
            if (selected_pidfd < 0) inventory_fail("actual_holder_pidfd_open");
            selected_borrowed = (int)syscall(SYS_pidfd_getfd, selected_pidfd, target, 0);
            if (selected_borrowed < 0) inventory_fail("actual_holder_pidfd_getfd_no_PCM_open_fallback");
            inventory_snapshot(pid, ticks, target, selected_borrowed, &before);
            if ((unsigned)before.info.card != card || before.info.device != device) {
                errno = ESTALE; inventory_fail("observed_node_and_PCM_INFO_differ");
            }
            if (strcmp(before.boot, boot) || before.time_ns.st_dev != own_time.st_dev || before.time_ns.st_ino != own_time.st_ino) {
                errno = ESTALE; inventory_fail("same_boot_and_time_namespace_required");
            }
            selected_pid = pid; selected_target = target;
            inventory_cut_json("inventory_before", pid, target, selected_borrowed, &before);
        }
        if (closedir(fds)) inventory_fail("proc_fd_directory_close");
    }
    if (closedir(processes)) inventory_fail("proc_directory_close");
    if (candidate_count != 1) { errno = EAGAIN; inventory_fail("no_existing_original_CONTROL_playback_PCM_descriptor_ready"); }
    inventory_snapshot(selected_pid, before.ticks, selected_target, selected_borrowed, &after);
    if (strcmp(before.boot, after.boot) || strcmp(before.link, after.link) || strcmp(before.exe, after.exe) ||
        memcmp(before.uids, after.uids, sizeof(before.uids)) || memcmp(before.gids, after.gids, sizeof(before.gids)) ||
        !inventory_same_stat(&before.descriptor, &after.descriptor) ||
        before.time_ns.st_dev != after.time_ns.st_dev || before.time_ns.st_ino != after.time_ns.st_ino ||
        memcmp(&before.info, &after.info, sizeof(before.info))) { errno = ESTALE; inventory_fail("holder_OFD_INFO_namespace_not_stable"); }
    inventory_cut_json("inventory_after", selected_pid, selected_target, selected_borrowed, &after);
    int duplicate_close = close(selected_borrowed), pidfd_close = close(selected_pidfd);
    if (duplicate_close || pidfd_close) inventory_fail("actual_inventory_duplicate_close");
    printf("{\"kind\":\"inventory_complete\",\"schema\":\"%s\",\"run\":\"%s\",\"boot\":\"%s\","
           "\"after_ns\":%" PRIu64 ",\"processes\":%u,\"fds\":%u,\"candidates\":%u,"
           "\"duplicate_close_rc\":%d,\"pidfd_close_rc\":%d,\"ready\":true,\"accepted\":false,\"onset_proven\":false}\n",
           INVENTORY_SCHEMA, argv[3], after.boot, ns(CLOCK_MONOTONIC), process_count, fd_count, candidate_count, duplicate_close, pidfd_close);
    if (fflush(stdout)) inventory_fail("inventory_complete_flush");
    return ferror(stdout) ? 1 : 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--inventory")) return inventory_main(argc, argv);
    if (argc != 12) {
        fprintf(stderr, "usage: %s PID START_TICKS FD DEV INO RDEV CARD DEVICE SUBDEVICE RUN32 SAMPLES\n", argv[0]);
        return 2;
    }
    if (getuid() || geteuid()) { errno = EPERM; fail("root launcher required"); }
    pid_t pid = (pid_t)number(argv[1], INT_MAX);
    uint64_t ticks = number(argv[2], UINT64_MAX);
    int target = (int)number(argv[3], INT_MAX);
    uint64_t dev = number(argv[4], UINT64_MAX), ino = number(argv[5], UINT64_MAX);
    uint64_t rdev = number(argv[6], UINT64_MAX);
    int card = (int)number(argv[7], INT_MAX);
    unsigned device = (unsigned)number(argv[8], UINT_MAX);
    unsigned subdevice = (unsigned)number(argv[9], UINT_MAX);
    const char *run = argv[10];
    size_t samples = (size_t)number(argv[11], 7500);
    if (pid <= 1 || ticks == 0 || samples < 2 || strlen(run) != 32 ||
        strspn(run, "0123456789abcdef") != 32) { errno = EINVAL; fail("bounded fresh identity"); }
    char boot[80];
    FILE *bf = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (!bf || !fgets(boot, sizeof(boot), bf)) fail("boot id");
    if (fclose(bf)) fail("close boot id");
    boot[strcspn(boot, "\n")] = 0;
    if (strlen(boot) != 36 || strspn(boot, "0123456789abcdef-") != 36) {
        errno = EINVAL; fail("boot id shape");
    }
    if (start_ticks(pid) != ticks) { errno = ESTALE; fail("initial producer incarnation"); }
    int pfd = (int)syscall(SYS_pidfd_open, pid, 0);
    if (pfd < 0) fail("pidfd_open");
    int fd = (int)syscall(SYS_pidfd_getfd, pfd, target, 0);
    if (fd < 0) fail("pidfd_getfd; no device-open fallback");
    identity(pid, ticks, target, fd);
    struct stat st;
    if (fstat(fd, &st)) fail("fstat borrowed PCM");
    if (!S_ISCHR(st.st_mode) || (uint64_t)st.st_dev != dev ||
        (uint64_t)st.st_ino != ino || (uint64_t)st.st_rdev != rdev) {
        errno = ESTALE; fail("PCM descriptor stat");
    }
    struct snd_pcm_info info;
    memset(&info, 0, sizeof(info));
    if (ioctl(fd, SNDRV_PCM_IOCTL_INFO, &info)) fail("PCM INFO");
    if (info.stream != SNDRV_PCM_STREAM_PLAYBACK || info.card != card ||
        info.device != device || info.subdevice != subdevice) {
        errno = ESTALE; fail("PCM card/device/subdevice");
    }
    int version = 0;
    if (ioctl(fd, SNDRV_PCM_IOCTL_PVERSION, &version)) fail("PCM protocol version");
    const pid_t sampler_pid = getpid();
    const uint64_t sampler_ticks = start_ticks(sampler_pid);
    struct stat sampler_time_ns;
    memset(&sampler_time_ns, 0, sizeof(sampler_time_ns));
    const int sampler_time_ns_rc = stat("/proc/self/ns/time", &sampler_time_ns);
    const int sampler_time_ns_errno = sampler_time_ns_rc ? errno : 0;
    printf("{\"kind\":\"header\",\"schema\":\"media375-hw-sync/v1\",\"run\":\"%s\","
           "\"boot\":\"%s\",\"pid\":%ld,\"ticks\":%" PRIu64 ",\"fd\":%d,"
           "\"dev\":%" PRIu64 ",\"ino\":%" PRIu64 ",\"rdev\":%" PRIu64 ","
           "\"card\":%d,\"device\":%u,\"subdevice\":%u,\"version\":%d,"
           "\"sampler_pid\":%ld,\"sampler_ticks\":%" PRIu64 ",\"borrowed_fd\":%d,"
           "\"time_ns_rc\":%d,\"time_ns_errno\":%d,\"time_ns_dev\":%" PRIu64 ",\"time_ns_ino\":%" PRIu64 "}\n",
           run, boot, (long)pid, ticks, target, dev, ino, rdev, card, device, subdevice, version,
           (long)sampler_pid, sampler_ticks, fd, sampler_time_ns_rc, sampler_time_ns_errno,
           (uint64_t)sampler_time_ns.st_dev, (uint64_t)sampler_time_ns.st_ino);
    for (size_t seq = 0; seq < samples; ++seq) {
        identity(pid, ticks, target, fd);
        struct snd_pcm_sync_ptr status;
        memset(&status, 0, sizeof(status));
        uint64_t before = ns(CLOCK_MONOTONIC);
        status.flags = SNDRV_PCM_SYNC_PTR_HWSYNC | SNDRV_PCM_SYNC_PTR_APPL | SNDRV_PCM_SYNC_PTR_AVAIL_MIN;
        int rc = ioctl(fd, SNDRV_PCM_IOCTL_SYNC_PTR, &status);
        int saved_errno = errno;
        uint64_t real = ns(CLOCK_REALTIME), after = ns(CLOCK_MONOTONIC);
        if (rc) { errno = saved_errno; fail("PCM SYNC_PTR query; no cached fallback"); }
        identity(pid, ticks, target, fd);
        if ((uint64_t)status.c.control.appl_ptr > INT64_MAX ||
            (uint64_t)status.s.status.hw_ptr > INT64_MAX ||
            status.c.control.appl_ptr < status.s.status.hw_ptr) {
            errno = ERANGE; fail("actual PCM pointers outside nonwrapping verifier range");
        }
        printf("{\"kind\":\"sample\",\"seq\":%zu,\"before_ns\":%" PRIu64
               ",\"real_ns\":%" PRIu64 ",\"after_ns\":%" PRIu64
               ",\"state\":%d,\"hw_ptr\":%" PRIu64 ",\"appl_ptr\":%" PRIu64
               ",\"queued_frames\":%" PRId64 ",\"raw_tstamp_sec\":%" PRId64
               ",\"raw_tstamp_nsec\":%" PRId64 "}\n", seq, before, real, after,
               (int)status.s.status.state, (uint64_t)status.s.status.hw_ptr, (uint64_t)status.c.control.appl_ptr,
               (int64_t)status.c.control.appl_ptr - (int64_t)status.s.status.hw_ptr,
               (int64_t)status.s.status.tstamp.tv_sec, (int64_t)status.s.status.tstamp.tv_nsec);
        if (fflush(stdout)) fail("flush sampler evidence");
        struct timespec wait = {0, 8000000L};
        int wait_rc;
        do { wait_rc = nanosleep(&wait, &wait); } while (wait_rc && errno == EINTR);
        if (wait_rc) fail("sample interval wait");
    }
    identity(pid, ticks, target, fd);
    if (close(fd) || close(pfd)) fail("close borrowed descriptors");
    puts("{\"kind\":\"complete\"}");
    return ferror(stdout) ? 1 : 0;
}
