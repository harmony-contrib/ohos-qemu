/* SPDX-License-Identifier: Apache-2.0 */
/* Raw ABI probe. Uses an invalid/reserved token, never an application's token. */
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#if defined(__aarch64__)
#define PROBE_ARCH "arm64"
#elif defined(__arm__)
#define PROBE_ARCH "armv7a"
#elif defined(__x86_64__)
#define PROBE_ARCH "x86_64"
#else
#error unsupported probe architecture
#endif

typedef struct { uint32_t token, perm[64]; } Bitmap;
typedef struct { uint32_t token, opcode; bool granted; } Permission;
_Static_assert(sizeof(Bitmap) == 260, "GET_ALL ABI");
_Static_assert(sizeof(Permission) == 12, "GET/SET ABI");
#define ADD _IOW('A', 5, Bitmap)
#define REMOVE _IOW('A', 6, uint32_t)
#define GET _IOW('A', 7, Permission)
#define SET _IOW('A', 8, Permission)
#define GET_ALL _IOW('A', 11, Bitmap)
#define GET_VERSION _IOR('A', 25, uint32_t)
// AccessTokenID type=3/version=7 is reserved, not a valid native/HAP token.
#define RESERVED_TOKEN UINT32_MAX
static int fd = -1;
static bool owned;
static Bitmap expected = {.token = RESERVED_TOKEN};
static atomic_bool stop_reader, reader_failed;
static atomic_uint reader_attempts;
static const char *run_id;

static void cleanup(void)
{
    if (owned) {
        uint32_t token = RESERVED_TOKEN;
        if (ioctl(fd, REMOVE, &token) != 0) perror("cleanup reserved token");
    }
    if (fd >= 0) close(fd);
}

static void check(bool pass, const char *name)
{
    printf("{\"kind\":\"case\",\"run_id\":\"%s\",\"name\":\"%s\",\"pass\":%s}\n",
        run_id, name, pass ? "true" : "false");
    fflush(stdout);
    if (!pass) exit(1);
}

