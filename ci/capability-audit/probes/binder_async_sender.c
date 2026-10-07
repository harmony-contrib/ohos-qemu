/* SPDX-License-Identifier: Apache-2.0
 * Real isolated vndbinder context, never the production Binder manager.
 * Refuse an already-owned context. Closing the last owned FD removes it.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/android/binder.h>
#include <poll.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { MAP_BYTES = 128 * 1024, READ_BYTES = 4096, TIMEOUT_MS = 15000,
       FAKE_PID = INT_MAX - 17, FROZEN_UPDATES = 64, CLONE_STACK_BYTES = 1024 * 1024 };
static const char *challenge;
static unsigned cases;
static int passed = 1;

struct channel { int fd; void *mapping; };
struct payload { char nonce[33]; uint32_t test; };

static int step(const char *name, int64_t actual, int64_t expected)
{
    const int ok = actual == expected;
    ++cases;
    passed &= ok;
    printf("{\"type\":\"case\",\"run_id\":\"%s\",\"name\":\"%s\","
           "\"actual\":%lld,\"expected\":%lld,\"passed\":%s}\n",
           challenge, name, (long long)actual, (long long)expected, ok ? "true" : "false");
    fflush(stdout);
    return ok;
}

static int open_channel(struct channel *channel)
{
    channel->fd = open("/dev/vndbinder", O_RDWR | O_CLOEXEC | O_NONBLOCK);
    channel->mapping = MAP_FAILED;
    if (channel->fd < 0) return -errno;
    struct binder_version version = {0};
    if (ioctl(channel->fd, BINDER_VERSION, &version) != 0) return -errno;
    if (version.protocol_version != BINDER_CURRENT_PROTOCOL_VERSION) return -EPROTO;
    channel->mapping = mmap(NULL, MAP_BYTES, PROT_READ, MAP_PRIVATE, channel->fd, 0);
    return channel->mapping == MAP_FAILED ? -errno : 0;
}

static void close_channel(struct channel *channel)
{
    if (channel->mapping != MAP_FAILED) munmap(channel->mapping, MAP_BYTES);
    if (channel->fd >= 0) close(channel->fd);
    channel->fd = -1;
    channel->mapping = MAP_FAILED;
}

static int write_command(int fd, uint32_t command, const void *payload, size_t bytes)
{
    unsigned char buffer[sizeof(uint32_t) + sizeof(struct binder_transaction_data)];
    if (bytes > sizeof(buffer) - sizeof(command)) return -EOVERFLOW;
    memcpy(buffer, &command, sizeof(command));
    if (bytes != 0) memcpy(buffer + sizeof(command), payload, bytes);
    struct binder_write_read request = {
        .write_size = sizeof(command) + bytes,
        .write_buffer = (binder_uintptr_t)(uintptr_t)buffer,
    };
    int result;
    do result = ioctl(fd, BINDER_WRITE_READ, &request); while (result < 0 && errno == EINTR);
    if (result < 0) return -errno;
    return request.write_consumed == request.write_size ? 0 : -EIO;
}

static int64_t milliseconds(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return -1;
    return (int64_t)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

static int read_transaction_timeout(int fd, uint32_t wanted, struct binder_transaction_data *transaction,
                                    int timeout_ms)
{
    const int64_t deadline = milliseconds() + timeout_ms;
    unsigned char buffer[READ_BYTES];
    while (milliseconds() < deadline) {
        struct binder_write_read request = {
            .read_size = sizeof(buffer), .read_buffer = (binder_uintptr_t)(uintptr_t)buffer,
        };
        if (ioctl(fd, BINDER_WRITE_READ, &request) < 0) {
            if (errno == EINTR) continue;
            if (errno != EAGAIN) return -errno;
            struct pollfd pfd = {.fd = fd, .events = POLLIN};
            if (poll(&pfd, 1, 50) < 0 && errno != EINTR) return -errno;
            continue;
        }
        size_t offset = 0;
        while (offset < request.read_consumed) {
            uint32_t command;
            if (request.read_consumed - offset < sizeof(command)) return -EPROTO;
            memcpy(&command, buffer + offset, sizeof(command));
            offset += sizeof(command);
            const size_t bytes = _IOC_SIZE(command);
            if (bytes > request.read_consumed - offset) return -EPROTO;
            if (command == wanted) {
                if (transaction == NULL) return bytes == 0 ? 0 : -EPROTO;
                if (bytes != sizeof(*transaction)) return -EPROTO;
                memcpy(transaction, buffer + offset, bytes);
                return 0;
            }
            if (command == BR_FAILED_REPLY || command == BR_DEAD_REPLY) return -ECONNRESET;
            if (command == BR_ERROR) return -EPROTO;
            offset += bytes;
        }
    }
    return -ETIMEDOUT;
}

static int read_transaction(int fd, uint32_t wanted, struct binder_transaction_data *transaction)
{
    return read_transaction_timeout(fd, wanted, transaction, TIMEOUT_MS);
}

static int client(int inherited, unsigned test, int one_way)
{
    close(inherited); /* Never share the manager's Binder proc across fork. */
    struct channel channel = {.fd = -1, .mapping = MAP_FAILED};
    int result = open_channel(&channel);
    if (result != 0) goto finish;
    struct payload body = {.test = test};
    memcpy(body.nonce, challenge, 33);
    struct binder_transaction_data transaction = {
        .target.handle = 0, .code = test, .flags = one_way ? TF_ONE_WAY : 0,
        .sender_pid = FAKE_PID, .sender_euid = UINT32_MAX,
        .data_size = sizeof(body), .data.ptr.buffer = (binder_uintptr_t)(uintptr_t)&body,
    };
    if (test == 4) {
        // An invalid offset-table size reaches real transaction error cleanup.
        transaction.offsets_size = 1;
        transaction.data.ptr.offsets = (binder_uintptr_t)(uintptr_t)&body;
    }
    result = write_command(channel.fd, BC_TRANSACTION, &transaction, sizeof(transaction));
    if (result == 0 && test == 4) {
        result = read_transaction(channel.fd, BR_FAILED_REPLY, NULL);
        goto finish;
    }
    if (result != 0 || one_way) goto finish;
    result = read_transaction(channel.fd, BR_REPLY, &transaction);
    if (result != 0) goto finish;
    if (transaction.data_size != sizeof(body) || transaction.offsets_size != 0 ||
        memcmp((const void *)(uintptr_t)transaction.data.ptr.buffer, &body, sizeof(body)) != 0) {
        result = -EPROTO;
    }
    const binder_uintptr_t pointer = transaction.data.ptr.buffer;
    if (write_command(channel.fd, BC_FREE_BUFFER, &pointer, sizeof(pointer)) != 0) result = -EIO;
