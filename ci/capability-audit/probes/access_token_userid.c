/* SPDX-License-Identifier: Apache-2.0 */
/* No token/account allocation. Mutates only this root test task, then restores. */
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__aarch64__)
#define USERID_ARCH "arm64"
#elif defined(__arm__)
#define USERID_ARCH "armv7a"
#elif defined(__x86_64__)
#define USERID_ARCH "x86_64"
#else
#error unsupported probe architecture
#endif
#define SET_USERID _IOW('A', 12, uint32_t)
#define GET_USERID _IOR('A', 13, uint32_t)

static bool report(FILE *out, const char *run, const char *name, bool pass)
{
    fprintf(out, "{\"kind\":\"case\",\"run_id\":\"%s\",\"name\":\"%s\",\"pass\":%s}\n",
        run, name, pass ? "true" : "false");
    fflush(out);
    return pass;
}

/* Also called inside an ordinary HAP, with the OS account service's ID. */
int AccessTokenUserIdProbe(bool privileged, const char *run, uint32_t expected, FILE *out)
{
    if (strlen(run) != 32 || strspn(run, "0123456789abcdef") != 32 ||
        (privileged && (getuid() != 0 || geteuid() != 0)) ||
        (!privileged && (getuid() == 0 || getuid() == 3020 || geteuid() == 0 || geteuid() == 3020))) return 2;
    fprintf(out, "{\"kind\":\"userid_run\",\"run_id\":\"%s\",\"mode\":\"%s\",\"uid\":%u,"
        "\"euid\":%u,\"pointer_bits\":%zu,\"arch\":\"%s\",\"expected_user_id\":%u}\n",
        run, privileged ? "privileged" : "unprivileged", (unsigned)getuid(), (unsigned)geteuid(),
        sizeof(void *) * 8, USERID_ARCH, expected);
    int result = 1, fd = open("/dev/access_token_id", O_RDWR | O_CLOEXEC);
    uint32_t original = 0, value = 0;
    bool changed = false;
    void *readonly = MAP_FAILED;
    size_t length = 0;
#define CHECK(expression, name) do { if (!report(out, run, name, (expression))) goto cleanup; } while (0)
    /* Unlike the bitmap test, denial at open is not success: AppSpawn ID must be observable. */
    CHECK(fd >= 0, "userid_device_openable");
    CHECK(ioctl(fd, GET_USERID, &original) == 0, "userid_initial_read");
    if (!privileged) {
        CHECK(original == expected, "appspawn_userid_matches_os_account");
        value = original ^ 1u;
        int ret = ioctl(fd, SET_USERID, &value);
        changed = ret == 0;
        CHECK(ret == -1 && errno == EPERM, "normal_uid_cannot_retag_account");
        CHECK(ioctl(fd, GET_USERID, &value) == 0 && value == original, "normal_uid_account_unchanged");
    } else {
        value = original ^ 1u;
        int ret = ioctl(fd, SET_USERID, &value);
        changed = ret == 0;
        CHECK(ret == 0, "root_set_distinct_userid");
        uint32_t actual = 0;
        CHECK(ioctl(fd, GET_USERID, &actual) == 0 && actual == value, "userid_actual_roundtrip");
        pid_t child = fork();
        if (child == 0) {
            actual = 0;
            bool inherited = ioctl(fd, GET_USERID, &actual) == 0 && actual == value;
            uint32_t distinct = value ^ 2u;
            bool isolated = ioctl(fd, SET_USERID, &distinct) == 0 &&
                ioctl(fd, GET_USERID, &actual) == 0 && actual == distinct;
            _exit(inherited && isolated ? 0 : 1);
        }
        CHECK(child >= 0, "userid_fork_created");
        int status = 0;
        pid_t waited;
        do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
        CHECK(waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
            "userid_fork_inherited_and_child_changed");
        CHECK(ioctl(fd, GET_USERID, &actual) == 0 && actual == value, "child_userid_does_not_change_parent");
        CHECK(ioctl(fd, SET_USERID, NULL) == -1 && errno == EINVAL, "userid_null_set_rejected");
        CHECK(ioctl(fd, SET_USERID, (void *)(uintptr_t)1) == -1 && errno == EFAULT,
            "userid_invalid_input_rejected");
        CHECK(ioctl(fd, GET_USERID, &actual) == 0 && actual == value, "bad_set_keeps_userid");
        CHECK(ioctl(fd, SET_USERID, &original) == 0, "userid_original_restored");
        changed = false;
        CHECK(ioctl(fd, GET_USERID, &actual) == 0 && actual == original, "userid_restore_observed");
    }
    CHECK(ioctl(fd, GET_USERID, NULL) == -1 && errno == EINVAL, "userid_null_get_rejected");
    CHECK(ioctl(fd, GET_USERID, (void *)(uintptr_t)1) == -1 && errno == EFAULT,
        "userid_invalid_output_rejected");
    long page = sysconf(_SC_PAGESIZE);
    CHECK(page >= (long)sizeof(uint32_t), "userid_boundary_page_size");
    length = (size_t)page;
    readonly = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    CHECK(readonly != MAP_FAILED, "userid_boundary_mapping_created");
    CHECK(mprotect(readonly, length, PROT_READ) == 0, "userid_boundary_mapping_readonly");
    CHECK(ioctl(fd, GET_USERID, readonly) == -1 && errno == EFAULT, "userid_readonly_copyout_rejected");
    CHECK(munmap(readonly, length) == 0, "userid_boundary_mapping_removed");
    readonly = MAP_FAILED;
    CHECK(ioctl(fd, GET_USERID, &value) == 0 && value == original, "userid_final_state_unchanged");
    fprintf(out, "{\"kind\":\"complete\",\"run_id\":\"%s\"}\n", run);
    result = 0;
cleanup:
    if (readonly != MAP_FAILED) munmap(readonly, length);
    if (changed && ioctl(fd, SET_USERID, &original) != 0) result = 1;
    if (fd >= 0) close(fd);
    fflush(out);
    return result;
#undef CHECK
}

#ifndef ACCESS_TOKEN_USERID_LIBRARY
int main(int argc, char **argv)
{
    if (argc != 4 || (strcmp(argv[1], "--privileged") && strcmp(argv[1], "--unprivileged")) ||
        !argv[3][0] || strspn(argv[3], "0123456789") != strlen(argv[3])) return 2;
    errno = 0;
    char *end = NULL;
    unsigned long long expected = strtoull(argv[3], &end, 10);
    if (errno || *end || expected > UINT32_MAX) return 2;
    return AccessTokenUserIdProbe(!strcmp(argv[1], "--privileged"), argv[2], (uint32_t)expected, stdout);
}
#endif
