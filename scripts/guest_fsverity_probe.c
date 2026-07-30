#include <errno.h>
#include <fcntl.h>
#include <linux/fsverity.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    const char *path = argc > 1 ? argv[1] : "/data/local/tmp/fsverity-probe";
    static const char contents[] = "OpenHarmony QEMU fs-verity probe\n";
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) {
        perror("create probe");
        return 1;
    }
    if (write(fd, contents, sizeof(contents) - 1) != sizeof(contents) - 1 ||
        fsync(fd) != 0 || close(fd) != 0) {
        perror("write probe");
        return 1;
    }

    fd = open(path, O_RDONLY);
    if (fd < 0) {
        perror("open probe");
        return 1;
    }

    struct fsverity_enable_arg arg = {
        .version = 1,
        .hash_algorithm = FS_VERITY_HASH_ALG_SHA256,
        .block_size = 4096,
    };
    if (ioctl(fd, FS_IOC_ENABLE_VERITY, &arg) != 0) {
        fprintf(stderr, "FS_IOC_ENABLE_VERITY failed: errno=%d (%s)\n",
                errno, strerror(errno));
        close(fd);
        return 1;
    }

    uint8_t digest_buffer[sizeof(struct fsverity_digest) + 64] = {0};
    struct fsverity_digest *digest = (struct fsverity_digest *)digest_buffer;
    digest->digest_algorithm = FS_VERITY_HASH_ALG_SHA256;
    digest->digest_size = sizeof(digest_buffer) - sizeof(*digest);
    if (ioctl(fd, FS_IOC_MEASURE_VERITY, digest) != 0) {
        fprintf(stderr, "FS_IOC_MEASURE_VERITY failed: errno=%d (%s)\n",
                errno, strerror(errno));
        close(fd);
        return 1;
    }

    printf("FS_IOC_ENABLE_VERITY=0 FS_IOC_MEASURE_VERITY=0 algorithm=%u digest_size=%u\n",
           digest->digest_algorithm, digest->digest_size);
    close(fd);
    return 0;
}