finish:
    close_channel(&channel);
    return result;
}

static int wait_child(pid_t child)
{
    int status = 0;
    pid_t result;
    do result = waitpid(child, &status, 0); while (result < 0 && errno == EINTR);
    return result == child && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -ECHILD;
}

struct namespace_state { int result; pid_t namespace_pid; pid_t proc_pid; };
struct namespace_args { int inherited; int ready[2]; int release[2]; unsigned test; int exited; };

static pid_t proc_tgid(void)
{
    /* Keep the existing proc mount: this is also OHOS GetRealPid's identity
     * source. Do not mount a filesystem or change any other process's view. */
    FILE *status = fopen("/proc/self/status", "re");
    if (status == NULL) return -errno;
    char line[256];
    long number = -1;
    while (fgets(line, sizeof(line), status) != NULL) {
        if (sscanf(line, "Tgid: %ld", &number) == 1) break;
    }
    fclose(status);
    return number > 0 && number <= INT_MAX ? (pid_t)number : -EPROTO;
}

static int namespace_client(void *opaque)
{
    const struct namespace_args *args = opaque;
    close(args->inherited);
    close(args->ready[0]);
    close(args->release[1]);
    struct channel channel = {.fd = -1, .mapping = MAP_FAILED};
    struct namespace_state state = {.namespace_pid = getpid(), .proc_pid = proc_tgid()};
    state.result = open_channel(&channel);
    struct payload body = {.test = args->test};
    memcpy(body.nonce, challenge, sizeof(body.nonce));
    struct binder_transaction_data transaction = {
        .target.handle = 0, .code = args->test, .flags = TF_ONE_WAY,
        .sender_pid = FAKE_PID, .sender_euid = UINT32_MAX,
        .data_size = sizeof(body), .data.ptr.buffer = (binder_uintptr_t)(uintptr_t)&body,
    };
    if (state.result == 0)
        state.result = write_command(channel.fd, BC_TRANSACTION, &transaction, sizeof(transaction));
    ssize_t written;
    do written = write(args->ready[1], &state, sizeof(state)); while (written < 0 && errno == EINTR);
    int result = state.result;
    if (written != (ssize_t)sizeof(state)) result = -EIO;
    if (result == 0 && !args->exited) {
        struct pollfd pfd = {.fd = args->release[0], .events = POLLIN};
        int polled;
        do polled = poll(&pfd, 1, TIMEOUT_MS); while (polled < 0 && errno == EINTR);
        char released = 0;
        ssize_t received;
        do received = polled > 0 ? read(pfd.fd, &released, 1) : -1;
        while (received < 0 && polled > 0 && errno == EINTR);
        if (received != 1 || released != 1) result = -EIO;
    }
    close_channel(&channel);
    close(args->ready[1]);
    close(args->release[0]);
    _exit(result == 0 ? 0 : 1);
}

