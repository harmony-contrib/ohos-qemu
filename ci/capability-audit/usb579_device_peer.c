/*
 * Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by law or agreed in writing, distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 */
/* A real standard FunctionFS bulk endpoint and independent gadget raw-MIDI
 * consumer. It never opens a host USB device, calls OH_MIDI, invents a UDC,
 * modifies configfs, forks, loads a module or creates a peer at the API layer.
 * The original Root OwnedIO owns this one process and every device transition.
 */
#define _GNU_SOURCE
#include <endian.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/usb/ch9.h>
#include <linux/usb/functionfs.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static unsigned sequence;
static char run_id[33];
static int64_t Deadline(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static void Stop(int value) { (void)value; stopping = 1; }
static void Number(const char *event, int64_t value)
{
    printf("{\"event\":\"%s\",\"value\":%" PRId64 ",\"seq\":%u,\"monotonic_ms\":%" PRId64 "}\n",
        event, value, ++sequence, Deadline()); fflush(stdout);
}
static void Bytes(const char *event, const uint8_t *data, size_t size)
{
    printf("{\"event\":\"%s\",\"hex\":\"", event);
    for (size_t i = 0; i < size; ++i) printf("%02x", data[i]);
    printf("\",\"seq\":%u,\"monotonic_ms\":%" PRId64 "}\n", ++sequence, Deadline()); fflush(stdout);
}
static int Hex(const char *text, uint8_t *out, size_t count)
{
    if (strlen(text) != count * 2) return -1;
    for (size_t i = 0; i < count; ++i) {
        unsigned value = 0;
        for (unsigned j = 0; j < 2; ++j) {
            char c = text[i * 2 + j];
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return -1;
            value = value * 16 + (unsigned)(c <= '9' ? c - '0' : c - 'a' + 10);
        }
        out[i] = (uint8_t)value;
    }
    return 0;
}
static int Random(uint8_t *data, size_t count)
{
    size_t offset = 0;
    while (offset < count) {
        ssize_t size = getrandom(data + offset, count - offset, 0);
        if (size < 0 && errno == EINTR) continue;
        if (size <= 0) return -1;
        offset += (size_t)size;
    }
    return 0;
}
static int PollOne(int fd, short wanted, int64_t deadline)
{
    while (!stopping) {
        int64_t left = deadline - Deadline();
        if (left <= 0) { errno = ETIMEDOUT; return -1; }
        struct pollfd rows[2] = {{fd, wanted, 0}, {STDIN_FILENO, POLLIN, 0}};
        int rc = poll(rows, 2, left > 100 ? 100 : (int)left);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) return -1;
        if (rows[1].revents & POLLIN) {
            char command[16]; ssize_t n = read(STDIN_FILENO, command, sizeof(command));
            if (n > 0 && memchr(command, 'x', (size_t)n) != NULL) { stopping = 1; errno = ECANCELED; return -1; }
        }
        if (rows[0].revents & wanted) return 0;
        if (rows[0].revents & (POLLERR | POLLHUP | POLLNVAL)) { errno = ENODEV; return -1; }
    }
    errno = ECANCELED; return -1;
}
static int All(int fd, uint8_t *data, size_t count, bool output, int64_t deadline)
{
    size_t offset = 0;
    while (offset < count) {
        if (PollOne(fd, output ? POLLOUT : POLLIN, deadline) != 0) return -1;
        ssize_t size = output ? write(fd, data + offset, count - offset) : read(fd, data + offset, count - offset);
        if (size < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (size <= 0) { if (size == 0) errno = EPIPE; return -1; }
        offset += (size_t)size;
    }
    return 0;
}
struct __attribute__((packed)) BulkSet {
    struct usb_interface_descriptor interface;
    struct usb_endpoint_descriptor_no_audio in;
    struct usb_endpoint_descriptor_no_audio out;
};
struct __attribute__((packed)) BulkDescriptors {
    struct usb_functionfs_descs_head_v2 header;
    uint32_t fs_count;
    uint32_t hs_count;
    struct BulkSet fs;
    struct BulkSet hs;
};
static struct BulkSet Bulk(uint16_t packet)
{
    struct BulkSet value;
    memset(&value, 0, sizeof(value));
    value.interface.bLength = sizeof(value.interface); value.interface.bDescriptorType = USB_DT_INTERFACE;
    value.interface.bNumEndpoints = 2; value.interface.bInterfaceClass = USB_CLASS_VENDOR_SPEC;
    value.interface.bInterfaceSubClass = 0x57; value.interface.bInterfaceProtocol = 1; value.interface.iInterface = 1;
    value.in.bLength = sizeof(value.in); value.in.bDescriptorType = USB_DT_ENDPOINT;
    value.in.bEndpointAddress = USB_DIR_IN | 1; value.in.bmAttributes = USB_ENDPOINT_XFER_BULK;
    value.in.wMaxPacketSize = htole16(packet);
    value.out = value.in; value.out.bEndpointAddress = USB_DIR_OUT | 2;
    return value;
}
static int WriteDescription(int fd)
{
    struct BulkDescriptors value;
    memset(&value, 0, sizeof(value));
    value.header.magic = htole32(FUNCTIONFS_DESCRIPTORS_MAGIC_V2);
    value.header.length = htole32(sizeof(value));
    value.header.flags = htole32(FUNCTIONFS_HAS_FS_DESC | FUNCTIONFS_HAS_HS_DESC);
    value.fs_count = value.hs_count = htole32(3); value.fs = Bulk(64); value.hs = Bulk(512);
    if (write(fd, &value, sizeof(value)) != (ssize_t)sizeof(value)) return -1;
    static const char label[] = "OpenHarmony QEMU independent bulk endpoint";
    uint8_t strings[sizeof(struct usb_functionfs_strings_head) + sizeof(uint16_t) + sizeof(label)];
    struct usb_functionfs_strings_head header = {htole32(FUNCTIONFS_STRINGS_MAGIC), htole32(sizeof(strings)), htole32(1), htole32(1)};
    uint16_t language = htole16(0x0409);
    memcpy(strings, &header, sizeof(header)); memcpy(strings + sizeof(header), &language, sizeof(language));
    memcpy(strings + sizeof(header) + sizeof(language), label, sizeof(label));
    return write(fd, strings, sizeof(strings)) == (ssize_t)sizeof(strings) ? 0 : -1;
}
static int OpenEndpoint(const char *mount, unsigned number)
{
    char path[256];
    int count = snprintf(path, sizeof(path), "%s/ep%u", mount, number);
    if (count <= 0 || (size_t)count >= sizeof(path)) { errno = EINVAL; return -1; }
    return open(path, O_RDWR | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
}
static int BulkPeer(const char *mount)
{
    /* The normal product init owns this mount. Never mount or steal g1/HDC. */
    if (strcmp(mount, "/dev/usb-ffs/usb579") != 0) { errno = EINVAL; return -1; }
    int ep0 = -1, in = -1, out = -1, result = -1;
    ep0 = OpenEndpoint(mount, 0);
    if (ep0 < 0 || WriteDescription(ep0) != 0) goto done;
    in = OpenEndpoint(mount, 1); out = OpenEndpoint(mount, 2);
    if (in < 0 || out < 0) goto done;
    Number("descriptors-and-strings-written", 1);
    bool enabled = false; unsigned round = 0; int64_t deadline = Deadline() + 600000;
    while (!stopping && round < 24) {
        struct pollfd rows[3] = {{ep0, POLLIN, 0}, {out, enabled ? POLLIN : 0, 0}, {STDIN_FILENO, POLLIN, 0}};
        int rc = poll(rows, 3, 100);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0 || Deadline() >= deadline) { errno = ETIMEDOUT; goto done; }
        if (rows[2].revents & POLLIN) {
            char command[16]; ssize_t n = read(STDIN_FILENO, command, sizeof(command));
            if (n > 0 && memchr(command, 'x', (size_t)n) != NULL) { stopping = 1; break; }
        }
        if (rows[0].revents & POLLIN) {
            struct usb_functionfs_event event;
            ssize_t n = read(ep0, &event, sizeof(event));
            if (n != (ssize_t)sizeof(event)) { if (n < 0 && errno == EAGAIN) continue; goto done; }
            Number("functionfs-event", event.type);
            if (event.type == FUNCTIONFS_ENABLE) enabled = true;
            if (event.type == FUNCTIONFS_DISABLE || event.type == FUNCTIONFS_UNBIND) enabled = false;
            if (event.type == FUNCTIONFS_SETUP) {
                /* No vendor control API: stall an unhandled real setup request. */
                int code = (event.u.setup.bRequestType & USB_DIR_IN) ? read(ep0, &event, 0) : write(ep0, &event, 0);
                Number("unhandled-control-stall", code);
            }
        }
        if (!enabled || !(rows[1].revents & POLLIN)) continue;
        uint8_t request[64], response[128], ack[64], expected_ack[64], run[16];
        if (All(out, request, sizeof(request), false, Deadline() + 10000) != 0) goto done;
        Bytes("actual-host-request", request, sizeof(request));
        if (Hex(run_id, run, sizeof(run)) != 0 || memcmp(request, "UH57", 4) != 0 || memcmp(request + 4, run, sizeof(run)) != 0) { errno = EPROTO; goto done; }
        if (Random(response, sizeof(response)) != 0) goto done;
        memcpy(response, "UP57", 4); uint32_t index = htole32(++round); memcpy(response + 4, &index, sizeof(index));
        memcpy(response + 8, request, sizeof(request));
        Bytes("actual-independent-device-response", response, sizeof(response));
        if (All(in, response, sizeof(response), true, Deadline() + 10000) != 0 ||
            All(out, ack, sizeof(ack), false, Deadline() + 10000) != 0) goto done;
        Bytes("actual-host-challenge-ack", ack, sizeof(ack));
        memcpy(expected_ack, "UA57", 4); memcpy(expected_ack + 4, request + 20, 16);
        for (size_t i = 0; i < 32; ++i) expected_ack[20 + i] = response[72 + i] ^ 0xa5;
        memcpy(expected_ack + 52, run, 12);
        if (memcmp(ack, expected_ack, sizeof(ack)) != 0) { errno = EPROTO; goto done; }
        Number("actual-bidirectional-round", round);
    }
    result = stopping && round > 0 ? 0 : -1;
done:
    if (out >= 0) close(out);
    if (in >= 0) close(in);
    if (ep0 >= 0) close(ep0);
    return result;
}
static int MidiPeer(const char *path)
{
    unsigned card, device; char tail;
    if (sscanf(path, "/dev/snd/midiC%uD%u%c", &card, &device, &tail) != 2 || card > 127 || device > 31) { errno = EINVAL; return -1; }
    int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    struct stat st;
    if (fstat(fd, &st) != 0 || !S_ISCHR(st.st_mode)) { close(fd); errno = ENODEV; return -1; }
    Number("actual-midi-device-major-minor", (int64_t)st.st_rdev); Number("actual-midi-device-inode", st.st_ino);
    uint8_t nonce[16], received[48], wire[512]; unsigned count = 0, used = 0; uint8_t status = 0, first = 0; bool half = false;
    if (Hex(run_id, nonce, sizeof(nonce)) != 0) { close(fd); return -1; }
    Number("actual-gadget-midi-peer-ready", card);
    int64_t deadline = Deadline() + 30000, ready_at = 0;
    while (count < 16 && !stopping) {
        if (Deadline() >= deadline) { close(fd); errno = ETIMEDOUT; return -1; }
        if (Deadline() >= ready_at) {
            uint8_t ready[6] = {0x92, 0x55, 0x57, 0x82, 0x55, 0};
            if (All(fd, ready, sizeof(ready), true, Deadline() + 1000) != 0) { close(fd); return -1; }
            Bytes("actual-independent-midi-ready-wire", ready, sizeof(ready)); ready_at = Deadline() + 200;
        }
        struct pollfd incoming = {fd, POLLIN, 0};
        int code = poll(&incoming, 1, 100);
        if (code < 0 && errno == EINTR) continue;
        if (code < 0 || (incoming.revents & (POLLHUP | POLLERR))) { close(fd); return -1; }
        if (!(incoming.revents & POLLIN)) continue;
        ssize_t n = read(fd, wire, sizeof(wire));
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (n <= 0) { close(fd); return -1; }
        Bytes("actual-usb-gadget-midi-read", wire, (size_t)n);
        for (ssize_t i = 0; i < n; ++i) {
            uint8_t value = wire[i];
            if (value >= 0xf8) continue;
            if (value & 0x80) { status = value; half = false; continue; }
            if ((status & 0xf0) != 0x90 && (status & 0xf0) != 0x80) continue;
            if (!half) { first = value; half = true; continue; }
            half = false;
            if (status != 0x90 || value == 0) continue;
            if (count >= 16) { close(fd); errno = EOVERFLOW; return -1; }
            received[count * 3] = status; received[count * 3 + 1] = first; received[count * 3 + 2] = value;
            if (first != (uint8_t)(48 + nonce[count] % 24) || value != (uint8_t)(20 + nonce[count] % 90)) {
                close(fd); errno = EPROTO; return -1;
            }
            ++count; ++used;
        }
    }
    if (count != 16 || used != 16) { close(fd); errno = EPROTO; return -1; }
    Bytes("actual-consumed-host-midi-nonce", received, sizeof(received));
    uint8_t challenge[16], response[96];
    if (Random(challenge, sizeof(challenge)) != 0) { close(fd); return -1; }
    Bytes("independent-midi-challenge", challenge, sizeof(challenge));
    for (size_t i = 0; i < 16; ++i) {
        response[i * 3] = 0x91; response[i * 3 + 1] = challenge[i] & 0x7f;
        response[i * 3 + 2] = 64 + (challenge[i] >> 7);
        response[48 + i * 3] = 0x81; response[48 + i * 3 + 1] = response[i * 3 + 1]; response[48 + i * 3 + 2] = 0;
    }
    Bytes("actual-independent-gadget-midi-write", response, sizeof(response));
    int result = All(fd, response, sizeof(response), true, Deadline() + 10000);
    /* Retain the real peer FD until the original IO requests stop or a real
     * detach makes this kernel endpoint unavailable. Neither is a MIDI pass. */
    Number("actual-midi-response-written", result);
    while (result == 0 && !stopping && Deadline() < deadline) {
        struct pollfd row[2] = {{fd, POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
        int code = poll(row, 2, 100);
        if (code < 0 && errno == EINTR) continue;
        if (row[1].revents & POLLIN) {
            char command[16]; ssize_t n = read(STDIN_FILENO, command, sizeof(command));
            if (n > 0 && memchr(command, 'x', (size_t)n) != NULL) { stopping = 1; break; }
        }
        if (code < 0 || (row[0].revents & (POLLHUP | POLLERR))) { Number("actual-midi-peer-detached", row[0].revents); break; }
        if (row[0].revents & POLLIN) {
            ssize_t n = read(fd, wire, sizeof(wire));
            if (n > 0) Bytes("actual-midi-cleanup-traffic", wire, (size_t)n);
            else if (n < 0 && errno != EAGAIN && errno != EINTR) break;
        }
    }
    close(fd); return result;
}
int main(int argc, char **argv)
{
    if (argc != 4 || (strcmp(argv[1], "bulk") != 0 && strcmp(argv[1], "midi") != 0)) return 2;
    uint8_t nonce[16];
    if (Hex(argv[2], nonce, sizeof(nonce)) != 0 || getuid() != 0 || geteuid() != 0) return 2;
    memcpy(run_id, argv[2], sizeof(run_id));
    struct sigaction action; memset(&action, 0, sizeof(action)); action.sa_handler = Stop;
    sigemptyset(&action.sa_mask); sigaction(SIGTERM, &action, NULL); sigaction(SIGINT, &action, NULL); signal(SIGPIPE, SIG_IGN);
    char boot[40] = {0}; int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    ssize_t size = fd >= 0 ? read(fd, boot, sizeof(boot) - 1) : -1; if (fd >= 0) close(fd);
    if (size != 37 || boot[36] != '\n') return 1; boot[36] = 0;
    printf("{\"event\":\"identity\",\"run\":\"%s\",\"mode\":\"%s\",\"boot\":\"%s\",\"uid\":%u,\"euid\":%u,\"pid\":%u,\"seq\":%u}\n",
        run_id, argv[1], boot, (unsigned)getuid(), (unsigned)geteuid(), (unsigned)getpid(), ++sequence); fflush(stdout);
    int result = strcmp(argv[1], "bulk") == 0 ? BulkPeer(argv[3]) : MidiPeer(argv[3]);
    int error = result == 0 ? 0 : errno; Number("native-error", error); Number("all-peer-fds-closed", result);
    return result == 0 ? 0 : 1;
}
