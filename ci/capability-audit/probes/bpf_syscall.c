/* SPDX-License-Identifier: Apache-2.0
 * Real map readback and loopback UDP filter replacement. Root only, not a
 * NetFirewall/NetManager authorization or policy-service acceptance test.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <unistd.h>

static const char *challenge;
static unsigned cases;
static int passed = 1;

static int step(const char *name, int actual, int expected)
{
    ++cases;
    const int ok = actual == expected;
    printf("{\"type\":\"case\",\"run_id\":\"%s\",\"name\":\"%s\","
           "\"actual\":%d,\"expected\":%d,\"passed\":%s}\n",
           challenge, name, actual, expected, ok ? "true" : "false");
    fflush(stdout);
    passed &= ok;
    return ok;
}

static int bpf_call(enum bpf_cmd command, union bpf_attr *attr)
{
    int result = syscall(__NR_bpf, command, attr, sizeof(*attr));
    return result < 0 ? -errno : result;
}

static int filter(uint32_t value)
{
    const struct bpf_insn instructions[] = {
        {.code = BPF_ALU64 | BPF_MOV | BPF_K, .dst_reg = BPF_REG_0, .imm = (int32_t)value},
        {.code = BPF_JMP | BPF_EXIT},
    };
    union bpf_attr attr = {0};
    attr.prog_type = BPF_PROG_TYPE_SOCKET_FILTER;
    attr.insn_cnt = sizeof(instructions) / sizeof(instructions[0]);
    attr.insns = (uint64_t)(uintptr_t)instructions;
    attr.license = (uint64_t)(uintptr_t)"Apache";
    return bpf_call(BPF_PROG_LOAD, &attr);
}

int main(int argc, char **argv)
{
    if (argc != 2 || strlen(argv[1]) != 32 || strspn(argv[1], "0123456789abcdef") != 32) return 2;
    challenge = argv[1];
    printf("{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"pointer_bits\":%zu}\n",
           challenge, (unsigned)geteuid(), sizeof(void *) * 8);
    int map = -1, receiver = -1, sender = -1, drop = -1, allow = -1;
    union bpf_attr attr = {0};
    attr.map_type = BPF_MAP_TYPE_ARRAY;
    attr.key_size = sizeof(uint32_t);
    attr.value_size = sizeof(uint32_t);
    attr.max_entries = 4;
    map = bpf_call(BPF_MAP_CREATE, &attr);
    if (!step("map_create", map >= 0 ? 0 : map, 0)) goto finish;
    uint32_t key = 1, value = 0, observed = 0;
    memcpy(&value, challenge, sizeof(value));
    memset(&attr, 0, sizeof(attr));
    attr.map_fd = map;
    attr.key = (uint64_t)(uintptr_t)&key;
    attr.value = (uint64_t)(uintptr_t)&value;
    attr.flags = BPF_ANY;
    step("map_update", bpf_call(BPF_MAP_UPDATE_ELEM, &attr), 0);
    attr.value = (uint64_t)(uintptr_t)&observed;
    step("map_lookup", bpf_call(BPF_MAP_LOOKUP_ELEM, &attr), 0);
    step("map_challenge_readback", observed == value ? 0 : 1, 0);
    key = 7;
    step("map_lookup_out_of_range", bpf_call(BPF_MAP_LOOKUP_ELEM, &attr), -ENOENT);
    step("map_update_out_of_range", bpf_call(BPF_MAP_UPDATE_ELEM, &attr), -E2BIG);
    attr.map_fd = (uint32_t)-1;
    step("map_bad_fd", bpf_call(BPF_MAP_LOOKUP_ELEM, &attr), -EBADF);
    struct bpf_map_info info = {0};
    memset(&attr, 0, sizeof(attr));
    attr.info.bpf_fd = map;
    attr.info.info_len = sizeof(info);
    attr.info.info = (uint64_t)(uintptr_t)&info;
    step("map_info", bpf_call(BPF_OBJ_GET_INFO_BY_FD, &attr), 0);
    step("map_info_fields", info.type == BPF_MAP_TYPE_ARRAY && info.key_size == 4 &&
         info.value_size == 4 && info.max_entries == 4 ? 0 : 1, 0);

    drop = filter(0);
    if (!step("load_drop_filter", drop >= 0 ? 0 : drop, 0)) goto finish;
    allow = filter(UINT32_MAX);
    if (!step("load_allow_filter", allow >= 0 ? 0 : allow, 0)) goto finish;
    receiver = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (!step("receiver_socket", receiver >= 0 ? 0 : -errno, 0)) goto finish;
    sender = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (!step("sender_socket", sender >= 0 ? 0 : -errno, 0)) goto finish;
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    int result = bind(receiver, (struct sockaddr *)&address, sizeof(address));
    if (!step("bind_loopback", result == 0 ? 0 : -errno, 0)) goto finish;
    socklen_t size = sizeof(address);
    result = getsockname(receiver, (struct sockaddr *)&address, &size);
    if (!step("query_ephemeral_port", result == 0 && address.sin_port != 0 ? 0 : -1, 0)) goto finish;
    struct timeval timeout = {.tv_sec = 0, .tv_usec = 200000};
    result = setsockopt(receiver, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    if (!step("bounded_receive", result == 0 ? 0 : -errno, 0)) goto finish;
    result = setsockopt(receiver, SOL_SOCKET, SO_ATTACH_BPF, &drop, sizeof(drop));
    if (!step("attach_drop", result == 0 ? 0 : -errno, 0)) goto finish;
    result = sendto(sender, challenge, 32, 0, (struct sockaddr *)&address, sizeof(address));
    step("send_drop_challenge", result < 0 ? -errno : result, 32);
    char payload[64] = {0};
    do { result = recv(receiver, payload, sizeof(payload), 0); } while (result < 0 && errno == EINTR);
    step("drop_no_payload", result < 0 ? -errno : result, -EAGAIN);
    result = setsockopt(receiver, SOL_SOCKET, SO_ATTACH_BPF, &allow, sizeof(allow));
    if (!step("replace_with_allow", result == 0 ? 0 : -errno, 0)) goto finish;
    result = sendto(sender, challenge, 32, 0, (struct sockaddr *)&address, sizeof(address));
    step("send_allow_challenge", result < 0 ? -errno : result, 32);
    memset(payload, 0, sizeof(payload));
    do { result = recv(receiver, payload, sizeof(payload), 0); } while (result < 0 && errno == EINTR);
    step("allow_payload_length", result < 0 ? -errno : result, 32);
    step("allow_challenge_bytes", result == 32 && memcmp(payload, challenge, 32) == 0 ? 0 : 1, 0);
finish:
    if (map >= 0) close(map);
    if (receiver >= 0) close(receiver);
    if (sender >= 0) close(sender);
    if (drop >= 0) close(drop);
    if (allow >= 0) close(allow);
    printf("{\"type\":\"summary\",\"run_id\":\"%s\",\"cases\":%u,\"passed\":%s}\n",
           challenge, cases, passed ? "true" : "false");
    return passed ? 0 : 1;
}