static int namespace_ready(int fd, struct namespace_state *state)
{
    struct pollfd pfd = {.fd = fd, .events = POLLIN};
    int polled;
    do polled = poll(&pfd, 1, TIMEOUT_MS); while (polled < 0 && errno == EINTR);
    if (polled <= 0) return polled == 0 ? -ETIMEDOUT : -errno;
    ssize_t received;
    do received = read(fd, state, sizeof(*state)); while (received < 0 && errno == EINTR);
    return received == (ssize_t)sizeof(*state) ? 0 : -EIO;
}

static int namespace_delivery(struct channel *server, const char *prefix, unsigned test, pid_t child)
{
    struct binder_transaction_data transaction = {0};
    int result = read_transaction(server->fd, BR_TRANSACTION, &transaction);
    char name[80];
    snprintf(name, sizeof(name), "%s_delivery", prefix);
    if (!step(name, result, 0)) return result;
    snprintf(name, sizeof(name), "%s_wire_pid", prefix);
    step(name, transaction.sender_pid, 0);
    snprintf(name, sizeof(name), "%s_wire_uid", prefix);
    step(name, transaction.sender_euid, geteuid());
    struct binder_sender_info info = {0};
    result = ioctl(server->fd, BINDER_GET_SENDER_INFO, &info) == 0 ? 0 : -errno;
    snprintf(name, sizeof(name), "%s_sender_ioctl", prefix);
    step(name, result, 0);
    snprintf(name, sizeof(name), "%s_kernel_pid", prefix);
    step(name, (int64_t)info.sender_pid_nr, child);
    snprintf(name, sizeof(name), "%s_forged_pid_ignored", prefix);
    step(name, info.sender_pid_nr != FAKE_PID && info.sender_pid_nr != 1 &&
               info.sender_pid_nr != (uint64_t)getpid(), 1);
    struct payload body = {.test = test};
    memcpy(body.nonce, challenge, sizeof(body.nonce));
    snprintf(name, sizeof(name), "%s_payload_and_protocol", prefix);
    step(name, transaction.code == test && transaction.flags == TF_ONE_WAY &&
         transaction.offsets_size == 0 && transaction.data_size == sizeof(body) &&
         memcmp((const void *)(uintptr_t)transaction.data.ptr.buffer, &body, sizeof(body)) == 0, 1);
    const binder_uintptr_t pointer = transaction.data.ptr.buffer;
    snprintf(name, sizeof(name), "%s_free_buffer", prefix);
    step(name, write_command(server->fd, BC_FREE_BUFFER, &pointer, sizeof(pointer)), 0);
    return result;
}

