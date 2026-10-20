/* Same-guest bounded AT peer, NOT a modem/SIM/IMS implementation.
 * Original Owner compiles/runs this executable and exclusively owns its fds,
 * the configured AT-path binding and cleanup. This program never changes any
 * system path/property, publishes registry state, or calls any telephony IPC.
 * argv: RUN32 BOOT36; stdin: OP32<TAB>{one,zero,invalid,stop}\n.
 * stdout is the unfiltered raw JSONL journal; stderr is diagnostics only.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>

static const char *run_id, *boot_id;
static unsigned long seq;
static char zero_op[] = "00000000000000000000000000000000";
static int hex_id(const char *s, size_t length, int boot)
{
    if (strlen(s) != length) return 0;
    for (size_t i = 0; i < length; ++i) {
        if (boot && (i == 8 || i == 13 || i == 18 || i == 23)) { if (s[i] != '-') return 0; }
        else if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
    }
    return 1;
}
static uint64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME, &t)) exit(71);
    return (uint64_t)t.tv_sec * 1000 + (uint64_t)t.tv_nsec / 1000000;
}
static void journal_at(const char *kind, const char *op, const unsigned char *raw, size_t length, uint64_t at)
{
    if (length > 4096) exit(72);
    printf("{\"schema\":1,\"run_id\":\"%s\",\"boot_id\":\"%s\",\"pid\":%d,\"uid\":%d,"
        "\"seq\":%lu,\"monotonic_ms\":%llu,\"kind\":\"%s\",\"operation_id\":\"%s\",\"hex\":\"",
        run_id, boot_id, (int)getpid(), (int)getuid(), ++seq, (unsigned long long)at, kind, op);
    for (size_t i = 0; i < length; ++i) printf("%02x", raw[i]);
    puts("\"}");
    if (fflush(stdout)) exit(73);
}
static void journal(const char *kind, const char *op, const unsigned char *raw, size_t length)
{
    journal_at(kind, op, raw, length, now_ms());
}
static void send_wire(int fd, const char *wire, const char *op)
{
    /* Stamp the successful transfer's start. A genuine callback may run on
     * another CPU before this process is scheduled to append its tx journal.
     * No event is emitted unless every actual write below has completed. */
    uint64_t started = now_ms();
    size_t length = strlen(wire), done = 0;
    while (done < length) {
        ssize_t count = write(fd, wire + done, length - done);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) exit(74);
        done += (size_t)count;
    }
    journal_at("tx", op, (const unsigned char *)wire, length, started);
}
static void reply(int fd, char *command)
{
    static const char *const config[] = {"ATE0Q0V1", "AT+CREG=2", "AT+CGREG=2", "AT+CRC=1", "AT+CSMS=1",
        "AT+CNMI=1,2,0,1,1", "AT^SIMST=1", "ATS0=0", "AT+CMEE=1", "AT^HCSQ=3,10",
        "AT^CURCEX=2,F7FFFFFFFFFFFF", "AT+CIREG=2", "AT+CCWA=1", "AT+CMUT=0", "AT+CSSN=0,1",
        "AT+CMGF=0", "AT+CSCS=\"IRA\"", "AT+CPMS=\"SM\",\"SM\",\"ME\"", "AT^TIME=1", "AT+CTZR=1",
        "AT+CIREP=1", "AT+CFUN=1,0", "AT+CFUN=0,0"};
    for (size_t i = 0; i < sizeof(config) / sizeof(config[0]); ++i) {
        if (!strcmp(command, config[i])) { send_wire(fd, "\r\nOK\r\n", zero_op); return; }
    }
    if (!strcmp(command, "AT+CPIN?")) { send_wire(fd, "\r\n+CME ERROR: 10\r\n", zero_op); return; }
    if (!strcmp(command, "AT+CREG?")) { send_wire(fd, "\r\n+CREG: 2,0\r\n\r\nOK\r\n", zero_op); return; }
    if (!strcmp(command, "AT+CGREG?")) { send_wire(fd, "\r\n+CGREG: 2,0\r\n\r\nOK\r\n", zero_op); return; }
    send_wire(fd, "\r\nERROR\r\n", zero_op);
}
int main(int argc, char **argv)
{
    if (argc != 3 || !hex_id(argv[1], 32, 0) || !hex_id(argv[2], 36, 1)) return 64;
    run_id = argv[1]; boot_id = argv[2];
    char actual_boot[64]; FILE *boot = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (!boot || !fgets(actual_boot, sizeof(actual_boot), boot)) return 65;
    fclose(boot); actual_boot[strcspn(actual_boot, "\r\n")] = 0;
    if (strcmp(actual_boot, boot_id)) return 66;
    int master = posix_openpt(O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (master < 0 || grantpt(master) || unlockpt(master)) return 67;
    char path[128]; if (ptsname_r(master, path, sizeof(path))) return 68;
    int slave = open(path, O_RDWR | O_NOCTTY | O_CLOEXEC);
    struct termios term;
    if (slave < 0 || tcgetattr(slave, &term)) return 69;
    cfmakeraw(&term);
    if (tcsetattr(slave, TCSANOW, &term)) return 70;
    /* Keep the slave open until the actual RIL reader opens it; no fake bytes. */
    journal("ready", zero_op, (unsigned char *)path, strlen(path));
    char control[128], incoming[4097]; size_t ctl = 0, used = 0;
    struct pollfd fds[] = {{master, POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
    for (;;) {
        if (poll(fds, 2, 30000) < 0) { if (errno == EINTR) continue; return 75; }
        if (fds[1].revents & (POLLERR | POLLHUP | POLLNVAL)) return 76;
        if (fds[1].revents & POLLIN) {
            char ch; ssize_t n = read(STDIN_FILENO, &ch, 1);
            if (n != 1) return 77;
            if (ch == '\n') {
                control[ctl] = 0;
                if (ctl < 34 || control[32] != '\t') return 78;
                control[32] = 0;
                if (!hex_id(control, 32, 0)) return 79;
                const char *action = control + 33;
                journal("control", control, (const unsigned char *)action, strlen(action));
                if (!strcmp(action, "one")) send_wire(master, "\r\n+OHOS5A: 1\r\n", control);
                else if (!strcmp(action, "zero")) send_wire(master, "\r\n+OHOS5A: 0\r\n", control);
                else if (!strcmp(action, "invalid")) send_wire(master, "\r\n+OHOS5A: 2\r\n\r\n+OHOS5A: 1x\r\n\r\n+OHOS5A: true\r\n", control);
                else if (!strcmp(action, "stop")) {
                    journal("closed", control, (const unsigned char *)path, strlen(path));
                    close(slave); close(master); return 0;
                } else return 80;
                ctl = 0;
            } else { if (ctl + 1 >= sizeof(control)) return 81; control[ctl++] = ch; }
        }
        if (fds[0].revents & POLLIN) {
            unsigned char bytes[256]; ssize_t n = read(master, bytes, sizeof(bytes));
            if (n <= 0) return 82;
            journal("rx", zero_op, bytes, (size_t)n);
            for (ssize_t i = 0; i < n; ++i) {
                if (bytes[i] == '\r' || bytes[i] == '\n') {
                    if (used) { incoming[used] = 0; reply(master, incoming); used = 0; }
                } else { if (used == sizeof(incoming) - 1) return 83; incoming[used++] = (char)bytes[i]; }
            }
        }
        if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) return 84;
    }
}
