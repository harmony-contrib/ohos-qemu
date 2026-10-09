/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
/* Disposable guest only. Confine quota changes to a new, unused project ID.
 * This proves kernel enforcement, NOT ordinary-app Storage API permissions. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <linux/capability.h>
#include <linux/fs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/quota.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

enum { PROJECT_QUOTA = 2, WRITE_BLOCK_SIZE = 4096, HARD_KIB = 2048 };
static const char *device;
static int project;

static int query(struct dqblk *value)
{
    memset(value, 0, sizeof(*value));
    return quotactl(QCMD(Q_GETQUOTA, PROJECT_QUOTA), device, project, (char *)value);
}

static int unused(const struct dqblk *value)
{
    return !value->dqb_curspace && !value->dqb_curinodes &&
        !value->dqb_bhardlimit && !value->dqb_bsoftlimit &&
        !value->dqb_ihardlimit && !value->dqb_isoftlimit &&
        !value->dqb_btime && !value->dqb_itime;
}

/* UID 65534 without capabilities cannot bypass quota as root can. */
static int writer(int directory, int expectQuota)
{
    struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3 };
    struct __user_cap_data_struct caps[2] = {{0}, {0}};
    if (setgroups(0, NULL) || setgid(65534) || setuid(65534) ||
        syscall(SYS_capget, &header, caps) || getuid() != 65534 || geteuid() != 65534 ||
        caps[0].effective || caps[1].effective || caps[0].permitted || caps[1].permitted) return 10;
    int fd = openat(directory, "payload", O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return 11;
    struct fsxattr actual = {0};
    if (ioctl(fd, FS_IOC_FSGETXATTR, &actual) || actual.fsx_projid != (unsigned)project) {
        close(fd);
        return 14;
    }
    char block[WRITE_BLOCK_SIZE];
    memset(block, 0xa5, sizeof(block));
    size_t count = 0;
    int error = 0;
    for (unsigned i = 0; i < 1024; ++i) {
        ssize_t result;
        do { result = write(fd, block, sizeof(block)); } while (result < 0 && errno == EINTR);
        if (result < 0) { error = errno; break; }
        if (result != sizeof(block)) { error = EIO; break; }
        count += (size_t)result;
    }
    if (!error && fsync(fd)) error = errno;
    if (close(fd) && !error) error = errno;
    if (expectQuota) return error == EDQUOT && count > 0 && count <= HARD_KIB * 1024 ? 0 : 12;
    return !error && count == 4 * 1024 * 1024 ? 0 : 13;
}

static int run_writer(int directory, int expectQuota)
{
    pid_t child = fork();
    if (child < 0) return -1;
    if (!child) _exit(writer(directory, expectQuota));
    int status = 0;
    pid_t result;
    do { result = waitpid(child, &status, 0); } while (result < 0 && errno == EINTR);
    return result == child && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
}

int main(int argc, char **argv)
{
    if (argc != 4 || strcmp(argv[1], "--disposable-guest") || strlen(argv[3]) != 32) return 2;
    for (const char *p = argv[3]; *p; ++p) if (!strchr("0123456789abcdef", *p)) return 2;
    device = argv[2];
    struct stat disk, data;
    struct statfs fs;
    if (geteuid() || strncmp(device, "/dev/block/", 11) || stat(device, &disk) ||
        !S_ISBLK(disk.st_mode) || stat("/data", &data) || disk.st_rdev != data.st_dev ||
        statfs("/data", &fs) || (unsigned long)fs.f_type != 0xf2f52010UL) return 3;
    /* Fail before any writes when project quota or either accounting class is unavailable. */
    for (int type = 0; type < 3; ++type) {
        int format = 0;
        if (quotactl(QCMD(Q_GETFMT, type), device, 0, (char *)&format) || format != 4) return 4;
    }
    unsigned randomId;
    int randomFd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    if (randomFd < 0) return 5;
    ssize_t received = read(randomFd, &randomId, sizeof(randomId));
    close(randomFd);
    if (received != sizeof(randomId)) return 5;
    project = (int)(0x60000000U | (randomId & 0x0fffffffU));
    struct dqblk saved, measured;
    if (query(&saved) || !unused(&saved)) return 6;

    char path[] = "/data/local/tmp/qemu-project-quota-XXXXXX";
    if (!mkdtemp(path)) return 7;
    int directory = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    int failed = 1, changed = 0;
    uint64_t grown = 0, recovered = 0;
    struct fsxattr original = {0}, assigned = {0};
    if (directory < 0 || ioctl(directory, FS_IOC_FSGETXATTR, &original)) goto cleanup;
    assigned = original;
    assigned.fsx_projid = (unsigned)project;
    assigned.fsx_xflags |= FS_XFLAG_PROJINHERIT;
    if (ioctl(directory, FS_IOC_FSSETXATTR, &assigned)) goto cleanup;
    if (fchown(directory, 65534, 65534) || fchmod(directory, 0700)) goto cleanup;
    struct dqblk limits = { .dqb_bhardlimit = HARD_KIB, .dqb_valid = QIF_BLIMITS };
    if (quotactl(QCMD(Q_SETQUOTA, PROJECT_QUOTA), device, project, (char *)&limits)) goto cleanup;
    changed = 1;
    if (run_writer(directory, 1) || query(&measured) || !measured.dqb_curspace ||
        measured.dqb_bhardlimit != HARD_KIB) goto cleanup;
    grown = measured.dqb_curspace;
    if (unlinkat(directory, "payload", 0) || syncfs(directory) || query(&measured) ||
        measured.dqb_curspace >= grown) goto cleanup;
    /* Restore only limits we changed; never write kernel usage counters. */
    saved.dqb_valid = QIF_BLIMITS;
    if (quotactl(QCMD(Q_SETQUOTA, PROJECT_QUOTA), device, project, (char *)&saved)) goto cleanup;
    changed = 0;
    if (run_writer(directory, 0) || query(&measured) ||
        measured.dqb_curspace < 4 * 1024 * 1024 || measured.dqb_bhardlimit) goto cleanup;
    recovered = measured.dqb_curspace;
    failed = 0;

cleanup:
    if (directory >= 0) {
        if (unlinkat(directory, "payload", 0) && errno != ENOENT) failed = 1;
        if (syncfs(directory)) failed = 1;
        if (changed) {
            saved.dqb_valid = QIF_BLIMITS;
            if (quotactl(QCMD(Q_SETQUOTA, PROJECT_QUOTA), device, project, (char *)&saved)) failed = 1;
        }
        if (close(directory)) failed = 1;
    }
    if (rmdir(path) || query(&measured) || !unused(&measured)) failed = 1;
    if (failed) {
        fprintf(stderr, "project quota runtime failed; owned project=%d path=%s\n", project, path);
        return 8;
    }
    printf("QEMU_PROJECT_QUOTA:{\"nonce\":\"%s\",\"scope\":\"disposable_guest_kernel_NOT_app_api\","
        "\"project\":%d,\"limitedBytes\":%" PRIu64 ",\"recoveredBytes\":%" PRIu64 ","
        "\"unprivilegedEdquot\":true,\"cleanup\":true}\n", argv[3], project, grown, recovered);
    return 0;
}
