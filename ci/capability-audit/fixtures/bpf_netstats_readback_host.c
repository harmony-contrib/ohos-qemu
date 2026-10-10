/* Actual probe body with a syscall boundary fixture; never guest proof. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <linux/bpf.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static const char *scenario;
static int calls;
static int closes;
static long probe_syscall(long number, ...);
static uid_t probe_geteuid(void);
static int probe_close(int fd);
#define syscall probe_syscall
#define geteuid probe_geteuid
#define close probe_close
#define main probe_main
#include "../probes/bpf_netstats_readback.c"
#undef main
#undef close
#undef geteuid
#undef syscall

static uid_t probe_geteuid(void)
{
    return strcmp(scenario, "unprivileged") == 0 ? 20010000 : 0;
}

static int probe_close(int fd)
{
    assert(fd == 17);
    ++closes;
    if (strcmp(scenario, "close-failure") == 0) { errno = EIO; return -1; }
    return 0;
}

static long probe_syscall(long number, ...)
{
    assert(number == __NR_bpf);
    va_list values;
    va_start(values, number);
    int command = va_arg(values, int);
    union bpf_attr *attr = va_arg(values, union bpf_attr *);
    size_t size = va_arg(values, size_t);
    va_end(values);
    assert(size == sizeof(*attr));
    ++calls;
    if (command == BPF_OBJ_GET) {
        assert(calls == 1 && attr->file_flags == BPF_F_RDONLY);
        assert(strcmp((const char *)(uintptr_t)attr->pathname,
                      "/sys/fs/bpf/netsys/maps/app_uid_stats_map") == 0);
        if (strcmp(scenario, "open-failure") == 0) { errno = ENOENT; return -1; }
        return 17;
    }
    if (command == BPF_OBJ_GET_INFO_BY_FD) {
        assert(calls == 2 && attr->info.bpf_fd == 17);
        assert(attr->info.info_len == sizeof(struct bpf_map_info));
        if (strcmp(scenario, "info-failure") == 0) { errno = EACCES; return -1; }
        struct bpf_map_info *info = (void *)(uintptr_t)attr->info.info;
        info->type = strcmp(scenario, "wrong-type") == 0 ? BPF_MAP_TYPE_ARRAY : BPF_MAP_TYPE_HASH;
        info->key_size = strcmp(scenario, "legacy-key") == 0 ? 4 : 8;
        info->value_size = strcmp(scenario, "wrong-value") == 0 ? 8 : 32;
        info->id = strcmp(scenario, "zero-id") == 0 ? 0 : 42;
        info->max_entries = strcmp(scenario, "zero-capacity") == 0 ? 0 : 5000;
        return 0;
    }
    if (command == BPF_MAP_LOOKUP_ELEM) {
        assert(calls == 3 && attr->map_fd == 17);
        uint64_t key = *(uint64_t *)(uintptr_t)attr->key;
        assert(key == UINT32_MAX || key == 20010000);
        if (strcmp(scenario, "absent") == 0) { errno = ENOENT; return -1; }
        if (strcmp(scenario, "lookup-failure") == 0) { errno = EACCES; return -1; }
        struct counters *value = (void *)(uintptr_t)attr->value;
        *value = (struct counters){1, UINT64_MAX, 3, (UINT64_C(1) << 63) + 5};
        return 0;
    }
    /* A future mutation/attach call must fail the fixture, not be ignored. */
    abort();
}

int main(int argc, char **argv)
{
    assert(argc == 5);
    scenario = argv[1];
    char *arguments[] = {argv[0], argv[2], argv[3], NULL};
    int result = probe_main(3, arguments);
    assert(result == atoi(argv[4]));
    if (result == 2) { assert(calls == 0 && closes == 0); }
    else if (strcmp(scenario, "open-failure") == 0) { assert(calls == 1 && closes == 0); }
    else { assert(closes == 1); }
    return 0;
}
