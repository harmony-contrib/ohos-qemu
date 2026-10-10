/* Read-only WPA control diagnostic; not an ordinary-app or WLAN acceptance test. */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

int main(void)
{
    const char *server = "/data/service/el1/public/wifi/sockets/wpa/wlan0";
    const char *command = "GET_CAPABILITY freq";
    char directory[] = "/data/local/tmp/oq-wpa-readback-XXXXXX";
    struct sockaddr_un local = {0};
    struct sockaddr_un remote = {0};
    struct stat server_info;
    int descriptor = -1;
    int bound = 0;
    int status = 1;
    char reply[16384];
    struct timeval timeout = {.tv_sec = 10, .tv_usec = 0};
    if (lstat(server, &server_info) != 0 || !S_ISSOCK(server_info.st_mode)) {
        fprintf(stderr, "real WLAN control socket unavailable\n");
        return 1;
    }
    /* Only newly created diagnostic files are affected. No existing ACL changes. */
    umask(077);
    if (mkdtemp(directory) == NULL) {
        perror("mkdtemp");
        return 1;
    }
    local.sun_family = AF_UNIX;
    remote.sun_family = AF_UNIX;
    int length = snprintf(local.sun_path, sizeof(local.sun_path), "%s/client", directory);
    if (length < 0 || (size_t)length >= sizeof(local.sun_path) || strlen(server) >= sizeof(remote.sun_path)) {
        fprintf(stderr, "control socket path exceeds UNIX limit\n");
        goto finished;
    }
    memcpy(remote.sun_path, server, strlen(server) + 1);
    descriptor = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (descriptor < 0 || setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
        perror("create bounded control socket");
        goto finished;
    }
    if (bind(descriptor, (struct sockaddr *)&local,
             (socklen_t)(offsetof(struct sockaddr_un, sun_path) + strlen(local.sun_path) + 1)) != 0) {
        perror("bind owned control socket");
        goto finished;
    }
    bound = 1;
    if (connect(descriptor, (struct sockaddr *)&remote,
                (socklen_t)(offsetof(struct sockaddr_un, sun_path) + strlen(remote.sun_path) + 1)) != 0) {
        perror("connect actual WPA socket");
        goto finished;
    }
    if (send(descriptor, command, strlen(command), 0) != (ssize_t)strlen(command)) {
        perror("send read-only capability request");
        goto finished;
    }
    struct iovec vector = {.iov_base = reply, .iov_len = sizeof(reply)};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1};
    ssize_t received = recvmsg(descriptor, &message, 0);
    if (received <= 0 || (message.msg_flags & MSG_TRUNC) != 0) {
        fprintf(stderr, "missing or truncated capability reply: errno=%d\n", errno);
        goto finished;
    }
    if ((size_t)received < strlen("Mode[") || memcmp(reply, "Mode[", strlen("Mode[")) != 0) {
        fprintf(stderr, "WPA did not return a frequency capability document\n");
        goto finished;
    }
    if (fwrite(reply, 1, (size_t)received, stdout) != (size_t)received || fflush(stdout) != 0) {
        perror("capture capability reply");
        goto finished;
    }
    status = 0;
finished:
    if (descriptor >= 0) {
        close(descriptor);
    }
    if (bound && unlink(local.sun_path) != 0) {
        perror("remove owned control socket");
        status = 1;
    }
    if (rmdir(directory) != 0) {
        perror("remove owned diagnostic directory");
        status = 1;
    }
    return status;
}
