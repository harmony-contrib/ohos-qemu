/* Same-guest finite virtual classic SIM AT backend for APN UI testing only.
 * Original APN mode stays unchanged. Opt-in L22 adds finite CS/SMS/TUN
 * endpoint transactions; it does not implement carrier IMS/RF/media.
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
/* Opt-in bounded virtual modem transactions on the SAME original APN peer.
 * No telephony IPC/callback or registry success is injected. This process owns
 * the actual PTY and nonpersistent TUN fd; the packaged RIL reads/writes both.
 * A virtual packet/SIM endpoint is not RF, carrier IMS or real-world delivery. */
#include <net/if.h>
static int business_mode, registered_network, tun_fd = -1, pdp_active;
/* The already-held APN peer receives usb0 from QEMU's packaged netsysnative.
 * It never opens /dev/tun or receives CAP_NET_ADMIN. Kernel credentials and
 * the SELinux context authenticate the service independently of its reply. */
#include <stddef.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
static int tun_control = -1;
static void acquire_modem_tun(const char *op)
{
    static const char endpoint[] = "qemu_modem_tun579";
    static const char expected_context[] = "u:r:netsysnative:s0";
    int received = -1;
    tun_control = socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);
    if(tun_control<0)exit(124);
    struct timeval limit={3,0};
    if(setsockopt(tun_control,SOL_SOCKET,SO_RCVTIMEO,&limit,sizeof(limit)) ||
       setsockopt(tun_control,SOL_SOCKET,SO_SNDTIMEO,&limit,sizeof(limit)))exit(125);
    struct sockaddr_un address;
    memset(&address,0,sizeof(address));address.sun_family=AF_UNIX;
    memcpy(address.sun_path+1,endpoint,sizeof(endpoint)-1);
    if(connect(tun_control,(struct sockaddr *)&address,
       (socklen_t)(offsetof(struct sockaddr_un,sun_path)+sizeof(endpoint))))exit(126);
    struct ucred native; socklen_t size=sizeof(native);
    if(getsockopt(tun_control,SOL_SOCKET,SO_PEERCRED,&native,&size) ||
       size!=sizeof(native) || native.pid<=0)exit(127);
    char context[128];size=sizeof(context);
    if(getsockopt(tun_control,SOL_SOCKET,SO_PEERSEC,context,&size) ||
       !size || size>sizeof(context))exit(128);
    if(context[size-1]==0)--size;
    if(size!=sizeof(expected_context)-1 || memcmp(context,expected_context,size))exit(129);
    char request[160],response[256],expected[256],identity[256];
    int count=snprintf(request,sizeof(request),"QMT1\t%s\t%s\t%s\n",run_id,boot_id,op);
    if(count<=0 || (size_t)count>=sizeof(request) ||
       send(tun_control,request,(size_t)count,MSG_NOSIGNAL)!=count)exit(130);
    journal("backend",op,(const unsigned char *)request,(size_t)count);
    struct iovec vector={response,sizeof(response)};
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(4*sizeof(int))]; } ancillary;
    memset(&ancillary,0,sizeof(ancillary));
    struct msghdr message;
    memset(&message,0,sizeof(message));message.msg_iov=&vector;message.msg_iovlen=1;
    message.msg_control=ancillary.bytes;message.msg_controllen=sizeof(ancillary.bytes);
    ssize_t length=recvmsg(tun_control,&message,MSG_CMSG_CLOEXEC);
    unsigned descriptors=0;int invalid=0;
    if(length<=0 || (size_t)length>=sizeof(response) || (message.msg_flags&(MSG_TRUNC|MSG_CTRUNC)))invalid=1;
    for(struct cmsghdr *c=CMSG_FIRSTHDR(&message);c;c=CMSG_NXTHDR(&message,c)) {
        if(c->cmsg_level!=SOL_SOCKET || c->cmsg_type!=SCM_RIGHTS || c->cmsg_len<CMSG_LEN(0)) {invalid=1;continue;}
        size_t n=(c->cmsg_len-CMSG_LEN(0))/sizeof(int);
        if(c->cmsg_len!=CMSG_LEN(sizeof(int)))invalid=1;
        int *fds=(int *)CMSG_DATA(c);
        for(size_t i=0;i<n;i++) {if(descriptors++==0)received=fds[i];else close(fds[i]);}
    }
    if(descriptors!=1)invalid=1;
    if(invalid) {if(received>=0)close(received);exit(131);}
    unsigned index=if_nametoindex("usb0");
    count=snprintf(expected,sizeof(expected),"QMT1\t%s\t%s\t%s\t%d\t%u\t%u\t%d\n",
        run_id,boot_id,op,(int)native.pid,(unsigned)native.uid,index,(int)getpid());
    if(!index || count<=0 || (size_t)count>=sizeof(expected) || length!=count ||
       memcmp(response,expected,(size_t)count)) {close(received);exit(132);}
    int flags=fcntl(received,F_GETFL),fdflags=fcntl(received,F_GETFD);
    if(flags<0 || fdflags<0 || fcntl(received,F_SETFL,flags|O_NONBLOCK) ||
       !(fdflags&FD_CLOEXEC)) {close(received);exit(133);}
    tun_fd=received;
    journal("backend",op,(const unsigned char *)response,(size_t)length);
    count=snprintf(identity,sizeof(identity),"TUN-SERVER\t%d\t%u\t%.*s\n",
        (int)native.pid,(unsigned)native.uid,(int)size,context);
    if(count<=0 || (size_t)count>=sizeof(identity))exit(134);
    journal("backend",op,(const unsigned char *)identity,(size_t)count);
}