static void namespace_case(struct channel *server, unsigned test, int exited)
{
    const char *prefix = exited ? "namespace_exited_async" : "namespace_async";
    struct namespace_args args = {.inherited = server->fd, .ready = {-1, -1},
        .release = {-1, -1}, .test = test, .exited = exited};
    char name[80];
    int pipes = pipe2(args.ready, O_CLOEXEC) == 0 && pipe2(args.release, O_CLOEXEC) == 0 ? 0 : -errno;
    snprintf(name, sizeof(name), "%s_pipe_setup", prefix);
    if (!step(name, pipes, 0)) goto close_pipes;
    void *stack = malloc(CLONE_STACK_BYTES);
    pid_t child = stack == NULL ? -1 : clone(namespace_client,
        (char *)stack + CLONE_STACK_BYTES, CLONE_NEWPID | SIGCHLD, &args);
    snprintf(name, sizeof(name), "%s_clone_private_pid_namespace", prefix);
    if (!step(name, child > 0, 1)) { free(stack); goto close_pipes; }
    close(args.ready[1]); args.ready[1] = -1;
    close(args.release[0]); args.release[0] = -1;
    struct namespace_state state = {0};
    int result = namespace_ready(args.ready[0], &state), waited = 0;
    snprintf(name, sizeof(name), "%s_ready_delivery", prefix);
    if (!step(name, result, 0)) goto finish;
    snprintf(name, sizeof(name), "%s_child_open_and_send", prefix);
    if (!step(name, state.result, 0)) { result = state.result; goto finish; }
    snprintf(name, sizeof(name), "%s_namespace_pid", prefix);
    step(name, state.namespace_pid, 1);
    snprintf(name, sizeof(name), "%s_proc_pid", prefix);
    step(name, state.proc_pid, child);
    if (exited) {
        waited = 1;
        result = wait_child(child);
        snprintf(name, sizeof(name), "%s_exit_before_delivery", prefix);
        if (!step(name, result, 0)) goto finish;
    }
    printf("{\"type\":\"namespace_sender\",\"run_id\":\"%s\",\"test\":%u,\"pid\":%d,"
           "\"namespace_pid\":%d,\"proc_pid\":%d,\"one_way\":true,\"exited\":%s}\n",
           challenge, test, child, state.namespace_pid, state.proc_pid, exited ? "true" : "false");
    fflush(stdout);
    result = namespace_delivery(server, prefix, test, child);
    if (!exited && result == 0) {
        const char released = 1;
        ssize_t written;
        do written = write(args.release[1], &released, 1); while (written < 0 && errno == EINTR);
        if (written != 1) result = -EIO;
    }
finish:
    /* Only our positive clone result can be killed, never PID 0 or a service. */
    if (!waited && result != 0) kill(child, SIGKILL);
    snprintf(name, sizeof(name), "%s_client_exit", prefix);
    step(name, waited ? result : wait_child(child), 0);
    free(stack);
close_pipes:
    for (unsigned i = 0; i < 2; ++i) {
        if (args.ready[i] >= 0) close(args.ready[i]);
        if (args.release[i] >= 0) close(args.release[i]);
    }
}

static int transaction_case(struct channel *server, unsigned test, int one_way, int exited)
{
    const char *prefix = test == 1 ? "sync" : test == 2 ? "async" : "exited_async";
    const pid_t child = fork();
    if (child == 0) _exit(client(server->fd, test, one_way) == 0 ? 0 : 1);
    if (child < 0) return -errno;
    printf("{\"type\":\"sender\",\"run_id\":\"%s\",\"test\":%u,\"pid\":%d,\"one_way\":%s,\"exited\":%s}\n",
           challenge, test, child, one_way ? "true" : "false", exited ? "true" : "false");
    fflush(stdout);
    int waited = 0;
    if (exited) { waited = 1; if (wait_child(child) != 0) return -ECHILD; }
    struct binder_transaction_data transaction = {0};
    int result = read_transaction(server->fd, BR_TRANSACTION, &transaction);
    char name[80];
    snprintf(name, sizeof(name), "%s_delivery", prefix);
    if (!step(name, result, 0)) goto finish;
    snprintf(name, sizeof(name), "%s_wire_pid", prefix);
    step(name, transaction.sender_pid, one_way ? 0 : child);
    snprintf(name, sizeof(name), "%s_wire_uid", prefix);
    step(name, transaction.sender_euid, geteuid());
    struct binder_sender_info info;
    memset(&info, 0xff, sizeof(info));
    result = ioctl(server->fd, BINDER_GET_SENDER_INFO, &info) == 0 ? 0 : -errno;
    snprintf(name, sizeof(name), "%s_sender_ioctl", prefix);
    step(name, result, 0);
    snprintf(name, sizeof(name), "%s_kernel_pid", prefix);
    step(name, (int64_t)info.sender_pid_nr, child);
    snprintf(name, sizeof(name), "%s_forged_pid_ignored", prefix);
    step(name, info.sender_pid_nr != FAKE_PID && info.sender_pid_nr != (uint64_t)getpid(), 1);
    struct payload expected = {.test = test};
    memcpy(expected.nonce, challenge, 33);
    const int valid = transaction.code == test && transaction.data_size == sizeof(expected) &&
        transaction.offsets_size == 0 && transaction.flags == (one_way ? TF_ONE_WAY : 0) &&
        memcmp((const void *)(uintptr_t)transaction.data.ptr.buffer, &expected, sizeof(expected)) == 0;
    snprintf(name, sizeof(name), "%s_payload_and_protocol", prefix);
    step(name, valid, 1);
    if (!one_way) {
        struct binder_transaction_data reply = {
            .data_size = sizeof(expected), .data.ptr.buffer = (binder_uintptr_t)(uintptr_t)&expected,
        };
        result = write_command(server->fd, BC_REPLY, &reply, sizeof(reply));
        step("sync_reply", result, 0);
    }
    const binder_uintptr_t pointer = transaction.data.ptr.buffer;
    snprintf(name, sizeof(name), "%s_free_buffer", prefix);
    step(name, write_command(server->fd, BC_FREE_BUFFER, &pointer, sizeof(pointer)), 0);
finish:
    if (!waited && result != 0) kill(child, SIGKILL);
    snprintf(name, sizeof(name), "%s_client_exit", prefix);
    step(name, waited ? 0 : wait_child(child), 0);
    return result;
}

