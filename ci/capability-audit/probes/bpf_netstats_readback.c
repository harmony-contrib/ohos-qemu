/* SPDX-License-Identifier: Apache-2.0
 * Read-only observation of the pinned NetManager UID map, never policy writes.
 * Missing UID is reported separately from a present zero counter. This probe
 * alone proves neither traffic accounting nor public API authorization.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static const char map_path[] = "/sys/fs/bpf/netsys/maps/app_uid_stats_map";
struct counters {
    uint64_t rx_packets;
    uint64_t rx_bytes;
    uint64_t tx_packets;
    uint64_t tx_bytes;
};
_Static_assert(sizeof(struct counters) == 32, "fixed release NetManager map value ABI");

int main(int argc, char **argv)
{
    if (argc != 3 || strlen(argv[1]) != 32 || strspn(argv[1], "0123456789abcdef") != 32 ||
        argv[2][0] == '\0' || strlen(argv[2]) > 10 ||
        strspn(argv[2], "0123456789") != strlen(argv[2])) {
        fprintf(stderr, "usage: bpf-netstats-readback RUN_ID_32HEX UID_DECIMAL\n");
        return 2;
    }
    errno = 0;
    char *end = NULL;
    uint64_t uid = strtoull(argv[2], &end, 10);
    if (errno || *end != '\0' || uid > UINT32_MAX || geteuid() != 0) {
        fprintf(stderr, "requires an actual root diagnostic caller and uint32 UID\n");
        return 2;
    }
    union bpf_attr attr = {0};
    attr.pathname = (uint64_t)(uintptr_t)map_path;
    attr.file_flags = BPF_F_RDONLY;
    int descriptor = (int)syscall(__NR_bpf, BPF_OBJ_GET, &attr, sizeof(attr));
    if (descriptor < 0) {
        perror("open actual pinned NetManager map read-only");
        return 1;
    }
    int status = 1;
    struct bpf_map_info info = {0};
    memset(&attr, 0, sizeof(attr));
    attr.info.bpf_fd = (uint32_t)descriptor;
    attr.info.info_len = sizeof(info);
    attr.info.info = (uint64_t)(uintptr_t)&info;
    if (syscall(__NR_bpf, BPF_OBJ_GET_INFO_BY_FD, &attr, sizeof(attr)) != 0) {
        perror("read actual map ABI");
        goto finished;
    }
    /* The pinned release service uses a uint64 key, unlike the independent
     * legacy bpf/bpf_progs/netstats.c uint32 map. Do not silently read either.
     */
    if (info.type != BPF_MAP_TYPE_HASH || info.key_size != sizeof(uid) ||
        info.value_size != sizeof(struct counters) || info.id == 0 || info.max_entries == 0) {
        fprintf(stderr, "unexpected NetManager map ABI: type=%u key=%u value=%u id=%u entries=%u\n",
                info.type, info.key_size, info.value_size, info.id, info.max_entries);
        goto finished;
    }
    struct counters value = {0};
    memset(&attr, 0, sizeof(attr));
    attr.map_fd = (uint32_t)descriptor;
    attr.key = (uint64_t)(uintptr_t)&uid;
    attr.value = (uint64_t)(uintptr_t)&value;
    int found = (int)syscall(__NR_bpf, BPF_MAP_LOOKUP_ELEM, &attr, sizeof(attr));
    int present = found == 0;
    if (found != 0 && errno != ENOENT) {
        perror("read actual UID counters");
        goto finished;
    }
    /* Decimal strings preserve every uint64 bit in JSON/JavaScript consumers. */
    if (printf("{\"run_id\":\"%s\",\"caller_uid\":0,\"uid\":%" PRIu64
               ",\"map_id\":%u,\"key_bytes\":%u,\"value_bytes\":%u,\"present\":%s,"
               "\"rx_packets\":\"%" PRIu64 "\",\"rx_bytes\":\"%" PRIu64
               "\",\"tx_packets\":\"%" PRIu64 "\",\"tx_bytes\":\"%" PRIu64 "\"}\n",
               argv[1], uid, info.id, info.key_size, info.value_size, present ? "true" : "false",
               value.rx_packets, value.rx_bytes, value.tx_packets, value.tx_bytes) < 0 || fflush(stdout) != 0) {
        perror("write counter observation");
        goto finished;
    }
    status = 0;
finished:
    if (close(descriptor) != 0) {
        perror("close read-only map descriptor");
        status = 1;
    }
    return status;
}
