/* SPDX-License-Identifier: Apache-2.0
 * Read-only actual kernel BPF inventory. No load/update/attach/detach syscall.
 * Program/map IDs and cgroup attachments are observations, not acceptance.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/vfs.h>
#include <time.h>
#include <unistd.h>

static const char *run_id, *boot_id;
static unsigned long seq;
static unsigned total_keys;
static size_t total_value_bytes;
static int failures;
static long call(enum bpf_cmd command, union bpf_attr *attr) {
    errno = 0;
    return syscall(__NR_bpf, command, attr, sizeof(*attr));
}
static uint64_t pointer(const void *value) { return (uint64_t)(uintptr_t)value; }
static void prefix(const char *kind) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) _exit(111);
    printf("{\"schema\":\"networking579-bpf-raw/v1\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
        "\"seq\":%lu,\"pid\":%ld,\"uid\":%ld,\"mono_ns\":%llu,\"kind\":\"%s\"",
        run_id, boot_id, seq++, (long)getpid(), (long)getuid(),
        (unsigned long long)now.tv_sec * 1000000000ULL + now.tv_nsec, kind);
}
static void hex(const void *data, size_t size) {
    const unsigned char *p = data;
    for (size_t i = 0; i < size; ++i) printf("%02x", p[i]);
}
static void error(const char *operation, unsigned id, int code) {
    ++failures; prefix("error");
    printf(",\"operation\":\"%s\",\"id\":%u,\"errno\":%d}\n", operation, id, code);
}
static unsigned cpus(void) {
    FILE *f = fopen("/sys/devices/system/cpu/possible", "r");
    char line[8192]; unsigned result = 0;
    if (!f) return 0;
    if (!fgets(line, sizeof(line), f) || !strchr(line, '\n')) { fclose(f); return 0; }
    fclose(f);
    char *cursor = line;
    while (*cursor && *cursor != '\n') {
        char *end; errno = 0; unsigned long first = strtoul(cursor, &end, 10), last = first;
        if (errno || end == cursor || first > 8191) return 0;
        cursor = end;
        if (*cursor == '-') {
            last = strtoul(cursor + 1, &end, 10);
            if (errno || end == cursor + 1 || last < first || last > 8191) return 0;
            cursor = end;
        }
        if (result != first) return 0;
        result = (unsigned)last + 1;
        if (*cursor == ',') ++cursor;
        else if (*cursor != '\n' && *cursor) return 0;
    }
    return result;
}
static void map_values(int fd, const struct bpf_map_info *info) {
    int per_cpu = info->type == BPF_MAP_TYPE_PERCPU_HASH || info->type == BPF_MAP_TYPE_PERCPU_ARRAY ||
        info->type == BPF_MAP_TYPE_LRU_PERCPU_HASH;
    if (info->type != BPF_MAP_TYPE_HASH && info->type != BPF_MAP_TYPE_ARRAY && info->type != BPF_MAP_TYPE_LRU_HASH && !per_cpu) {
        prefix("map-opaque"); printf(",\"id\":%u,\"type\":%u}\n", info->id, info->type); return;
    }
    unsigned possible = per_cpu ? cpus() : 1;
    size_t bytes = per_cpu ? ((info->value_size + 7UL) & ~7UL) * possible : info->value_size;
    if (!possible || !info->key_size || info->key_size > 256 || !bytes || bytes > 1024*1024 || info->max_entries > 65536) {
        error("map-bounds", info->id, EOVERFLOW); return;
    }
    unsigned char *key = calloc(1, info->key_size), *next = calloc(1, info->key_size), *value = calloc(1, bytes);
    if (!key || !next || !value) { free(key); free(next); free(value); error("allocate", info->id, ENOMEM); return; }
    int first = 1; unsigned count = 0;
    while (count <= info->max_entries) {
        union bpf_attr a = {0}; a.map_fd = fd; a.key = first ? 0 : pointer(key); a.next_key = pointer(next);
        if (call(BPF_MAP_GET_NEXT_KEY, &a)) {
            if (errno != ENOENT) error("map-next-key", info->id, errno);
            break;
        }
        if (count++ == info->max_entries) { error("map-churn-or-overflow", info->id, EOVERFLOW); break; }
        if (++total_keys > 4096 || total_value_bytes + info->key_size + bytes > 16*1024*1024) {
            error("whole-inventory-bounds", info->id, EOVERFLOW); break;
        }
        total_value_bytes += info->key_size + bytes;
        memcpy(key, next, info->key_size); first = 0;
        a = (union bpf_attr){0}; a.map_fd = fd; a.key = pointer(key); a.value = pointer(value);
        long result = call(BPF_MAP_LOOKUP_ELEM, &a); int actual_errno = errno;
        prefix("map-value"); printf(",\"id\":%u,\"key_hex\":\"", info->id); hex(key, info->key_size);
        printf("\",\"lookup_result\":%ld,\"errno\":%d,\"cpu_count\":%u,\"value_hex\":\"", result, actual_errno, possible);
        if (result == 0) hex(value, bytes);
        printf("\"}\n");
        /* Deletion during a live map scan is recorded, never filled with zero. */
        if (result && actual_errno != ENOENT) ++failures;
    }
    prefix("map-values-end"); printf(",\"id\":%u,\"observed_keys\":%u,\"atomic\":false}\n", info->id, count);
    free(value); free(next); free(key);
}
static void maps(void) {
    unsigned id = 0, count = 0;
    for (;;) {
        union bpf_attr a = {0}; a.start_id = id;
        if (call(BPF_MAP_GET_NEXT_ID, &a)) { if (errno != ENOENT) error("map-next-id", id, errno); break; }
        if (a.next_id <= id || ++count > 256) { error("map-id-bounds", id, EOVERFLOW); break; }
        id = a.next_id; a = (union bpf_attr){0}; a.map_id = id;
        int fd = (int)call(BPF_MAP_GET_FD_BY_ID, &a);
        if (fd < 0) { error("map-fd", id, errno); continue; }
        struct bpf_map_info info = {0}; a = (union bpf_attr){0}; a.info.bpf_fd = fd; a.info.info_len = sizeof(info); a.info.info = pointer(&info);
        if (call(BPF_OBJ_GET_INFO_BY_FD, &a)) error("map-info", id, errno);
        else {
            prefix("map"); printf(",\"id\":%u,\"type\":%u,\"key_size\":%u,\"value_size\":%u,\"max_entries\":%u,\"flags\":%u,\"name_hex\":\"",
                info.id, info.type, info.key_size, info.value_size, info.max_entries, info.map_flags);
            hex(info.name, sizeof(info.name)); printf("\"}\n"); map_values(fd, &info);
        }
        if (close(fd)) error("map-close", id, errno);
    }
    prefix("maps-end"); printf(",\"observed_maps\":%u}\n", count);
}
static void programs(void) {
    unsigned id = 0, count = 0;
    for (;;) {
        union bpf_attr a = {0}; a.start_id = id;
        if (call(BPF_PROG_GET_NEXT_ID, &a)) { if (errno != ENOENT) error("program-next-id", id, errno); break; }
        if (a.next_id <= id || ++count > 256) { error("program-id-bounds", id, EOVERFLOW); break; }
        id = a.next_id; a = (union bpf_attr){0}; a.prog_id = id;
        int fd = (int)call(BPF_PROG_GET_FD_BY_ID, &a);
        if (fd < 0) { error("program-fd", id, errno); continue; }
        uint32_t ids[256] = {0}; struct bpf_prog_info info = {0}; info.nr_map_ids = 256; info.map_ids = pointer(ids);
        a = (union bpf_attr){0}; a.info.bpf_fd = fd; a.info.info_len = sizeof(info); a.info.info = pointer(&info);
        if (call(BPF_OBJ_GET_INFO_BY_FD, &a)) error("program-info", id, errno);
        else if (info.nr_map_ids > 256) error("program-map-count", id, EOVERFLOW);
        else {
            prefix("program"); printf(",\"id\":%u,\"type\":%u,\"created_by_uid\":%u,\"name_hex\":\"", info.id, info.type, info.created_by_uid);
            hex(info.name, sizeof(info.name)); printf("\",\"tag_hex\":\""); hex(info.tag, sizeof(info.tag));
            printf("\",\"map_ids\":["); for (unsigned i = 0; i < info.nr_map_ids; ++i) printf("%s%u", i ? "," : "", ids[i]);
            printf("]}\n");
        }
        if (close(fd)) error("program-close", id, errno);
    }
    prefix("programs-end"); printf(",\"observed_programs\":%u}\n", count);
}
static void pinned(const char *path, int program) {
    union bpf_attr a = {0}; a.pathname = pointer(path); a.file_flags = program ? 0 : BPF_F_RDONLY;
    int fd = (int)call(BPF_OBJ_GET, &a);
    if (fd < 0) { error("pinned-object-get", 0, errno); return; }
    struct bpf_map_info map = {0}; struct bpf_prog_info prog = {0};
    a = (union bpf_attr){0}; a.info.bpf_fd = fd;
    a.info.info_len = program ? sizeof(prog) : sizeof(map);
    a.info.info = pointer(program ? (void *)&prog : (void *)&map);
    if (call(BPF_OBJ_GET_INFO_BY_FD, &a)) error("pinned-object-info", 0, errno);
    else { prefix(program ? "pinned-program" : "pinned-map");
        printf(",\"path\":\"%s\",\"id\":%u}\n", path, program ? prog.id : map.id); }
    if (close(fd)) error("pinned-object-close", 0, errno);
}
static void attachments(const char *path) {
    int fd = open(path, O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (fd < 0) { prefix("cgroup-open"); printf(",\"path\":\"%s\",\"result\":-1,\"errno\":%d}\n", path, errno); return; }
    struct stat s; if (fstat(fd, &s)) { error("cgroup-stat", 0, errno); close(fd); return; }
    struct statfs fs;
    if (fstatfs(fd, &fs)) { error("cgroup-statfs", 0, errno); close(fd); return; }
    prefix("cgroup-kind"); printf(",\"path\":\"%s\",\"filesystem_type\":%llu}\n", path, (unsigned long long)fs.f_type);
    if ((unsigned long)fs.f_type != 0x63677270UL) { close(fd); return; }
    const enum bpf_attach_type types[] = {BPF_CGROUP_INET_INGRESS, BPF_CGROUP_INET_EGRESS, BPF_CGROUP_INET_SOCK_CREATE,
        BPF_CGROUP_INET4_CONNECT, BPF_CGROUP_INET6_CONNECT};
    for (unsigned i = 0; i < sizeof(types)/sizeof(types[0]); ++i) {
        uint32_t ids[256] = {0}; union bpf_attr a = {0}; a.query.target_fd = fd; a.query.attach_type = types[i];
        a.query.query_flags = BPF_F_QUERY_EFFECTIVE; a.query.prog_cnt = 256; a.query.prog_ids = pointer(ids);
        long result = call(BPF_PROG_QUERY, &a); int code = errno;
        prefix("attachment"); printf(",\"path\":\"%s\",\"dev\":%llu,\"ino\":%llu,\"attach_type\":%u,\"result\":%ld,\"errno\":%d,\"effective\":true,\"program_ids\":[",
            path, (unsigned long long)s.st_dev, (unsigned long long)s.st_ino, types[i], result, code);
        if (result == 0 && a.query.prog_cnt <= 256) for (unsigned j = 0; j < a.query.prog_cnt; ++j) printf("%s%u", j ? "," : "", ids[j]);
        printf("]}\n");
        if (result || a.query.prog_cnt > 256) ++failures;
    }
    if (close(fd)) error("cgroup-close", 0, errno);
}
int main(int argc, char **argv) {
    if (argc != 3 || strlen(argv[1]) != 32 || strlen(argv[2]) != 36) return 2;
    for (size_t i = 0; i < 32; ++i) if (!((argv[1][i] >= 'a' && argv[1][i] <= 'f') || (argv[1][i] >= '0' && argv[1][i] <= '9'))) return 2;
    char actual[64] = {0}; int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY|O_CLOEXEC);
    if (fd < 0) return 3; ssize_t n = read(fd, actual, sizeof(actual)-1); close(fd);
    if (n != 37 || actual[36] != '\n' || memcmp(actual, argv[2], 36)) return 3;
    run_id = argv[1]; boot_id = argv[2]; prefix("begin"); printf(",\"readonly\":true}\n");
    if (getuid() != 0 || geteuid() != 0) { error("root-required", 0, EPERM); }
    else {
        maps(); programs();
        pinned("/sys/fs/bpf/netsys/maps/app_uid_stats_map", 0);
        pinned("/sys/fs/bpf/netsys/maps/app_uid_access_policy_map", 0);
        pinned("/sys/fs/bpf/netsys/progs/cgroup_skb_uid_ingress", 1);
        pinned("/sys/fs/bpf/netsys/progs/cgroup_skb_uid_egress", 1);
        attachments("/sys/fs/cgroup"); attachments("/dev/cg2_bpf");
    }
    prefix("end"); printf(",\"errors\":%d,\"readonly\":true}\n", failures); fflush(stdout);
    return failures ? 1 : 0;
}