static int frozen_client(int inherited)
{
    close(inherited);
    struct channel channel = {.fd = -1, .mapping = MAP_FAILED};
    int result = open_channel(&channel);
    if (result != 0) goto finish;
    struct payload body = {0};
    memcpy(body.nonce, challenge, 33);
    struct binder_transaction_data transaction = {
        .target.handle = 0, .code = 5, .flags = TF_ONE_WAY | TF_UPDATE_TXN,
        .sender_pid = FAKE_PID, .sender_euid = UINT32_MAX,
        .data_size = sizeof(body), .data.ptr.buffer = (binder_uintptr_t)(uintptr_t)&body,
    };
    for (unsigned i = 1; i <= FROZEN_UPDATES; ++i) {
        body.test = i;
        result = write_command(channel.fd, BC_TRANSACTION, &transaction, sizeof(transaction));
        if (result != 0) goto finish;
    }
    /* A frozen target must still reject synchronous work, not bypass it. */
    transaction.code = 6;
    transaction.flags = 0;
    result = write_command(channel.fd, BC_TRANSACTION, &transaction, sizeof(transaction));
    if (result == 0) result = read_transaction(channel.fd, BR_FROZEN_REPLY, NULL);
finish:
    close_channel(&channel);
    return result;
}

static void frozen_update_case(struct channel *server)
{
    /* Freeze only this probe's own process; never an application/service PID. */
    struct binder_freeze_info freeze = {.pid = (uint32_t)getpid(), .enable = 1, .timeout_ms = 0};
    int result = ioctl(server->fd, BINDER_FREEZE, &freeze) == 0 ? 0 : -errno;
    if (!step("freeze_owned_manager", result, 0)) return;
    const pid_t child = fork();
    if (child == 0) _exit(frozen_client(server->fd) == 0 ? 0 : 1);
    if (child < 0) goto thaw;
    printf("{\"type\":\"sender\",\"run_id\":\"%s\",\"test\":5,\"pid\":%d,"
           "\"one_way\":true,\"exited\":true,\"updates\":%u}\n", challenge, child, FROZEN_UPDATES);
    fflush(stdout);
    if (!step("frozen_updates_and_sync_rejection_client_exit", wait_child(child), 0)) goto thaw;
    struct binder_frozen_status_info status = {.pid = (uint32_t)getpid()};
    result = ioctl(server->fd, BINDER_GET_FROZEN_INFO, &status) == 0 ? 0 : -errno;
    if (!step("frozen_info_ioctl", result, 0)) goto thaw;
    step("frozen_async_received", status.async_recv, 1);
    /* GET_FROZEN_INFO combines the rejected-sync bit and pending-work bit. */
    step("frozen_sync_received", status.sync_recv, 3);
    freeze.enable = 0;
    result = ioctl(server->fd, BINDER_FREEZE, &freeze) == 0 ? 0 : -errno;
    if (!step("unfreeze_owned_manager", result, 0)) goto thaw;
    for (unsigned i = 0; i < 2; ++i) {
        const char *prefix = i == 0 ? "frozen_first" : "frozen_last";
        struct binder_transaction_data transaction = {0};
        char name[80];
        result = read_transaction(server->fd, BR_TRANSACTION, &transaction);
        snprintf(name, sizeof(name), "%s_delivery", prefix);
        if (!step(name, result, 0)) return;
        snprintf(name, sizeof(name), "%s_wire_pid", prefix);
        step(name, transaction.sender_pid, 0);
        snprintf(name, sizeof(name), "%s_wire_uid", prefix);
        step(name, transaction.sender_euid, geteuid());
        struct binder_sender_info info = {0};
        result = ioctl(server->fd, BINDER_GET_SENDER_INFO, &info) == 0 ? 0 : -errno;
        snprintf(name, sizeof(name), "%s_sender_ioctl", prefix);
        step(name, result, 0);
        snprintf(name, sizeof(name), "%s_kernel_pid", prefix);
        step(name, (int64_t)info.sender_pid_nr, child);
        snprintf(name, sizeof(name), "%s_forged_pid_ignored", prefix);
        step(name, info.sender_pid_nr != FAKE_PID && info.sender_pid_nr != (uint64_t)getpid(), 1);
        struct payload expected = {.test = i == 0 ? 1 : FROZEN_UPDATES};
        memcpy(expected.nonce, challenge, 33);
        const int valid = transaction.code == 5 && transaction.data_size == sizeof(expected) &&
            transaction.offsets_size == 0 && transaction.flags == (TF_ONE_WAY | TF_UPDATE_TXN) &&
            memcmp((const void *)(uintptr_t)transaction.data.ptr.buffer, &expected, sizeof(expected)) == 0;
        snprintf(name, sizeof(name), "%s_payload_and_protocol", prefix);
        step(name, valid, 1);
        const binder_uintptr_t pointer = transaction.data.ptr.buffer;
        snprintf(name, sizeof(name), "%s_free_buffer", prefix);
        step(name, write_command(server->fd, BC_FREE_BUFFER, &pointer, sizeof(pointer)), 0);
    }
    struct binder_transaction_data unexpected = {0};
    /* The exited sender cannot enqueue more work. After both BC_FREE_BUFFER
     * commands complete, replaced items must not become ready in this queue. */
    step("frozen_superseded_transactions_not_delivered",
         read_transaction_timeout(server->fd, BR_TRANSACTION, &unexpected, 500), -ETIMEDOUT);
    return;
thaw:
    freeze.enable = 0;
    step("unfreeze_owned_manager", ioctl(server->fd, BINDER_FREEZE, &freeze) == 0 ? 0 : -errno, 0);
}