static void *reader(void *arg)
{
    (void)arg;
    while (!atomic_load(&stop_reader)) {
        Bitmap data = {.token = RESERVED_TOKEN};
        int ret = ioctl(fd, GET_ALL, &data);
        int error = errno;
        if ((ret == 0 && memcmp(&data, &expected, sizeof(data)) != 0) ||
            (ret != 0 && error != ENODATA)) atomic_store(&reader_failed, true);
        Permission permission = {.token = RESERVED_TOKEN, .opcode = 2047};
        ret = ioctl(fd, GET, &permission);
        error = errno;
        int wanted = (int)(expected.perm[63] >> 31);
        if ((ret >= 0 && ret != wanted) || (ret < 0 && error != ENODATA))
            atomic_store(&reader_failed, true);
        atomic_fetch_add(&reader_attempts, 1);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    if (argc != 3 || strlen(argv[2]) != 32 || strspn(argv[2], "0123456789abcdef") != 32 ||
        (strcmp(argv[1], "--privileged") && strcmp(argv[1], "--unprivileged"))) return 2;
    run_id = argv[2];
    bool privileged = !strcmp(argv[1], "--privileged");
    // The mutation-authorized users are root and ATM (3020), not normal apps.
    if ((privileged && geteuid() != 0) || (!privileged && (geteuid() == 0 || geteuid() == 3020))) return 2;
    printf("{\"kind\":\"run\",\"run_id\":\"%s\",\"mode\":\"%s\",\"uid\":%u,\"pointer_bits\":%zu,\"arch\":\"%s\"}\n",
        run_id, argv[1] + 2, (unsigned)geteuid(), sizeof(void *) * 8, PROBE_ARCH);
    atexit(cleanup);
    fd = open("/dev/access_token_id", O_RDWR | O_CLOEXEC);
    if (!privileged && fd < 0 && (errno == EACCES || errno == EPERM)) {
        check(true, "normal_uid_device_access_denied");
        printf("{\"kind\":\"complete\",\"run_id\":\"%s\"}\n", run_id);
        return 0;
    }
    check(fd >= 0, "device_present_and_openable");
    for (unsigned i = 0; i < 64; ++i) expected.perm[i] = 0x9e3779b9u * (i + 1);
    Bitmap data = {.token = RESERVED_TOKEN};
    check(ioctl(fd, GET_ALL, &data) == -1 && errno == ENODATA, "reserved_token_absent_before_test");
    if (!privileged) {
        int ret = ioctl(fd, ADD, &expected);
        if (ret == 0) owned = true;
        check(ret == -1 && errno == EPERM, "normal_uid_cannot_add_permissions");
        Permission permission = {.token = RESERVED_TOKEN, .opcode = 0, .granted = true};
        check(ioctl(fd, SET, &permission) == -1 && errno == EPERM, "normal_uid_cannot_set_permissions");
        uint32_t token = RESERVED_TOKEN;
        check(ioctl(fd, REMOVE, &token) == -1 && errno == EPERM, "normal_uid_cannot_remove_permissions");
        uint64_t own_token = 0;
        check(ioctl(fd, _IOR('A', 1, uint64_t), &own_token) == 0, "normal_uid_read_own_token");
        check(ioctl(fd, _IOW('A', 2, uint64_t), &own_token) == -1 && errno == EPERM,
            "normal_uid_cannot_set_token");
    } else {
        int ret = ioctl(fd, ADD, &expected);
        owned = ret == 0;
        check(owned, "root_add_reserved_bitmap");
        check(ioctl(fd, GET_ALL, &data) == 0 && !memcmp(&data, &expected, sizeof(data)), "all_64_words_match");
        bool same = true;
        for (unsigned i = 0; i < 2048; ++i) {
            Permission permission = {.token = RESERVED_TOKEN, .opcode = i};
            if (ioctl(fd, GET, &permission) != (int)((expected.perm[i / 32] >> (i % 32)) & 1)) same = false;
        }
        check(same, "all_2048_bits_match_single_query");
        Permission permission = {.token = RESERVED_TOKEN, .opcode = 2047};
        check(ioctl(fd, SET, &permission) == 0, "revoke_last_bit");
        check(ioctl(fd, GET, &permission) == 0, "revocation_observed");
        permission.granted = true;
        check(ioctl(fd, SET, &permission) == 0 && ioctl(fd, GET, &permission) == 1, "grant_last_bit_observed");
        expected.perm[63] |= 0x80000000u;
        check(ioctl(fd, GET_ALL, &data) == 0 && !memcmp(&data, &expected, sizeof(data)), "grant_bitmap_observed");
        permission.opcode = 2048;
        check(ioctl(fd, GET, &permission) == -1 && errno == EINVAL, "opcode_2048_rejected");
        permission.opcode = UINT32_MAX;
        check(ioctl(fd, SET, &permission) == -1 && errno == EINVAL, "overflow_opcode_rejected");
        check(ioctl(fd, GET_ALL, NULL) == -1 && errno == EINVAL, "null_argument_rejected");
        check(ioctl(fd, GET_ALL, (void *)(uintptr_t)1) == -1 && errno == EFAULT, "invalid_user_address_rejected");
        long page_size = sysconf(_SC_PAGESIZE);
        check(page_size >= (long)sizeof(Bitmap), "page_size_for_copyout_boundary");
        void *readonly = mmap(NULL, (size_t)page_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        check(readonly != MAP_FAILED, "copyout_boundary_mapping_created");
        *(Bitmap *)readonly = expected;
        check(mprotect(readonly, (size_t)page_size, PROT_READ) == 0, "copyout_boundary_mapping_readonly");
        check(ioctl(fd, GET_ALL, readonly) == -1 && errno == EFAULT, "readonly_copyout_rejected");
        check(munmap(readonly, (size_t)page_size) == 0, "copyout_boundary_mapping_removed");
        pthread_t thread;
        check(pthread_create(&thread, NULL, reader, NULL) == 0, "concurrent_reader_started");
        bool writes_ok = true;
        uint32_t token = RESERVED_TOKEN;
        // Encourage at least one read before scheduling the writer workload.
        for (unsigned i = 0; i < 10000 && !atomic_load(&reader_attempts); ++i) usleep(100);
        for (unsigned i = 0; i < 2000; ++i) {
            if (ioctl(fd, REMOVE, &token) != 0 || ioctl(fd, ADD, &expected) != 0) { writes_ok = false; break; }
        }
        atomic_store(&stop_reader, true);
        check(pthread_join(thread, NULL) == 0, "concurrent_reader_joined");
        check(writes_ok && atomic_load(&reader_attempts) > 0 && !atomic_load(&reader_failed),
            "remove_readd_reader_snapshot_consistency");
        check(ioctl(fd, REMOVE, &token) == 0, "reserved_token_removed");
        owned = false;
        check(ioctl(fd, GET_ALL, &data) == -1 && errno == ENODATA, "removed_token_has_no_permissions");
        uint32_t version = 0;
        check(ioctl(fd, GET_VERSION, &version) == -1 && errno == EOPNOTSUPP,
            "unsupported_spm_not_falsely_advertised");
    }
    printf("{\"kind\":\"complete\",\"run_id\":\"%s\"}\n", run_id);
    return 0;
}
