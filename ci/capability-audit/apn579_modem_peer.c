/* Same-guest finite virtual classic SIM AT backend for APN UI testing only.
 * It does not implement IMS, SMS/calls or a cellular packet/data link.
 * Original Owner compiles/runs this executable and exclusively owns its fds,
 * the configured AT-path binding and cleanup. This program never changes any
 * system path/property, publishes registry state, or calls any telephony IPC.
 * argv: RUN32 BOOT36; stdin: OP32<TAB>{insert,remove,status,stop}\n.
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
static int present, radio_on = 1, enabled = 1;
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
/* Classic SIM, not USIM/FCP: actual CARDMODE enum1 selects SimFileController.
 * MCC460/MNC00 selects the actual packaged CMNET default catalog; no external subscriber/network exists.
 * No telephony IPC, settings database, account table or registry is touched. */
struct elementary_file { unsigned id; const char *path, *hex; };
static const struct elementary_file files[] = {
    {0x2fe2, "3F00", "98001010000000000010"}, /* ICCID 89000101000000000001 */
    {0x6fad, "3F007F20", "00000002"},       /* two-digit MNC */
    {0x6f38, "3F007F20", "0000000000000000"}, /* no optional SIM services */
    {0x6f3e, "3F007F20", "FF"}, {0x6f3f, "3F007F20", "FF"}
};
static void sim_io(int fd, const char *command)
{
    unsigned command_id, file_id, p1, p2, p3; int consumed = 0;
    char path[33], wire[512], data[129];
    if (sscanf(command, "AT+CRSM=%u,%u,%u,%u,%u,\"\",\"%32[0-9A-F]\"%n",
        &command_id,&file_id,&p1,&p2,&p3,path,&consumed)!=6 || !consumed || command[consumed] ||
        p1>255 || p2>255 || p3>255 || file_id>65535) {
        send_wire(fd,"\r\n+CME ERROR: 50\r\n",zero_op); return;
    }
    if (!present) { send_wire(fd,"\r\n+CME ERROR: 10\r\n",zero_op); return; }
    const struct elementary_file *file = NULL;
    for (size_t i=0;i<sizeof(files)/sizeof(files[0]);++i) {
        if (files[i].id==file_id && !strcmp(files[i].path,path)) { file=&files[i]; break; }
    }
    if (!file) { send_wire(fd,"\r\n+CRSM: 148,4\r\n\r\nOK\r\n",zero_op); return; }
    size_t length=strlen(file->hex)/2;
    if (command_id==192 && p1==0 && p2==0 && p3==15) {
        /* GSM GET RESPONSE: size[2:3], ID[4:5], EF type[6], transparent[13]. */
        snprintf(data,sizeof(data),"0000%04X%04X0400FFFFFF01020000",(unsigned)length,file_id);
    } else if (command_id==176 && p1==0 && p3>0 && (size_t)p2+p3<=length) {
        memcpy(data,file->hex+p2*2,p3*2); data[p3*2]=0;
    } else {
        /* Unknown APDU/write/record operations never receive a generic OK. */
        send_wire(fd,"\r\n+CRSM: 105,130\r\n\r\nOK\r\n",zero_op); return;
    }
    int count=snprintf(wire,sizeof(wire),"\r\n+CRSM: 144,0,\"%s\"\r\n\r\nOK\r\n",data);
    if (count<=0 || (size_t)count>=sizeof(wire)) exit(85);
    send_wire(fd,wire,zero_op);
}
static void reply(int fd, char *command)
{
    static const char *const config[] = {"AT", "ATE0Q0V1", "AT+CREG=2", "AT+CGREG=2", "AT+CRC=1", "AT+CSMS=1",
        "AT+CNMI=1,2,0,1,1", "AT^SIMST=1", "ATS0=0", "AT+CMEE=1", "AT^HCSQ=3,10",
        "AT^CURCEX=2,F7FFFFFFFFFFFF", "AT+CIREG=2", "AT+CCWA=1", "AT+CMUT=0", "AT+CSSN=0,1",
        "AT+CMGF=0", "AT+CSCS=\"IRA\"", "AT+CPMS=\"SM\",\"SM\",\"ME\"", "AT^TIME=1", "AT+CTZR=1", "AT+CIREP=1"};
    for (size_t i=0;i<sizeof(config)/sizeof(config[0]);++i) {
        if (!strcmp(command,config[i])) { send_wire(fd,"\r\nOK\r\n",zero_op); return; }
    }
    if (!strcmp(command,"AT+CFUN=1,0") || !strcmp(command,"AT+CFUN=0,0")) {
        radio_on = command[8]=='1'; send_wire(fd,"\r\nOK\r\n",zero_op); return;
    }
    if (!strcmp(command,"AT+CFUN?")) {
        send_wire(fd,radio_on?"\r\n+CFUN: 1\r\n\r\nOK\r\n":"\r\n+CFUN: 0\r\n\r\nOK\r\n",zero_op); return;
    }
    if (!strcmp(command,"AT^CARDMODE")) {
        send_wire(fd,present?"\r\n^CARDMODE: 1\r\n\r\nOK\r\n":"\r\n^CARDMODE: 0\r\n\r\nOK\r\n",zero_op); return;
    }
    if (!strcmp(command,"AT+CPIN?")) {
        send_wire(fd,!present?"\r\n+CME ERROR: 10\r\n":(!radio_on?"\r\n+CME ERROR: 14\r\n":"\r\n+CPIN: READY\r\n\r\nOK\r\n"),zero_op); return;
    }
    if (!strcmp(command,"AT+CIMI")) {
        send_wire(fd,present?"\r\n460000123456789\r\n\r\nOK\r\n":"\r\n+CME ERROR: 10\r\n",zero_op); return;
    }
    if (!strncmp(command,"AT+CRSM=",8)) { sim_io(fd,command); return; }
    if (!strcmp(command,"AT^HVSST=1,1") || !strcmp(command,"AT^HVSST=0,1") ||
        !strcmp(command,"AT^HVSST=1,0") || !strcmp(command,"AT^HVSST=0,0")) {
        enabled=command[strlen(command)-1]=='1'; send_wire(fd,"\r\nOK\r\n",zero_op); return;
    }
    if (!strcmp(command,"AT+CLCK=\"SC\",2") || !strcmp(command,"AT+CLCK=\"FD\",2")) {
        send_wire(fd,"\r\n+CLCK: 0\r\n\r\nOK\r\n",zero_op); return;
    }
    /* APN database CRUD needs an actual active SIM account, not fake RF/PDP. */
    if (!strcmp(command,"AT+CREG?")) { send_wire(fd,"\r\n+CREG: 2,0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+CGREG?")) { send_wire(fd,"\r\n+CGREG: 2,0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+COPS?")) { send_wire(fd,"\r\n+COPS: 0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+COPS=3,0;+COPS?;+COPS=3,1;+COPS?;+COPS=3,2;+COPS?")) {
        send_wire(fd,"\r\n+COPS: 0,0,\"\"\r\n+COPS: 0,1,\"\"\r\n+COPS: 0,2,\"\"\r\n\r\nOK\r\n",zero_op); return;
    }
    if (!strcmp(command,"AT+CGSN")) { send_wire(fd,"\r\n001010000000000\r\n\r\nOK\r\n",zero_op); return; }
    send_wire(fd,"\r\nERROR\r\n",zero_op);
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
                if (!strcmp(action,"insert")) {
                    present=1; send_wire(master,"\r\n^SIMST: 1\r\n",control);
                } else if (!strcmp(action,"remove")) {
                    present=0; send_wire(master,"\r\n^SIMST: 0\r\n",control);
                } else if (!strcmp(action,"status")) {
                    char state[64]; snprintf(state,sizeof(state),"present=%d radio_on=%d enabled=%d",present,radio_on,enabled);
                    journal("backend",control,(unsigned char *)state,strlen(state));
                } else if (!strcmp(action,"stop")) {
                    if (present) return 86; /* removal must traverse the genuine service chain first */
                    journal("closed",control,(const unsigned char *)path,strlen(path));
                    close(slave);close(master);return 0;
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