int main(int argc, char **argv)
{
    if (argc != 2 || strlen(argv[1]) != 32 || strspn(argv[1], "0123456789abcdef") != 32) return 2;
    challenge = argv[1];
    signal(SIGPIPE, SIG_IGN); /* A failed private handshake still needs cleanup. */
    alarm(90); /* A bad driver must not leave an indefinitely blocked child. */
    printf("{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"pid\":%d,\"pointer_bits\":%zu,"
           "\"context\":\"vndbinder\",\"scope\":\"kernel_sender_only_not_RS_permissions\"}\n",
           challenge, (unsigned)geteuid(), getpid(), sizeof(void *) * 8);
    struct channel server = {.fd = -1, .mapping = MAP_FAILED};
    if (!step("open_private_context", open_channel(&server), 0)) goto finish;
    int zero = 0;
    int result = ioctl(server.fd, BINDER_SET_CONTEXT_MGR, &zero) == 0 ? 0 : -errno;
    /* EBUSY/EPERM is a hard failure, never replace any existing manager. */
    if (!step("acquire_unused_private_manager", result, 0)) goto finish;
    struct binder_sender_info info = {0};
    step("initial_sender_info_ioctl", ioctl(server.fd, BINDER_GET_SENDER_INFO, &info) == 0 ? 0 : -errno, 0);
    step("initial_no_sender_pid", (int64_t)info.sender_pid_nr, 0);
    step("sender_ioctl_null_rejected", ioctl(server.fd, BINDER_GET_SENDER_INFO, NULL) == 0 ? 0 : -errno, -EFAULT);
    step("enter_owned_looper", write_command(server.fd, BC_ENTER_LOOPER, NULL, 0), 0);
    if (transaction_case(&server, 1, 0, 0) != 0) goto finish;
    if (transaction_case(&server, 2, 1, 0) != 0) goto finish;
    const pid_t invalid = fork();
    if (invalid == 0) _exit(client(server.fd, 4, 1) == 0 ? 0 : 1);
    if (!step("malformed_async_rejected", invalid > 0 ? wait_child(invalid) : -errno, 0)) goto finish;
    if (transaction_case(&server, 3, 1, 1) != 0) goto finish;
    frozen_update_case(&server);
    namespace_case(&server, 7, 0);
    namespace_case(&server, 8, 1);
finish:
    close_channel(&server);
    printf("{\"type\":\"summary\",\"run_id\":\"%s\",\"cases\":%u,\"passed\":%s,"
           "\"private_manager_closed\":true,\"first_artifact_behavior_gate_passed\":false}\n",
           challenge, cases, passed ? "true" : "false");
    return passed ? 0 : 1;
}
