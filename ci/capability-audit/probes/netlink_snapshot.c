/* GET-only root diagnostic. Seven independent dumps; never an atomic snapshot.
 * No network configuration, service API, capabilities or ioctl operations.
 * stdout is an append-only observation stream; an error never emits END.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <linux/if_addr.h>
#include <linux/fib_rules.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define CAPACITY 262144U
typedef char wire_header_size[(sizeof(struct nlmsghdr) == 16) ? 1 : -1];
typedef char wire_link_size[(sizeof(struct ifinfomsg) == 16) ? 1 : -1];
typedef char wire_address_size[(sizeof(struct ifaddrmsg) == 8) ? 1 : -1];
typedef char wire_route_size[(sizeof(struct rtmsg) == 12) ? 1 : -1];
typedef char wire_rule_size[(sizeof(struct fib_rule_hdr) == 12) ? 1 : -1];
struct dataset { const char *name; uint16_t get, reply; unsigned char family; size_t payload; };
static const struct dataset sets[] = {
    {"links", RTM_GETLINK, RTM_NEWLINK, AF_UNSPEC, 16},
    {"addresses4", RTM_GETADDR, RTM_NEWADDR, AF_INET, 8},
    {"addresses6", RTM_GETADDR, RTM_NEWADDR, AF_INET6, 8},
    {"routes4", RTM_GETROUTE, RTM_NEWROUTE, AF_INET, 12},
    {"routes6", RTM_GETROUTE, RTM_NEWROUTE, AF_INET6, 12},
    {"rules4", RTM_GETRULE, RTM_NEWRULE, AF_INET, 12},
    {"rules6", RTM_GETRULE, RTM_NEWRULE, AF_INET6, 12}
};
static uint64_t ns(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static void hex(const unsigned char *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) printf("%02x", (unsigned)p[i]);
}
static int fail(const char *reason)
{
    int saved = errno;
    printf("{\"kind\":\"error\",\"reason\":\"%s\",\"errno\":%d}\n", reason, saved);
    fflush(stdout);
    return 1;
}
static int valid_run(const char *s)
{
    size_t n = strlen(s), i;
    if (n < 16 || n > 64) return 0;
    for (i = 0; i < n; ++i)
        if (!((s[i] >= 'a' && s[i] <= 'z') || (s[i] >= 'A' && s[i] <= 'Z') ||
              (s[i] >= '0' && s[i] <= '9') || s[i] == '_' || s[i] == '-')) return 0;
    return 1;
}
static int dump(int fd, uint32_t port, uint32_t seq, size_t index, int timeout,
                unsigned char *buffer, uint64_t *total_datagrams, uint64_t *total_messages)
{
    const struct dataset *d = &sets[index];
    unsigned char request[32] = {0};
    struct nlmsghdr h;
    struct sockaddr_nl kernel;
    uint64_t start = ns(), deadline, datagrams = 0, messages = 0, data_count = 0;
    int done = 0;
    if (!start) return fail("clock");
    deadline = start + (uint64_t)timeout * UINT64_C(1000000);
    memset(&h, 0, sizeof(h)); memset(&kernel, 0, sizeof(kernel));
    h.nlmsg_len = (uint32_t)(sizeof(h) + d->payload); h.nlmsg_type = d->get;
    h.nlmsg_flags = NLM_F_REQUEST | NLM_F_DUMP; h.nlmsg_seq = seq; h.nlmsg_pid = port;
    memcpy(request, &h, sizeof(h)); request[sizeof(h)] = d->family;
    kernel.nl_family = AF_NETLINK;
    printf("{\"kind\":\"request\",\"dataset\":\"%s\",\"index\":%zu,\"seq\":%u,\"clock_ns\":%" PRIu64 ",\"hex\":\"", d->name, index, seq, start);
    hex(request, h.nlmsg_len); printf("\"}\n"); fflush(stdout);
    if (sendto(fd, request, h.nlmsg_len, 0, (struct sockaddr *)&kernel, sizeof(kernel)) != (ssize_t)h.nlmsg_len)
        return fail("send_request");
    while (!done) {
        struct pollfd pfd; struct sockaddr_nl peer; struct iovec iov; struct msghdr msg;
        uint64_t now = ns(); ssize_t length; size_t pos = 0; int ready;
        if (!now || now >= deadline) { errno = ETIMEDOUT; return fail("dump_timeout"); }
        pfd.fd = fd; pfd.events = POLLIN; pfd.revents = 0;
        ready = poll(&pfd, 1, (int)((deadline - now + 999999) / 1000000));
        if (ready < 0 && errno == EINTR) continue;
        if (ready == 0) { errno = ETIMEDOUT; return fail("dump_timeout"); }
        if (ready < 0 || pfd.revents != POLLIN) return fail("poll");
        memset(&peer, 0, sizeof(peer)); memset(&msg, 0, sizeof(msg));
        iov.iov_base = buffer; iov.iov_len = CAPACITY;
        msg.msg_name = &peer; msg.msg_namelen = sizeof(peer); msg.msg_iov = &iov; msg.msg_iovlen = 1;
        length = recvmsg(fd, &msg, 0);
        if (length <= 0) return fail("recvmsg");
        /* Emit bytes even for a rejected datagram; decoder must reject the error stream. */
        printf("{\"kind\":\"datagram\",\"dataset\":\"%s\",\"index\":%" PRIu64 ",\"clock_ns\":%" PRIu64 ",\"peer_family\":%u,\"peer_pid\":%u,\"peer_groups\":%u,\"peer_bytes\":%u,\"msg_flags\":%d,\"bytes\":%zd,\"hex\":\"",
            d->name, datagrams, ns(), (unsigned)peer.nl_family, peer.nl_pid, peer.nl_groups,
            (unsigned)msg.msg_namelen, msg.msg_flags, length);
        hex(buffer, (size_t)length <= CAPACITY ? (size_t)length : CAPACITY); printf("\"}\n"); fflush(stdout);
        if ((size_t)length > CAPACITY || msg.msg_flags || msg.msg_namelen != sizeof(peer) ||
            peer.nl_family != AF_NETLINK || peer.nl_pid || peer.nl_groups) return fail("datagram_envelope");
        while (pos < (size_t)length) {
            size_t aligned, j;
            if ((size_t)length - pos < sizeof(h)) return fail("header_truncated");
            memcpy(&h, buffer + pos, sizeof(h)); aligned = NLMSG_ALIGN(h.nlmsg_len);
            if (h.nlmsg_len < sizeof(h) || h.nlmsg_len > (size_t)length - pos ||
                aligned < h.nlmsg_len || aligned > (size_t)length - pos ||
                h.nlmsg_seq != seq || (h.nlmsg_pid != port && h.nlmsg_pid != 0) ||
                (h.nlmsg_flags & ~NLM_F_MULTI) || !(h.nlmsg_flags & NLM_F_MULTI) || done)
                return fail("message_header");
            for (j = h.nlmsg_len; j < aligned; ++j) if (buffer[pos + j]) return fail("message_padding");
            printf("{\"kind\":\"message\",\"dataset\":\"%s\",\"index\":%" PRIu64 ",\"datagram\":%" PRIu64 ",\"offset\":%zu,\"length\":%u,\"type\":%u,\"flags\":%u,\"seq\":%u,\"pid\":%u,\"hex\":\"",
                d->name, messages, datagrams, pos, h.nlmsg_len, (unsigned)h.nlmsg_type,
                (unsigned)h.nlmsg_flags, h.nlmsg_seq, h.nlmsg_pid);
            hex(buffer + pos, h.nlmsg_len); printf("\"}\n"); fflush(stdout);
            if (h.nlmsg_type == NLMSG_DONE) {
                int32_t status = 0;
                if (h.nlmsg_len != sizeof(h) && h.nlmsg_len != sizeof(h) + sizeof(status)) return fail("done_shape");
                if (h.nlmsg_len > sizeof(h)) memcpy(&status, buffer + pos + sizeof(h), sizeof(status));
                if (status) return fail("done_status");
                done = 1;
            } else if (h.nlmsg_type != d->reply || h.nlmsg_len < sizeof(h) + d->payload) {
                return fail("unexpected_message_or_error");
            } else ++data_count;
            ++messages; pos += aligned;
        }
        ++datagrams;
    }
    {
        struct pollfd pfd; int ready;
        pfd.fd = fd; pfd.events = POLLIN; pfd.revents = 0;
        ready = poll(&pfd, 1, 0);
        if (ready != 0) return fail("queued_after_done");
    }
    printf("{\"kind\":\"dataset_end\",\"dataset\":\"%s\",\"datagrams\":%" PRIu64 ",\"messages\":%" PRIu64 ",\"data_messages\":%" PRIu64 ",\"done_count\":1,\"clock_ns\":%" PRIu64 "}\n",
        d->name, datagrams, messages, data_count, ns()); fflush(stdout);
    *total_datagrams += datagrams; *total_messages += messages;
    return 0;
}
int main(int argc, char **argv)
{
    const char *run; char boot[64], netns[128], *end; FILE *stream;
    unsigned char *buffer; struct sockaddr_nl local; socklen_t size = sizeof(local);
    uint64_t start, dg = 0, messages = 0; uint32_t seq; int fd, timeout = 5000; size_t i; long value;
    if ((argc != 3 && argc != 5) || strcmp(argv[1], "--run-id") || !valid_run(argv[2])) return fail("arguments");
    run = argv[2];
    if (argc == 5) {
        if (strcmp(argv[3], "--timeout-ms")) return fail("arguments");
        errno = 0; value = strtol(argv[4], &end, 10);
        if (errno || *end || value < 100 || value > 30000) return fail("timeout_argument");
        timeout = (int)value;
    }
    if (getuid() || geteuid()) return fail("root_required");
    stream = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (!stream) return fail("boot_open");
    if (!fgets(boot, sizeof(boot), stream) || fclose(stream)) return fail("boot_read");
    if (strlen(boot) != 37 || boot[36] != '\n') return fail("boot_shape");
    boot[36] = '\0';
    for (i = 0; i < 36; ++i) {
        int dash = (i == 8 || i == 13 || i == 18 || i == 23);
        if ((dash && boot[i] != '-') || (!dash && !((boot[i] >= '0' && boot[i] <= '9') ||
            (boot[i] >= 'a' && boot[i] <= 'f')))) return fail("boot_shape");
    }
    {
        ssize_t n = readlink("/proc/self/ns/net", netns, sizeof(netns) - 1);
        if (n <= 0 || (size_t)n >= sizeof(netns) - 1) return fail("netns");
        netns[n] = '\0';
        if (n <= 6 || strncmp(netns, "net:[", 5) || netns[n - 1] != ']') return fail("netns_shape");
        for (i = 5; i + 1 < (size_t)n; ++i) if (netns[i] < '0' || netns[i] > '9') return fail("netns_shape");
    }
    fd = socket(AF_NETLINK, SOCK_DGRAM | SOCK_CLOEXEC, NETLINK_ROUTE);
    if (fd < 0) return fail("socket");
    memset(&local, 0, sizeof(local)); local.nl_family = AF_NETLINK;
    if (bind(fd, (struct sockaddr *)&local, sizeof(local)) || getsockname(fd, (struct sockaddr *)&local, &size) ||
        size != sizeof(local) || local.nl_family != AF_NETLINK || !local.nl_pid || local.nl_groups) { close(fd); return fail("bind"); }
    start = ns(); if (!start) { close(fd); return fail("clock"); }
    seq = (uint32_t)(start ^ (uint64_t)getpid()); seq = seq % (UINT32_MAX - 7U) + 1U;
    printf("{\"kind\":\"begin\",\"schema\":\"ohos-readonly-rtnetlink/v1\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"uid\":%u,\"euid\":%u,\"gid\":%u,\"pid\":%ld,\"netns\":\"%s\",\"local_port\":%u,\"clock_ns\":%" PRIu64 ",\"timeout_ms\":%d,\"datasets\":7,\"atomic\":false}\n",
        run, boot, (unsigned)getuid(), (unsigned)geteuid(), (unsigned)getgid(), (long)getpid(), netns, local.nl_pid, start, timeout); fflush(stdout);
    buffer = malloc(CAPACITY); if (!buffer) { close(fd); return fail("allocation"); }
    for (i = 0; i < sizeof(sets) / sizeof(sets[0]); ++i)
        if (dump(fd, local.nl_pid, seq + (uint32_t)i, i, timeout, buffer, &dg, &messages)) { free(buffer); close(fd); return 1; }
    free(buffer);
    if (close(fd)) return fail("close");
    printf("{\"kind\":\"end\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"pid\":%ld,\"clock_ns\":%" PRIu64 ",\"datasets\":7,\"datagrams\":%" PRIu64 ",\"messages\":%" PRIu64 ",\"status\":\"complete\"}\n",
        run, boot, (long)getpid(), ns(), dg, messages);
    return fflush(stdout) ? 1 : 0;
}