static int call_state = -1, call_direction, sms_pending, sms_fail_next, dial_fail_next, dial_timeout_next;
static unsigned sms_reference = 40;
static char call_number[32], sms_pdu[4097];
static size_t sms_used;
static unsigned char report_address[10], report_toa, report_digits;
static int report_ready;
static unsigned char unhex(char c)
{
    if (c >= '0' && c <= '9') return (unsigned char)(c-'0');
    if (c >= 'a' && c <= 'f') return (unsigned char)(c-'a'+10);
    if (c >= 'A' && c <= 'F') return (unsigned char)(c-'A'+10);
    exit(111);
}
static unsigned char decimal_swap(int n)
{
    return (unsigned char)(((n%10)<<4) | ((n/10)%10));
}
static void sms_report(int fd, const char *op)
{
    if (!business_mode || !report_ready || sms_pending || !report_digits) exit(112);
    unsigned char p[32] = {0,2};
    size_t n=2, octets=(report_digits+1)/2;
    p[n++]=(unsigned char)sms_reference;p[n++]=report_digits;p[n++]=report_toa;
    memcpy(p+n,report_address,octets);n+=octets;
    time_t current=time(NULL);struct tm tm;
    if(current==(time_t)-1 || !gmtime_r(&current,&tm)) exit(113);
    unsigned char timestamp[7] = {decimal_swap(tm.tm_year%100),decimal_swap(tm.tm_mon+1),
        decimal_swap(tm.tm_mday),decimal_swap(tm.tm_hour),decimal_swap(tm.tm_min),decimal_swap(tm.tm_sec),0};
    memcpy(p+n,timestamp,7);n+=7;memcpy(p+n,timestamp,7);n+=7;p[n++]=0;
    char wire[256];int used=snprintf(wire,sizeof(wire),"\r\n+CDS: %zu\r\n",n-1);
    if(used<=0)exit(114);
    for(size_t i=0;i<n;i++) {
        int count=snprintf(wire+(size_t)used,sizeof(wire)-(size_t)used,"%02X",p[i]);
        if(count!=2)exit(115);
        used+=count;
    }
    if((size_t)used+3>sizeof(wire))exit(116);
    memcpy(wire+(size_t)used,"\r\n",3);send_wire(fd,wire,op);report_ready=0;
}
static unsigned short ip_checksum(const unsigned char *p, size_t n)
{
    unsigned sum = 0;
    for (size_t i = 0; i + 1 < n; i += 2) sum += ((unsigned)p[i] << 8) | p[i+1];
    while (sum >> 16) sum = (sum & 65535) + (sum >> 16);
    return (unsigned short)~sum;
}
static void call_urc(int fd, const char *op, int state)
{
    char wire[96];
    int n = snprintf(wire,sizeof(wire),"\r\n^CCALLSTATE: 1,%d,0\r\n",state);
    if (n <= 0 || (size_t)n >= sizeof(wire)) exit(90);
    send_wire(fd,wire,op);
}
static int transaction_control(int fd, const char *action, const char *op)
{
    if (!strcmp(action,"l22-on")) {
        if (business_mode || !present || !radio_on || if_nametoindex("usb0")) exit(91);
        acquire_modem_tun(op);
        business_mode=registered_network=1;
        send_wire(fd,"\r\n+CREG: 1,\"0001\",\"00000001\",7\r\n+CGREG: 1,\"0001\",\"00000001\",7\r\n",op);
    } else if (!strcmp(action,"l22-answer")) {
        if (!business_mode || call_state != 2 || call_direction) exit(94);
        call_state=0;call_urc(fd,op,0);
    } else if (!strcmp(action,"l22-incoming")) {
        if (!business_mode || call_state != -1) exit(95);
        memcpy(call_number,"5550199",8);call_direction=1;call_state=4;
        send_wire(fd,"\r\n+CRING: VOICE\r\n",op);call_urc(fd,op,4);
    } else if (!strcmp(action,"l22-carrier-drop")) {
        if (!business_mode) exit(96);
        if(call_state!=-1) {
            call_state=-1;send_wire(fd,"\r\nNO CARRIER\r\n",op);call_urc(fd,op,6);
        }
        registered_network=0;pdp_active=0;
        send_wire(fd,"\r\n+CREG: 0\r\n+CGREG: 0\r\n^DATADISCONN: 1\r\n",op);
    } else if (!strcmp(action,"l22-register")) {
        if (!business_mode) exit(97);
        registered_network=1;
        send_wire(fd,"\r\n+CREG: 1,\"0001\",\"00000001\",7\r\n+CGREG: 1,\"0001\",\"00000001\",7\r\n",op);
    } else if (!strcmp(action,"l22-sms-error")) {
        if (!business_mode) exit(98);
        sms_fail_next=1;
        static const char marker[]="SMS-CMS500-until-clear";
        journal("backend",op,(const unsigned char *)marker,sizeof(marker)-1);
    } else if (!strcmp(action,"l22-sms-clear")) {
        if (!business_mode || sms_pending) exit(117);
        sms_fail_next=0;
        static const char marker[]="SMS-CMS500-cleared";
        journal("backend",op,(const unsigned char *)marker,sizeof(marker)-1);
    } else if (!strcmp(action,"l22-sms-report")) {
        sms_report(fd,op);
    } else if (!strcmp(action,"l22-dial-error")) {
        if (!business_mode) exit(99);
        dial_fail_next=1;
        static const char marker[]="next-dial-NO-CARRIER";
        journal("backend",op,(const unsigned char *)marker,sizeof(marker)-1);
    } else if (!strcmp(action,"l22-status")) {
        if (!business_mode) exit(122);
        char state[128];
        int n=snprintf(state,sizeof(state),"registered=%d call=%d pdp=%d sms_pending=%d",registered_network,call_state,pdp_active,sms_pending);
        if(n<=0 || (size_t)n>=sizeof(state))exit(123);
        journal("backend",op,(const unsigned char *)state,(size_t)n);
    } else if (!strcmp(action,"l22-dial-timeout")) {
        if (!business_mode || call_state!=-1) exit(121);
        dial_timeout_next=1;
        static const char marker[]="next-ATD-no-response-native-timeout";
        journal("backend",op,(const unsigned char *)marker,sizeof(marker)-1);
    } else if (!strcmp(action,"l22-off")) {
        if (!business_mode || pdp_active || call_state != -1 || sms_pending) exit(100);
        if (close(tun_fd)) exit(101);
        tun_fd=-1;
        if(close(tun_control))exit(135);
        tun_control=-1;
        uint64_t deadline=now_ms()+2000;
        while(if_nametoindex("usb0") && now_ms()<deadline)usleep(10000);
        if (if_nametoindex("usb0")) exit(102);
        business_mode=registered_network=0;
        sms_fail_next=dial_fail_next=dial_timeout_next=report_ready=0;
        send_wire(fd,"\r\n+CREG: 0\r\n+CGREG: 0\r\n",op);
    } else return 0;
    return 1;
}
static int transaction_reply(int fd, const char *command)
{
    if (!business_mode) return 0;
    char wire[512];int id,active,n=0;
    if (!strcmp(command,"AT+CLCC")) {
        if (call_state == -1) send_wire(fd,"\r\nOK\r\n",zero_op);
        else {
            n=snprintf(wire,sizeof(wire),"\r\n+CLCC: 1,%d,%d,0,0,\"%s\",129\r\n\r\nOK\r\n",call_direction,call_state,call_number);
            if (n <= 0 || (size_t)n >= sizeof(wire)) exit(103);
            send_wire(fd,wire,zero_op);
        }
    } else if (!strncmp(command,"ATD",3)) {
        size_t length=strlen(command);
        if (length<5 || command[length-1]!=';' || length-4>=sizeof(call_number) || !registered_network || call_state!=-1) {
            send_wire(fd,"\r\nNO CARRIER\r\n",zero_op);return 1;
        }
        for (size_t i=3;i<length-1;i++) if (command[i]<'0' || command[i]>'9') {
            send_wire(fd,"\r\n+CME ERROR: 50\r\n",zero_op);return 1;
        }
        if (dial_fail_next) {dial_fail_next=0;send_wire(fd,"\r\nNO CARRIER\r\n",zero_op);return 1;}
        if (dial_timeout_next) {
            dial_timeout_next=0;
            static const char marker[]="ATD-consumed-without-response";
            journal("backend",zero_op,(const unsigned char *)marker,sizeof(marker)-1);
            return 1;
        }
        memcpy(call_number,command+3,length-4);call_number[length-4]=0;call_direction=0;call_state=2;
        send_wire(fd,"\r\nOK\r\n",zero_op);call_urc(fd,zero_op,2);
    } else if (!strcmp(command,"ATA")) {
        if (call_state!=4 || !call_direction) send_wire(fd,"\r\nERROR\r\n",zero_op);
        else {call_state=0;send_wire(fd,"\r\nOK\r\n",zero_op);call_urc(fd,zero_op,0);}
    } else if (!strcmp(command,"AT+CHLD=11") || !strcmp(command,"ATH")) {
        if (call_state==-1) send_wire(fd,"\r\nERROR\r\n",zero_op);
        else {call_state=-1;send_wire(fd,"\r\nOK\r\n",zero_op);call_urc(fd,zero_op,6);}
    } else if (sscanf(command,"AT+CMGS=%d%n",&id,&n)==1 && n>0 && !command[n]) {
        if (id<1 || id>1600 || sms_pending) send_wire(fd,"\r\n+CMS ERROR: 304\r\n",zero_op);
        else {sms_pending=id;sms_used=0;send_wire(fd,"\r\n> ",zero_op);}
    } else if (!strcmp(command,"AT+CSCA?")) send_wire(fd,"\r\n+CSCA: \"+1234567890\",145\r\n\r\nOK\r\n",zero_op);
    else if (!strcmp(command,"AT+CNMA=1") || !strcmp(command,"AT+CNMA=2")) send_wire(fd,"\r\nOK\r\n",zero_op);
    else if (!strcmp(command,"AT+CGACT?")) {
        n=snprintf(wire,sizeof(wire),"\r\n+CGACT: 1,%d\r\n\r\nOK\r\n",pdp_active);if(n<=0)exit(104);send_wire(fd,wire,zero_op);
    } else if (!strcmp(command,"AT+CGDCONT?")) send_wire(fd,"\r\n+CGDCONT: 1,\"IP\",\"cmnet\",\"\",0,0\r\n\r\nOK\r\n",zero_op);
    else if (!strcmp(command,"AT+CGDCONT=1,\"IP\",\"cmnet\",\"\",0,0")) send_wire(fd,"\r\nOK\r\n",zero_op);
    else if (sscanf(command,"AT^NDISDUP=%d,%d%n",&id,&active,&n)==2 && n>0 && !command[n] && id==1 && (active==0 || active==1)) {
        if (active && !registered_network) send_wire(fd,"\r\n+CME ERROR: 30\r\n",zero_op);
        else {pdp_active=active;send_wire(fd,"\r\nOK\r\n",zero_op);}
    } else if (!strcmp(command,"AT^DHCP?")) {
        if (!pdp_active) send_wire(fd,"\r\nERROR\r\n",zero_op);
        else send_wire(fd,"\r\n^DHCP: 021612C6,FCFFFFFF,011612C6,011612C6,011612C6,011612C6\r\n\r\nOK\r\n",zero_op);
    } else return 0;
    return 1;
}
static void sms_byte(int fd, unsigned char ch)
{
    if (ch==26) {
        /* The real outgoing TPDU is recorded as consumed endpoint bytes; raw
         * replay independently decodes destination/alphabet/fresh nonce. */
        journal("backend",zero_op,(const unsigned char *)sms_pdu,sms_used);
        if (!sms_used || sms_used%2 || sms_used/2<(size_t)sms_pending || sms_fail_next) {
            send_wire(fd,"\r\n+CMS ERROR: 500\r\n",zero_op);
        } else {
            char wire[80];int n=snprintf(wire,sizeof(wire),"\r\n+CMGS: %u\r\n\r\nOK\r\n",++sms_reference);
            if (n<=0 || (size_t)n>=sizeof(wire)) exit(105);
            unsigned char decoded[2048];size_t total=sms_used/2;
            if(total>sizeof(decoded))exit(118);
            for(size_t i=0;i<total;i++)decoded[i]=(unsigned char)((unhex(sms_pdu[2*i])<<4)|unhex(sms_pdu[2*i+1]));
            size_t base=1+decoded[0];
            if(base+4>=total || (decoded[base]&3)!=1)exit(119);
            report_digits=decoded[base+2];report_toa=decoded[base+3];
            size_t address_octets=(report_digits+1)/2;
            if(!report_digits || address_octets>sizeof(report_address) || base+4+address_octets>total)exit(120);
            memcpy(report_address,decoded+base+4,address_octets);
            report_ready=(decoded[base]&0x20)!=0;
            send_wire(fd,wire,zero_op);
        }
        sms_pending=0;sms_used=0;return;
    }
    if (ch=='\r' || ch=='\n') return;
    if (!((ch>='0'&&ch<='9')||(ch>='a'&&ch<='f')||(ch>='A'&&ch<='F')) || sms_used==sizeof(sms_pdu)-1) exit(106);
    sms_pdu[sms_used++]=(char)ch;
}
static void packet_reply(void)
{
    unsigned char p[2048];ssize_t count=read(tun_fd,p,sizeof(p));
    if(count<0 && (errno==EAGAIN||errno==EINTR))return;
    if(count<=0)exit(107);
    if(!pdp_active || count<28 || p[0]!=0x45 || p[9]!=17 || (p[6]&0x3f)||p[7])return;
    size_t size=((unsigned)p[2]<<8)|p[3];size_t udp=((unsigned)p[24]<<8)|p[25];
    if(size!=(size_t)count || udp!=size-20 || p[22]!=(53122>>8) || p[23]!=(53122&255) || udp<8)return;
    if(memcmp(p+16,(unsigned char[]){198,18,22,1},4))return;
    journal("backend",zero_op,p,size);
    static const char prefix[]="L22-REPLY:";size_t extra=sizeof(prefix)-1;
    if(size+extra>sizeof(p))exit(108);
    memmove(p+28+extra,p+28,size-28);memcpy(p+28,prefix,extra);size+=extra;udp+=extra;
    unsigned char tmp[4];memcpy(tmp,p+12,4);memcpy(p+12,p+16,4);memcpy(p+16,tmp,4);
    unsigned char port0=p[20],port1=p[21];p[20]=p[22];p[21]=p[23];p[22]=port0;p[23]=port1;
    p[2]=(unsigned char)(size>>8);p[3]=(unsigned char)size;p[24]=(unsigned char)(udp>>8);p[25]=(unsigned char)udp;
    p[26]=p[27]=p[10]=p[11]=0;unsigned short sum=ip_checksum(p,20);p[10]=(unsigned char)(sum>>8);p[11]=(unsigned char)sum;
    if(write(tun_fd,p,size)!=(ssize_t)size)exit(109);
    journal("backend",zero_op,p,size);
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
    if (transaction_reply(fd,command)) return;
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
    if (!strcmp(command,"AT+CREG?")) { send_wire(fd,registered_network?"\r\n+CREG: 2,1,\"0001\",\"00000001\",7\r\n\r\nOK\r\n":"\r\n+CREG: 2,0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+CGREG?")) { send_wire(fd,registered_network?"\r\n+CGREG: 2,1,\"0001\",\"00000001\",7\r\n\r\nOK\r\n":"\r\n+CGREG: 2,0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+COPS?")) { send_wire(fd,registered_network?"\r\n+COPS: 0,2,\"46000\",7\r\n\r\nOK\r\n":"\r\n+COPS: 0\r\n\r\nOK\r\n",zero_op); return; }
    if (!strcmp(command,"AT+COPS=3,0;+COPS?;+COPS=3,1;+COPS?;+COPS=3,2;+COPS?")) {
        send_wire(fd,registered_network?"\r\n+COPS: 0,0,\"OHOS L22\",7\r\n+COPS: 0,1,\"OHOS\",7\r\n+COPS: 0,2,\"46000\",7\r\n\r\nOK\r\n":"\r\n+COPS: 0,0,\"\"\r\n+COPS: 0,1,\"\"\r\n+COPS: 0,2,\"\"\r\n\r\nOK\r\n",zero_op); return;
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
    struct pollfd fds[] = {{master, POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}, {-1,POLLIN,0}, {-1,POLLIN,0}};
    for (;;) {
        fds[2].fd=tun_fd;
        fds[3].fd=tun_control;
        if (poll(fds, 4, 30000) < 0) { if (errno == EINTR) continue; return 75; }
        if (fds[3].revents) return 136; /* native service lost or unexpected reply; all owned fds close */
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
                if (transaction_control(master,action,control)) {
                    /* The new mode is explicitly armed and fully reversed. */
                } else if (!strcmp(action,"insert")) {
                    present=1; send_wire(master,"\r\n^SIMST: 1\r\n",control);
                } else if (!strcmp(action,"remove")) {
                    present=0; send_wire(master,"\r\n^SIMST: 0\r\n",control);
                } else if (!strcmp(action,"status")) {
                    char state[64]; snprintf(state,sizeof(state),"present=%d radio_on=%d enabled=%d",present,radio_on,enabled);
                    journal("backend",control,(unsigned char *)state,strlen(state));
                } else if (!strcmp(action,"stop")) {
                    if (present || business_mode || tun_fd!=-1 || pdp_active || call_state!=-1) return 86; /* removal must traverse the genuine service chain first */
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
                if (sms_pending) {sms_byte(master,bytes[i]);continue;}
                if (bytes[i] == '\r' || bytes[i] == '\n') {
                    if (used) { incoming[used] = 0; reply(master, incoming); used = 0; }
                } else { if (used == sizeof(incoming) - 1) return 83; incoming[used++] = (char)bytes[i]; }
            }
        }
        if (tun_fd>=0 && fds[2].fd==tun_fd && (fds[2].revents & POLLIN)) packet_reply();
        if (tun_fd>=0 && fds[2].fd==tun_fd && (fds[2].revents & (POLLERR|POLLHUP|POLLNVAL))) return 110;
        if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) return 84;
    }
}
