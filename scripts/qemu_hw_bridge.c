/*
 * Copyright (c) 2026 OpenHarmony QEMU contributors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Guest hardware capability bridge daemon & CLI controller (/vendor/bin/qemu-hw-bridge).
 *
 * Bridges QEMU host parameters (/proc/cmdline), virtio-serial port (ohos.hw.bridge0),
 * and local UNIX socket (/data/vendor/qemu_hw_bridge.sock) to OpenHarmony guest subsystems:
 *   1. GNSS Location HDI (/dev/unix/socket/qemu_gnss/input, QGN1/QGF1 protocol)
 *   2. Sensor HDI (/dev/unix/socket/qemu_sensor/{input,rotation,headposture}, QSN1/QSF1, QRS1/QRF1, QHP1/QHF1)
 *   3. Battery HDI & BatteryService (/data/service/el0/battery, test_power, SA 3302)
 *   4. Thermal HDI & ThermalService (/data/service/el0/thermal, SA 3303)
 *   5. Pasteboard / Clipboard NDK (libpasteboard.so + libudmf.so + /data/service/el1/public/qemu_clipboard.txt)
 *   6. Virtual Camera V4L2 test pattern control (/dev/video0 vivid controls)
 *   7. Host-to-Guest RTC millisecond clock sync
 */

#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CONTROL_SOCK_PATH "/data/vendor/qemu_hw_bridge.sock"
#define GNSS_SOCK_PATH "/dev/unix/socket/qemu_gnss/input"
#define SENSOR_ACCEL_SOCK_PATH "/dev/unix/socket/qemu_sensor/input"
#define SENSOR_ROT_SOCK_PATH "/dev/unix/socket/qemu_sensor/rotation"
#define SENSOR_HEAD_SOCK_PATH "/dev/unix/socket/qemu_sensor/headposture"

#define GNSS_STATE_FILE "/data/vendor/gnss/qemu_last_location.json"
#define SENSOR_STATE_FILE "/data/service/el1/public/qemu_sensor_state.json"
#define CLIPBOARD_FILE "/data/service/el1/public/qemu_clipboard.txt"

#define VIVID_CID_VIVID_BASE (0x00f00000 | 0xf000)
#define VIVID_CID_TEST_PATTERN (VIVID_CID_VIVID_BASE + 0)
#define VIVID_CID_OSD_TEXT_MODE (VIVID_CID_VIVID_BASE + 1)
#define VIVID_CID_HOR_MOVEMENT (VIVID_CID_VIVID_BASE + 2)
#define VIVID_CID_VERT_MOVEMENT (VIVID_CID_VIVID_BASE + 3)
#define VIVID_CID_SHOW_BORDER (VIVID_CID_VIVID_BASE + 4)
#define VIVID_CID_SHOW_SQUARE (VIVID_CID_VIVID_BASE + 5)
#define VIVID_CID_HFLIP (VIVID_CID_VIVID_BASE + 20)
#define VIVID_CID_VFLIP (VIVID_CID_VIVID_BASE + 21)

static void write_le(uint8_t *dst, uint64_t val, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        dst[i] = (uint8_t)((val >> (i * 8)) & 0xffu);
    }
}

static uint64_t read_le(const uint8_t *src, size_t count) {
    uint64_t val = 0;
    for (size_t i = 0; i < count; ++i) {
        val |= ((uint64_t)src[i]) << (i * 8);
    }
    return val;
}

static void write_f32_le(uint8_t *dst, float f) {
    uint32_t bits = 0;
    memcpy(&bits, &f, sizeof(bits));
    write_le(dst, bits, 4);
}

static void write_f64_le(uint8_t *dst, double d) {
    uint64_t bits = 0;
    memcpy(&bits, &d, sizeof(bits));
    write_le(dst, bits, 8);
}

static uint64_t now_realtime_ms(void) {
    struct timespec ts = {0, 0};
    clock_gettime(CLOCK_REALTIME, &ts);
    if (ts.tv_sec < 0) {
        return 0;
    }
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)(ts.tv_nsec / 1000000L);
}

static uint64_t now_monotonic_ms(void) {
    struct timespec ts = {0, 0};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)(ts.tv_nsec / 1000000L);
}

static int write_file_inplace(const char *path, const char *content) {
    int fd = open(path, O_CREAT | O_WRONLY | O_TRUNC | O_CLOEXEC, 0664);
    if (fd < 0) {
        return -1;
    }
    size_t len = strlen(content);
    ssize_t n = write(fd, content, len);
    close(fd);
    return (n == (ssize_t)len) ? 0 : -1;
}

static void mkdir_p_one(const char *path, mode_t mode) {
    mkdir(path, mode);
    chmod(path, mode);
}

/* Base64 helpers for safe single-line clipboard transport */
static const char b64_table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static size_t b64_encode(const uint8_t *in, size_t in_len, char *out, size_t out_cap) {
    size_t i = 0, o = 0;
    while (i < in_len && o + 4 < out_cap) {
        uint32_t a = i < in_len ? in[i++] : 0;
        uint32_t b = i < in_len ? in[i++] : 0;
        uint32_t c = i < in_len ? in[i++] : 0;
        uint32_t triple = (a << 16) | (b << 8) | c;
        out[o++] = b64_table[(triple >> 18) & 0x3f];
        out[o++] = b64_table[(triple >> 12) & 0x3f];
        out[o++] = b64_table[(triple >> 6) & 0x3f];
        out[o++] = b64_table[triple & 0x3f];
    }
    size_t mod = in_len % 3;
    if (mod == 1 && o >= 2) {
        out[o - 1] = '=';
        out[o - 2] = '=';
    } else if (mod == 2 && o >= 1) {
        out[o - 1] = '=';
    }
    out[o] = '\0';
    return o;
}

static int b64_val(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

static size_t b64_decode(const char *in, uint8_t *out, size_t out_cap) {
    size_t o = 0;
    uint32_t buf = 0;
    int bits = 0;
    for (const char *p = in; *p; ++p) {
        if (*p == '=' || *p == '\r' || *p == '\n' || *p == ' ') {
            continue;
        }
        int v = b64_val(*p);
        if (v < 0) {
            continue;
        }
        buf = (buf << 6) | (uint32_t)v;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (o + 1 < out_cap) {
                out[o++] = (uint8_t)((buf >> bits) & 0xffu);
            }
        }
    }
    out[o] = '\0';
    return o;
}

/* Bridge state */
typedef struct {
    int gnss_enabled;
    int gnss_fd;
    int gnss_ready;
    int gnss_location_host_started;
    uint8_t gnss_nonce[16];
    uint64_t gnss_seq;
    uint64_t gnss_last_utc_ms;
    double lat;
    double lon;
    double alt;
    float hacc;
    float vacc;
    float speed;
    float bearing;

    int sensor_enabled;
    int accel_fd;
    int accel_ready;
    uint8_t accel_nonce[16];
    uint64_t accel_seq;
    float ax, ay, az;

    int rot_fd;
    int rot_ready;
    uint8_t rot_nonce[16];
    uint64_t rot_seq;
    float rx, ry, rz, rw;

    int head_fd;
    int head_ready;
    uint8_t head_nonce[16];
    uint64_t head_seq;
    uint32_t head_order;
    float hw, hx, hy, hz;

    int battery_level;
    char battery_status[32];
    int battery_custom;
    int battery_synced_after_boot;

    double thermal_c;
    int thermal_custom;
    int thermal_synced_after_boot;

    char camera_pattern[64];
    int camera_custom;

    int vport_fd;
    int ctrl_listen_fd;
} bridge_state_t;

static void normalize_quat(float *x, float *y, float *z, float *w) {
    float n = sqrtf((*x) * (*x) + (*y) * (*y) + (*z) * (*z) + (*w) * (*w));
    if (!isfinite(n) || n < 1e-6f) {
        *x = 0.0f;
        *y = 0.0f;
        *z = 0.0f;
        *w = 1.0f;
        return;
    }
    *x /= n;
    *y /= n;
    *z /= n;
    *w /= n;
}

static int connect_unix_nonblock(const char *path) {
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        return -1;
    }
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        if (errno != EINPROGRESS) {
            close(fd);
            return -1;
        }
    }
    return fd;
}

static void save_gnss_state(const bridge_state_t *st) {
    mkdir_p_one("/data/vendor", 0771);
    mkdir_p_one("/data/vendor/gnss", 0770);
    char buf[512];
    snprintf(buf, sizeof(buf),
             "{\n"
             "  \"enabled\": %s,\n"
             "  \"connected\": %s,\n"
             "  \"sequence\": %llu,\n"
             "  \"utcMs\": %llu,\n"
             "  \"latitude\": %.6f,\n"
             "  \"longitude\": %.6f,\n"
             "  \"altitude\": %.2f,\n"
             "  \"speed\": %.2f,\n"
             "  \"bearing\": %.2f,\n"
             "  \"horizontalAccuracy\": %.2f,\n"
             "  \"verticalAccuracy\": %.2f\n"
             "}\n",
             st->gnss_enabled ? "true" : "false",
             st->gnss_ready ? "true" : "false",
             (unsigned long long)st->gnss_seq,
             (unsigned long long)st->gnss_last_utc_ms,
             st->lat, st->lon, st->alt, st->speed, st->bearing, st->hacc, st->vacc);
    write_file_inplace(GNSS_STATE_FILE, buf);
    write_file_inplace("/data/vendor/gnss_state.json", buf);
}

static void save_sensor_state(const bridge_state_t *st) {
    mkdir_p_one("/data/service/el1/public", 0775);
    mkdir_p_one("/data/vendor", 0771);
    char buf[512];
    snprintf(buf, sizeof(buf),
             "{\n"
             "  \"accelConnected\": %s,\n"
             "  \"accelSeq\": %llu,\n"
             "  \"accel\": [%.4f, %.4f, %.4f],\n"
             "  \"rotationConnected\": %s,\n"
             "  \"rotationSeq\": %llu,\n"
             "  \"rotation\": [%.4f, %.4f, %.4f, %.4f],\n"
             "  \"headPostureConnected\": %s,\n"
             "  \"headPostureSeq\": %llu,\n"
             "  \"headPosture\": [%.4f, %.4f, %.4f, %.4f]\n"
             "}\n",
             st->accel_ready ? "true" : "false",
             (unsigned long long)st->accel_seq,
             st->ax, st->ay, st->az,
             st->rot_ready ? "true" : "false",
             (unsigned long long)st->rot_seq,
             st->rx, st->ry, st->rz, st->rw,
             st->head_ready ? "true" : "false",
             (unsigned long long)st->head_seq,
             st->hw, st->hx, st->hy, st->hz);
    write_file_inplace(SENSOR_STATE_FILE, buf);
    write_file_inplace("/data/vendor/sensor_state.json", buf);
}

static void send_gnss_frame(bridge_state_t *st) {
    if (!st->gnss_enabled) {
        return;
    }
    if (st->gnss_fd < 0) {
        if (access(GNSS_SOCK_PATH, F_OK) != 0) {
            if (!st->gnss_location_host_started) {
                st->gnss_location_host_started = 1;
                pid_t pid = fork();
                if (pid == 0) {
                    alarm(4);
                    execl("/system/bin/param", "param", "set", "ohos.ctl.start", "location_host", (char *)NULL);
                    _exit(0);
                }
            }
            save_gnss_state(st);
            return;
        }
        st->gnss_fd = connect_unix_nonblock(GNSS_SOCK_PATH);
        st->gnss_ready = 0;
    }
    if (st->gnss_fd >= 0 && !st->gnss_ready) {
        uint8_t hello[32];
        ssize_t n = recv(st->gnss_fd, hello, sizeof(hello), MSG_DONTWAIT);
        if (n == 32 && memcmp(hello, "QGN1", 4) == 0 && read_le(hello + 4, 4) == 1 && read_le(hello + 24, 4) == 88) {
            memcpy(st->gnss_nonce, hello + 8, 16);
            st->gnss_seq = 0;
            st->gnss_last_utc_ms = 0;
            st->gnss_ready = 1;
        } else if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
            close(st->gnss_fd);
            st->gnss_fd = -1;
            st->gnss_ready = 0;
            save_gnss_state(st);
            return;
        }
    }
    if (st->gnss_fd >= 0 && st->gnss_ready) {
        uint64_t utc_ms = now_realtime_ms();
        if (utc_ms <= st->gnss_last_utc_ms) {
            utc_ms = st->gnss_last_utc_ms + 1;
        }
        uint64_t next_seq = st->gnss_seq + 1;
        uint8_t frame[88];
        memset(frame, 0, sizeof(frame));
        memcpy(frame, "QGF1", 4);
        write_le(frame + 4, 1, 4);
        memcpy(frame + 8, st->gnss_nonce, 16);
        write_le(frame + 24, next_seq, 8);
        write_le(frame + 32, utc_ms, 8);
        write_f64_le(frame + 40, st->lat);
        write_f64_le(frame + 48, st->lon);
        write_f64_le(frame + 56, st->alt);
        write_f32_le(frame + 64, st->hacc);
        write_f32_le(frame + 68, st->vacc);
        write_f32_le(frame + 72, st->speed);
        write_f32_le(frame + 76, st->bearing);
        write_le(frame + 80, (4u | 8u | 16u | 64u), 4);
        write_le(frame + 84, 0, 4);
        ssize_t n = send(st->gnss_fd, frame, sizeof(frame), MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n == (ssize_t)sizeof(frame)) {
            st->gnss_seq = next_seq;
            st->gnss_last_utc_ms = utc_ms;
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            close(st->gnss_fd);
            st->gnss_fd = -1;
            st->gnss_ready = 0;
        }
    }
    save_gnss_state(st);
}

static void send_sensor_frames(bridge_state_t *st) {
    if (!st->sensor_enabled) {
        return;
    }
    /* 1. Accelerometer (/dev/unix/socket/qemu_sensor/input) */
    if (st->accel_fd < 0 && access(SENSOR_ACCEL_SOCK_PATH, F_OK) == 0) {
        st->accel_fd = connect_unix_nonblock(SENSOR_ACCEL_SOCK_PATH);
        st->accel_ready = 0;
    }
    if (st->accel_fd >= 0 && !st->accel_ready) {
        uint8_t hello[32];
        ssize_t n = recv(st->accel_fd, hello, sizeof(hello), MSG_DONTWAIT);
        if (n == 32 && memcmp(hello, "QSN1", 4) == 0 && read_le(hello + 4, 4) == 1) {
            memcpy(st->accel_nonce, hello + 8, 16);
            st->accel_seq = 0;
            st->accel_ready = 1;
        } else if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
            close(st->accel_fd);
            st->accel_fd = -1;
            st->accel_ready = 0;
        }
    }
    if (st->accel_fd >= 0 && st->accel_ready) {
        uint64_t next_seq = st->accel_seq + 1;
        uint8_t frame[44];
        memset(frame, 0, sizeof(frame));
        memcpy(frame, "QSF1", 4);
        write_le(frame + 4, 1, 4);
        memcpy(frame + 8, st->accel_nonce, 16);
        write_le(frame + 24, next_seq, 8);
        write_f32_le(frame + 32, st->ax);
        write_f32_le(frame + 36, st->ay);
        write_f32_le(frame + 40, st->az);
        ssize_t n = send(st->accel_fd, frame, sizeof(frame), MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n == (ssize_t)sizeof(frame)) {
            st->accel_seq = next_seq;
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            close(st->accel_fd);
            st->accel_fd = -1;
            st->accel_ready = 0;
        }
    }

    /* 2. Rotation Vector (/dev/unix/socket/qemu_sensor/rotation) */
    if (st->rot_fd < 0 && access(SENSOR_ROT_SOCK_PATH, F_OK) == 0) {
        st->rot_fd = connect_unix_nonblock(SENSOR_ROT_SOCK_PATH);
        st->rot_ready = 0;
    }
    if (st->rot_fd >= 0 && !st->rot_ready) {
        uint8_t hello[32];
        ssize_t n = recv(st->rot_fd, hello, sizeof(hello), MSG_DONTWAIT);
        if (n == 32 && memcmp(hello, "QRS1", 4) == 0 && read_le(hello + 4, 4) == 1) {
            memcpy(st->rot_nonce, hello + 8, 16);
            st->rot_seq = 0;
            st->rot_ready = 1;
        } else if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
            close(st->rot_fd);
            st->rot_fd = -1;
            st->rot_ready = 0;
        }
    }
    if (st->rot_fd >= 0 && st->rot_ready) {
        uint64_t next_seq = st->rot_seq + 1;
        uint8_t frame[48];
        memset(frame, 0, sizeof(frame));
        memcpy(frame, "QRF1", 4);
        write_le(frame + 4, 1, 4);
        memcpy(frame + 8, st->rot_nonce, 16);
        write_le(frame + 24, next_seq, 8);
        write_f32_le(frame + 32, st->rx);
        write_f32_le(frame + 36, st->ry);
        write_f32_le(frame + 40, st->rz);
        write_f32_le(frame + 44, st->rw);
        ssize_t n = send(st->rot_fd, frame, sizeof(frame), MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n == (ssize_t)sizeof(frame)) {
            st->rot_seq = next_seq;
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            close(st->rot_fd);
            st->rot_fd = -1;
            st->rot_ready = 0;
        }
    }

    /* 3. Head Posture (/dev/unix/socket/qemu_sensor/headposture) */
    if (st->head_fd < 0 && access(SENSOR_HEAD_SOCK_PATH, F_OK) == 0) {
        st->head_fd = connect_unix_nonblock(SENSOR_HEAD_SOCK_PATH);
        st->head_ready = 0;
    }
    if (st->head_fd >= 0 && !st->head_ready) {
        uint8_t hello[32];
        ssize_t n = recv(st->head_fd, hello, sizeof(hello), MSG_DONTWAIT);
        if (n == 32 && memcmp(hello, "QHP1", 4) == 0 && read_le(hello + 4, 4) == 1) {
            memcpy(st->head_nonce, hello + 8, 16);
            st->head_seq = 0;
            st->head_order = 0;
            st->head_ready = 1;
        } else if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
            close(st->head_fd);
            st->head_fd = -1;
            st->head_ready = 0;
        }
    }
    if (st->head_fd >= 0 && st->head_ready) {
        uint64_t next_seq = st->head_seq + 1;
        uint32_t next_order = (st->head_order < 16777200u) ? (st->head_order + 1u) : 1u;
        uint8_t frame[52];
        memset(frame, 0, sizeof(frame));
        memcpy(frame, "QHF1", 4);
        write_le(frame + 4, 1, 4);
        memcpy(frame + 8, st->head_nonce, 16);
        write_le(frame + 24, next_seq, 8);
        write_le(frame + 32, next_order, 4);
        write_f32_le(frame + 36, st->hw);
        write_f32_le(frame + 40, st->hx);
        write_f32_le(frame + 44, st->hy);
        write_f32_le(frame + 48, st->hz);
        ssize_t n = send(st->head_fd, frame, sizeof(frame), MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n == (ssize_t)sizeof(frame)) {
            st->head_seq = next_seq;
            st->head_order = next_order;
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            close(st->head_fd);
            st->head_fd = -1;
            st->head_ready = 0;
        }
    }
    save_sensor_state(st);
}

static void apply_battery_and_thermal_files(const bridge_state_t *st, int trigger_hidumper) {
    mkdir_p_one("/data/service", 0771);
    mkdir_p_one("/data/service/el0", 0771);
    mkdir_p_one("/data/service/el0/battery", 0755);
    mkdir_p_one("/data/service/el0/battery/battery", 0755);
    mkdir_p_one("/data/service/el0/battery/ohos_charger", 0755);
    mkdir_p_one("/data/service/el0/battery/ohos-fgu", 0755);
    mkdir_p_one("/data/service/el0/thermal", 0755);
    mkdir_p_one("/data/service/el0/thermal/sensor", 0755);
    mkdir_p_one("/data/service/el0/thermal/sensor/battery", 0755);

    char cap_str[32];
    snprintf(cap_str, sizeof(cap_str), "%d\n", st->battery_level);
    char temp_deci_str[32];
    snprintf(temp_deci_str, sizeof(temp_deci_str), "%d\n", (int)round(st->thermal_c * 10.0));
    char temp_milli_str[32];
    int temp_milli = (int)round(st->thermal_c * 1000.0);
    snprintf(temp_milli_str, sizeof(temp_milli_str), "%d\n", temp_milli);

    int is_online = (strcasecmp(st->battery_status, "Discharging") != 0) ? 1 : 0;
    const char *online_str = is_online ? "1\n" : "0\n";
    char status_nl[40];
    snprintf(status_nl, sizeof(status_nl), "%s\n", st->battery_status);

    write_file_inplace("/data/service/el0/battery/battery/capacity", cap_str);
    write_file_inplace("/data/service/el0/battery/battery/charge_control_limit", "0\n");
    write_file_inplace("/data/service/el0/battery/battery/charge_counter", "4000000\n");
    write_file_inplace("/data/service/el0/battery/battery/charge_full", "4000000\n");
    write_file_inplace("/data/service/el0/battery/battery/charge_now", "4000000\n");
    write_file_inplace("/data/service/el0/battery/battery/constant_charge_current", "0\n");
    write_file_inplace("/data/service/el0/battery/battery/current_avg", "1000\n");
    write_file_inplace("/data/service/el0/battery/battery/current_now", "1000\n");
    write_file_inplace("/data/service/el0/battery/battery/health", "Good\n");
    write_file_inplace("/data/service/el0/battery/battery/input_current_limit", "0\n");
    write_file_inplace("/data/service/el0/battery/battery/online", online_str);
    write_file_inplace("/data/service/el0/battery/battery/present", "1\n");
    write_file_inplace("/data/service/el0/battery/battery/status", status_nl);
    write_file_inplace("/data/service/el0/battery/battery/temp", temp_deci_str);
    write_file_inplace("/data/service/el0/battery/battery/voltage_avg", "4123456\n");
    write_file_inplace("/data/service/el0/battery/battery/voltage_now", "4123456\n");
    write_file_inplace("/data/service/el0/battery/battery/type", "Battery\n");
    write_file_inplace("/data/service/el0/battery/battery/technology", "Li-ion\n");

    write_file_inplace("/data/service/el0/battery/ohos_charger/type", "USB\n");
    write_file_inplace("/data/service/el0/battery/ohos_charger/constant_charge_current", "0\n");
    write_file_inplace("/data/service/el0/battery/ohos_charger/health", "Good\n");
    write_file_inplace("/data/service/el0/battery/ohos_charger/online", online_str);
    write_file_inplace("/data/service/el0/battery/ohos_charger/status", status_nl);

    write_file_inplace("/data/service/el0/battery/ohos-fgu/capacity", "1000\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/current_avg", "1000\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/current_now", "1000\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/health", "Good\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/present", "1\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/status", status_nl);
    write_file_inplace("/data/service/el0/battery/ohos-fgu/type", "Unknown\n");
    write_file_inplace("/data/service/el0/battery/ohos-fgu/temp", temp_deci_str);
    write_file_inplace("/data/service/el0/battery/ohos-fgu/technology", "Li-ion\n");

    write_file_inplace("/data/service/el0/thermal/sensor/battery/type", "battery\n");
    write_file_inplace("/data/service/el0/thermal/sensor/battery/temp", temp_milli_str);

    /* Also update kernel test_power module parameters if present */
    if (access("/sys/module/test_power/parameters/battery_capacity", W_OK) == 0) {
        write_file_inplace("/sys/module/test_power/parameters/battery_capacity", cap_str);
        const char *tp_status = "charging\n";
        if (strcasecmp(st->battery_status, "Discharging") == 0) tp_status = "discharging\n";
        else if (strcasecmp(st->battery_status, "Full") == 0) tp_status = "full\n";
        else if (strcasecmp(st->battery_status, "Not charging") == 0) tp_status = "not-charging\n";
        write_file_inplace("/sys/module/test_power/parameters/battery_status", tp_status);
        write_file_inplace("/sys/module/test_power/parameters/ac_online", is_online ? "on\n" : "off\n");
        write_file_inplace("/sys/module/test_power/parameters/usb_online", is_online ? "on\n" : "off\n");
    }

    if (trigger_hidumper) {
        int lvl = st->battery_level;
        int Discharging = !is_online;
        int do_thermal = st->thermal_custom;
        pid_t pid = fork();
        if (pid == 0) {
            alarm(6);
            int null_fd = open("/dev/null", O_RDWR);
            if (null_fd >= 0) {
                dup2(null_fd, STDOUT_FILENO);
                dup2(null_fd, STDERR_FILENO);
                if (null_fd > 2) close(null_fd);
            }
            char cmd[512];
            if (Discharging) {
                snprintf(cmd, sizeof(cmd),
                         "/system/bin/hidumper -s 3302 -a '-r'; "
                         "/system/bin/hidumper -s 3302 -a '-u'; "
                         "/system/bin/hidumper -s 3302 -a '--capacity %d'",
                         lvl);
            } else {
                snprintf(cmd, sizeof(cmd),
                         "/system/bin/hidumper -s 3302 -a '-r'; "
                         "/system/bin/hidumper -s 3302 -a '--capacity %d'",
                         lvl);
            }
            system(cmd);
            if (do_thermal) {
                snprintf(cmd, sizeof(cmd),
                         "/system/bin/hidumper -s 3303 -a '-st 0'; "
                         "/system/bin/hidumper -s 3303 -a '-te battery %d'",
                         temp_milli);
                system(cmd);
            }
            _exit(0);
        }
    }
}

static void parse_battery_spec(bridge_state_t *st, const char *spec, int is_custom) {
    char buf[64];
    strncpy(buf, spec, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    char *colon = strchr(buf, ':');
    if (colon) {
        *colon = '\0';
        const char *state = colon + 1;
        if (strcasecmp(state, "charging") == 0) {
            strcpy(st->battery_status, "Charging");
        } else if (strcasecmp(state, "discharging") == 0) {
            strcpy(st->battery_status, "Discharging");
        } else if (strcasecmp(state, "full") == 0) {
            strcpy(st->battery_status, "Full");
        } else if (strcasecmp(state, "not_charging") == 0 || strcasecmp(state, "not-charging") == 0) {
            strcpy(st->battery_status, "Not charging");
        }
    }
    int lvl = atoi(buf);
    if (lvl < 0) lvl = 0;
    if (lvl > 100) lvl = 100;
    st->battery_level = lvl;
    if (is_custom) {
        st->battery_custom = 1;
    }
}

static int apply_camera_pattern(const char *pattern_spec) {
    int pattern_id = 0;
    int hor_move = 0;
    int vert_move = 0;
    int show_border = 1;
    int show_square = 1;
    int osd_mode = 1; /* Counters Only by default */

    if (isdigit((unsigned char)pattern_spec[0])) {
        pattern_id = atoi(pattern_spec);
    } else if (strncasecmp(pattern_spec, "bars", 4) == 0 || strncasecmp(pattern_spec, "colorbars", 9) == 0) {
        pattern_id = 0; /* 75% Colorbars */
    } else if (strncasecmp(pattern_spec, "smpte", 5) == 0 || strncasecmp(pattern_spec, "100bars", 7) == 0) {
        pattern_id = 1; /* 100% Colorbars */
    } else if (strncasecmp(pattern_spec, "csc", 3) == 0) {
        pattern_id = 2; /* CSC Colorbars */
    } else if (strncasecmp(pattern_spec, "hbars", 5) == 0) {
        pattern_id = 3; /* Horizontal 100% Colorbars */
    } else if (strncasecmp(pattern_spec, "squares", 7) == 0) {
        pattern_id = 4; /* 100% Color Squares */
    } else if (strncasecmp(pattern_spec, "black", 5) == 0) {
        pattern_id = 5;
    } else if (strncasecmp(pattern_spec, "white", 5) == 0) {
        pattern_id = 6;
    } else if (strncasecmp(pattern_spec, "red", 3) == 0) {
        pattern_id = 7;
    } else if (strncasecmp(pattern_spec, "green", 5) == 0) {
        pattern_id = 8;
    } else if (strncasecmp(pattern_spec, "blue", 4) == 0) {
        pattern_id = 9;
    } else if (strncasecmp(pattern_spec, "checkers", 8) == 0) {
        pattern_id = 10; /* 16x16 Checkers */
    } else if (strncasecmp(pattern_spec, "cross", 5) == 0) {
        pattern_id = 17; /* Ten Pixels Wide Cross */
    } else if (strncasecmp(pattern_spec, "ramp", 4) == 0 || strncasecmp(pattern_spec, "gray", 4) == 0) {
        pattern_id = 18; /* Gray Ramp */
    } else if (strncasecmp(pattern_spec, "noise", 5) == 0) {
        pattern_id = 19; /* Noise */
    } else if (strncasecmp(pattern_spec, "moving", 6) == 0) {
        pattern_id = 0;
        hor_move = 4;
        vert_move = 4;
    }
    if (strstr(pattern_spec, ":move") || strstr(pattern_spec, ",move")) {
        hor_move = 4;
        vert_move = 4;
    }

    int applied = 0;
    for (int i = 0; i < 4; ++i) {
        char devpath[32];
        snprintf(devpath, sizeof(devpath), "/dev/video%d", i);
        int fd = open(devpath, O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        struct v4l2_capability cap;
        memset(&cap, 0, sizeof(cap));
        if (ioctl(fd, VIDIOC_QUERYCAP, &cap) == 0 && strcmp((const char *)cap.driver, "vivid") == 0) {
            struct v4l2_control ctrl;
            ctrl.id = VIVID_CID_TEST_PATTERN;
            ctrl.value = pattern_id;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            ctrl.id = VIVID_CID_HOR_MOVEMENT;
            ctrl.value = hor_move;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            ctrl.id = VIVID_CID_VERT_MOVEMENT;
            ctrl.value = vert_move;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            ctrl.id = VIVID_CID_SHOW_BORDER;
            ctrl.value = show_border;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            ctrl.id = VIVID_CID_SHOW_SQUARE;
            ctrl.value = show_square;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            ctrl.id = VIVID_CID_OSD_TEXT_MODE;
            ctrl.value = osd_mode;
            ioctl(fd, VIDIOC_S_CTRL, &ctrl);
            applied = 1;
        }
        close(fd);
        if (applied) break;
    }
    return applied ? 0 : -1;
}

/* Clipboard via libpasteboard.so + libudmf.so + file mirror */
typedef void *(*fn_pb_create_t)(void);
typedef void (*fn_pb_destroy_t)(void *);
typedef int (*fn_pb_set_data_t)(void *, void *);
typedef void *(*fn_pb_get_data_t)(void *, int *);
typedef void *(*fn_udmf_data_create_t)(void);
typedef void (*fn_udmf_data_destroy_t)(void *);
typedef int (*fn_udmf_data_add_record_t)(void *, void *);
typedef void **(*fn_udmf_data_get_records_t)(void *, unsigned int *);
typedef void *(*fn_udmf_rec_create_t)(void);
typedef void (*fn_udmf_rec_destroy_t)(void *);
typedef int (*fn_udmf_rec_add_plain_t)(void *, void *);
typedef int (*fn_udmf_rec_get_plain_t)(void *, void *);
typedef void *(*fn_uds_plain_create_t)(void);
typedef void (*fn_uds_plain_destroy_t)(void *);
typedef int (*fn_uds_plain_set_content_t)(void *, const char *);
typedef const char *(*fn_uds_plain_get_content_t)(void *);

static void set_guest_clipboard(const char *text) {
    mkdir_p_one("/data/service/el1/public", 0775);
    write_file_inplace(CLIPBOARD_FILE, text);

    pid_t pid = fork();
    if (pid == 0) {
        alarm(3);
        void *h_pb = dlopen("libpasteboard.so", RTLD_LAZY);
        void *h_udmf = dlopen("libudmf.so", RTLD_LAZY);
        if (!h_pb) h_pb = dlopen("/system/lib64/ndk/libpasteboard.so", RTLD_LAZY);
        if (!h_pb) h_pb = dlopen("/system/lib/ndk/libpasteboard.so", RTLD_LAZY);
        if (!h_udmf) h_udmf = dlopen("/system/lib64/ndk/libudmf.so", RTLD_LAZY);
        if (!h_udmf) h_udmf = dlopen("/system/lib/ndk/libudmf.so", RTLD_LAZY);
        if (h_pb && h_udmf) {
            fn_pb_create_t pb_create = (fn_pb_create_t)dlsym(h_pb, "OH_Pasteboard_Create");
            fn_pb_destroy_t pb_destroy = (fn_pb_destroy_t)dlsym(h_pb, "OH_Pasteboard_Destroy");
            fn_pb_set_data_t pb_set = (fn_pb_set_data_t)dlsym(h_pb, "OH_Pasteboard_SetData");
            fn_udmf_data_create_t data_create = (fn_udmf_data_create_t)dlsym(h_udmf, "OH_UdmfData_Create");
            fn_udmf_data_destroy_t data_destroy = (fn_udmf_data_destroy_t)dlsym(h_udmf, "OH_UdmfData_Destroy");
            fn_udmf_data_add_record_t data_add = (fn_udmf_data_add_record_t)dlsym(h_udmf, "OH_UdmfData_AddRecord");
            fn_udmf_rec_create_t rec_create = (fn_udmf_rec_create_t)dlsym(h_udmf, "OH_UdmfRecord_Create");
            fn_udmf_rec_destroy_t rec_destroy = (fn_udmf_rec_destroy_t)dlsym(h_udmf, "OH_UdmfRecord_Destroy");
            fn_udmf_rec_add_plain_t rec_add_plain = (fn_udmf_rec_add_plain_t)dlsym(h_udmf, "OH_UdmfRecord_AddPlainText");
            fn_uds_plain_create_t plain_create = (fn_uds_plain_create_t)dlsym(h_udmf, "OH_UdsPlainText_Create");
            fn_uds_plain_destroy_t plain_destroy = (fn_uds_plain_destroy_t)dlsym(h_udmf, "OH_UdsPlainText_Destroy");
            fn_uds_plain_set_content_t plain_set = (fn_uds_plain_set_content_t)dlsym(h_udmf, "OH_UdsPlainText_SetContent");

            if (pb_create && pb_destroy && pb_set && data_create && data_destroy && data_add &&
                rec_create && rec_destroy && rec_add_plain && plain_create && plain_destroy && plain_set) {
                void *pb = pb_create();
                void *udata = data_create();
                void *urec = rec_create();
                void *uplain = plain_create();
                if (pb && udata && urec && uplain) {
                    plain_set(uplain, text);
                    rec_add_plain(urec, uplain);
                    data_add(udata, urec);
                    pb_set(pb, udata);
                }
                if (uplain) plain_destroy(uplain);
                if (urec) rec_destroy(urec);
                if (udata) data_destroy(udata);
                if (pb) pb_destroy(pb);
            }
        }
        _exit(0);
    }
}

static size_t get_guest_clipboard(char *out, size_t out_cap) {
    out[0] = '\0';
    int pipefd[2];
    if (pipe(pipefd) == 0) {
        pid_t pid = fork();
        if (pid == 0) {
            close(pipefd[0]);
            alarm(2);
            void *h_pb = dlopen("libpasteboard.so", RTLD_LAZY);
            void *h_udmf = dlopen("libudmf.so", RTLD_LAZY);
            if (!h_pb) h_pb = dlopen("/system/lib64/ndk/libpasteboard.so", RTLD_LAZY);
            if (!h_pb) h_pb = dlopen("/system/lib/ndk/libpasteboard.so", RTLD_LAZY);
            if (!h_udmf) h_udmf = dlopen("/system/lib64/ndk/libudmf.so", RTLD_LAZY);
            if (!h_udmf) h_udmf = dlopen("/system/lib/ndk/libudmf.so", RTLD_LAZY);
            if (h_pb && h_udmf) {
                fn_pb_create_t pb_create = (fn_pb_create_t)dlsym(h_pb, "OH_Pasteboard_Create");
                fn_pb_destroy_t pb_destroy = (fn_pb_destroy_t)dlsym(h_pb, "OH_Pasteboard_Destroy");
                fn_pb_get_data_t pb_get = (fn_pb_get_data_t)dlsym(h_pb, "OH_Pasteboard_GetData");
                fn_udmf_data_destroy_t data_destroy = (fn_udmf_data_destroy_t)dlsym(h_udmf, "OH_UdmfData_Destroy");
                fn_udmf_data_get_records_t data_get_recs = (fn_udmf_data_get_records_t)dlsym(h_udmf, "OH_UdmfData_GetRecords");
                fn_udmf_rec_get_plain_t rec_get_plain = (fn_udmf_rec_get_plain_t)dlsym(h_udmf, "OH_UdmfRecord_GetPlainText");
                fn_uds_plain_create_t plain_create = (fn_uds_plain_create_t)dlsym(h_udmf, "OH_UdsPlainText_Create");
                fn_uds_plain_destroy_t plain_destroy = (fn_uds_plain_destroy_t)dlsym(h_udmf, "OH_UdsPlainText_Destroy");
                fn_uds_plain_get_content_t plain_get = (fn_uds_plain_get_content_t)dlsym(h_udmf, "OH_UdsPlainText_GetContent");

                if (pb_create && pb_destroy && pb_get && data_destroy && data_get_recs &&
                    rec_get_plain && plain_create && plain_destroy && plain_get) {
                    void *pb = pb_create();
                    int status = -1;
                    void *udata = pb ? pb_get(pb, &status) : NULL;
                    if (udata && status == 0) {
                        unsigned int count = 0;
                        void **recs = data_get_recs(udata, &count);
                        if (recs && count > 0) {
                            void *uplain = plain_create();
                            if (uplain && rec_get_plain(recs[0], uplain) == 0) {
                                const char *content = plain_get(uplain);
                                if (content && content[0]) {
                                    write(pipefd[1], content, strlen(content));
                                }
                            }
                            if (uplain) plain_destroy(uplain);
                        }
                    }
                    if (udata) data_destroy(udata);
                    if (pb) pb_destroy(pb);
                }
            }
            close(pipefd[1]);
            _exit(0);
        }
        close(pipefd[1]);
        ssize_t n = read(pipefd[0], out, out_cap - 1);
        close(pipefd[0]);
        int wstatus = 0;
        waitpid(pid, &wstatus, 0);
        if (n > 0) {
            out[n] = '\0';
            write_file_inplace(CLIPBOARD_FILE, out);
            return (size_t)n;
        }
    }
    int fd = open(CLIPBOARD_FILE, O_RDONLY | O_CLOEXEC);
    if (fd >= 0) {
        ssize_t n = read(fd, out, out_cap - 1);
        close(fd);
        if (n > 0) {
            out[n] = '\0';
            return (size_t)n;
        }
    }
    return 0;
}

static int find_virtserial_port(const char *port_name) {
    DIR *dir = opendir("/sys/class/virtio-ports");
    if (!dir) {
        return -1;
    }
    struct dirent *ent;
    char devpath[128] = {0};
    while ((ent = readdir(dir)) != NULL) {
        if (strncmp(ent->d_name, "vport", 5) != 0) {
            continue;
        }
        char name_file[256];
        snprintf(name_file, sizeof(name_file), "/sys/class/virtio-ports/%s/name", ent->d_name);
        int fd = open(name_file, O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;
        char buf[128] = {0};
        ssize_t n = read(fd, buf, sizeof(buf) - 1);
        close(fd);
        if (n <= 0) continue;
        buf[strcspn(buf, "\r\n")] = '\0';
        if (strcmp(buf, port_name) == 0) {
            snprintf(devpath, sizeof(devpath), "/dev/%s", ent->d_name);
            break;
        }
    }
    closedir(dir);
    if (!devpath[0]) {
        return -1;
    }
    return open(devpath, O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
}

static void parse_cmdline(bridge_state_t *st) {
    int fd = open("/proc/cmdline", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return;
    char cmdline[4096] = {0};
    ssize_t n = read(fd, cmdline, sizeof(cmdline) - 1);
    close(fd);
    if (n <= 0) return;

    char *saveptr = NULL;
    for (char *tok = strtok_r(cmdline, " \t\r\n", &saveptr); tok; tok = strtok_r(NULL, " \t\r\n", &saveptr)) {
        if (strncmp(tok, "ohos.boot.qemu.gps=", 19) == 0) {
            const char *val = tok + 19;
            double lat = 39.9042, lon = 116.4074, alt = 50.0;
            float speed = 0.0f, bearing = 0.0f, hacc = 5.0f, vacc = 5.0f;
            int fields = sscanf(val, "%lf,%lf,%lf,%f,%f,%f,%f", &lat, &lon, &alt, &speed, &bearing, &hacc, &vacc);
            if (fields >= 2) {
                st->lat = lat;
                st->lon = lon;
                st->alt = alt;
                st->speed = speed;
                st->bearing = bearing;
                st->hacc = hacc > 0.0f ? hacc : 5.0f;
                st->vacc = vacc >= 0.0f ? vacc : 5.0f;
                st->gnss_enabled = 1;
            }
        } else if (strncmp(tok, "ohos.boot.qemu.sensor=", 22) == 0) {
            const char *val = tok + 22;
            float ax = 0.0f, ay = 9.8f, az = 0.0f;
            float rx = 0.0f, ry = 0.0f, rz = 0.0f, rw = 1.0f;
            int fields = sscanf(val, "%f,%f,%f:%f,%f,%f,%f", &ax, &ay, &az, &rx, &ry, &rz, &rw);
            if (fields >= 3) {
                st->ax = ax;
                st->ay = ay;
                st->az = az;
                if (fields == 7) {
                    normalize_quat(&rx, &ry, &rz, &rw);
                    st->rx = rx;
                    st->ry = ry;
                    st->rz = rz;
                    st->rw = rw;
                }
                st->sensor_enabled = 1;
            }
        } else if (strncmp(tok, "ohos.boot.qemu.battery=", 23) == 0) {
            parse_battery_spec(st, tok + 23, 1);
        } else if (strncmp(tok, "ohos.boot.qemu.thermal=", 23) == 0) {
            st->thermal_c = atof(tok + 23);
            st->thermal_custom = 1;
        } else if (strncmp(tok, "ohos.boot.qemu.camera=", 22) == 0) {
            strncpy(st->camera_pattern, tok + 22, sizeof(st->camera_pattern) - 1);
            st->camera_custom = 1;
        }
    }
}

static void handle_command_line(bridge_state_t *st, const char *line_in, int reply_fd) {
    char line[4096];
    strncpy(line, line_in, sizeof(line) - 1);
    line[sizeof(line) - 1] = '\0';
    line[strcspn(line, "\r\n")] = '\0';
    if (!line[0]) return;

    char reply[4600];
    reply[0] = '\0';

    if (strncasecmp(line, "GPS ", 4) == 0) {
        const char *val = line + 4;
        while (*val == ' ') ++val;
        if (strcasecmp(val, "off") == 0) {
            st->gnss_enabled = 0;
            if (st->gnss_fd >= 0) {
                close(st->gnss_fd);
                st->gnss_fd = -1;
            }
            st->gnss_ready = 0;
            save_gnss_state(st);
            snprintf(reply, sizeof(reply), "OK GPS off\n");
        } else {
            double lat = st->lat, lon = st->lon, alt = st->alt;
            float speed = st->speed, bearing = st->bearing, hacc = st->hacc, vacc = st->vacc;
            int fields = sscanf(val, "%lf,%lf,%lf,%f,%f,%f,%f", &lat, &lon, &alt, &speed, &bearing, &hacc, &vacc);
            if (fields >= 2) {
                st->lat = lat;
                st->lon = lon;
                st->alt = alt;
                st->speed = speed;
                st->bearing = bearing;
                st->hacc = hacc > 0.0f ? hacc : 5.0f;
                st->vacc = vacc >= 0.0f ? vacc : 5.0f;
                st->gnss_enabled = 1;
                send_gnss_frame(st);
                snprintf(reply, sizeof(reply), "OK GPS %.6f,%.6f,%.2f seq=%llu\n",
                         st->lat, st->lon, st->alt, (unsigned long long)st->gnss_seq);
            } else {
                snprintf(reply, sizeof(reply), "ERR GPS invalid format\n");
            }
        }
    } else if (strncasecmp(line, "ACCEL ", 6) == 0 || strncasecmp(line, "SENSOR ", 7) == 0) {
        const char *val = strchr(line, ' ') + 1;
        while (*val == ' ') ++val;
        float ax = st->ax, ay = st->ay, az = st->az;
        if (sscanf(val, "%f,%f,%f", &ax, &ay, &az) == 3) {
            st->ax = ax;
            st->ay = ay;
            st->az = az;
            st->sensor_enabled = 1;
            send_sensor_frames(st);
            snprintf(reply, sizeof(reply), "OK ACCEL %.4f,%.4f,%.4f seq=%llu\n",
                     st->ax, st->ay, st->az, (unsigned long long)st->accel_seq);
        } else {
            snprintf(reply, sizeof(reply), "ERR ACCEL invalid format\n");
        }
    } else if (strncasecmp(line, "ROTATION ", 9) == 0) {
        const char *val = line + 9;
        while (*val == ' ') ++val;
        float rx = 0.0f, ry = 0.0f, rz = 0.0f, rw = 1.0f;
        if (sscanf(val, "%f,%f,%f,%f", &rx, &ry, &rz, &rw) == 4) {
            normalize_quat(&rx, &ry, &rz, &rw);
            st->rx = rx;
            st->ry = ry;
            st->rz = rz;
            st->rw = rw;
            st->sensor_enabled = 1;
            send_sensor_frames(st);
            snprintf(reply, sizeof(reply), "OK ROTATION %.4f,%.4f,%.4f,%.4f seq=%llu\n",
                     st->rx, st->ry, st->rz, st->rw, (unsigned long long)st->rot_seq);
        } else {
            snprintf(reply, sizeof(reply), "ERR ROTATION invalid format\n");
        }
    } else if (strncasecmp(line, "HEADPOSTURE ", 12) == 0) {
        const char *val = line + 12;
        while (*val == ' ') ++val;
        float hw = 1.0f, hx = 0.0f, hy = 0.0f, hz = 0.0f;
        if (sscanf(val, "%f,%f,%f,%f", &hw, &hx, &hy, &hz) == 4) {
            normalize_quat(&hx, &hy, &hz, &hw);
            st->hw = hw;
            st->hx = hx;
            st->hy = hy;
            st->hz = hz;
            st->sensor_enabled = 1;
            send_sensor_frames(st);
            snprintf(reply, sizeof(reply), "OK HEADPOSTURE %.4f,%.4f,%.4f,%.4f seq=%llu\n",
                     st->hw, st->hx, st->hy, st->hz, (unsigned long long)st->head_seq);
        } else {
            snprintf(reply, sizeof(reply), "ERR HEADPOSTURE invalid format\n");
        }
    } else if (strncasecmp(line, "BATTERY ", 8) == 0) {
        const char *val = line + 8;
        while (*val == ' ') ++val;
        parse_battery_spec(st, val, 1);
        apply_battery_and_thermal_files(st, 1);
        snprintf(reply, sizeof(reply), "OK BATTERY %d:%s\n", st->battery_level, st->battery_status);
    } else if (strncasecmp(line, "THERMAL ", 8) == 0) {
        const char *val = line + 8;
        while (*val == ' ') ++val;
        st->thermal_c = atof(val);
        st->thermal_custom = 1;
        apply_battery_and_thermal_files(st, 1);
        snprintf(reply, sizeof(reply), "OK THERMAL %.1f\n", st->thermal_c);
    } else if (strncasecmp(line, "CAMERA ", 7) == 0) {
        const char *val = line + 7;
        while (*val == ' ') ++val;
        strncpy(st->camera_pattern, val, sizeof(st->camera_pattern) - 1);
        st->camera_custom = 1;
        int rc = apply_camera_pattern(st->camera_pattern);
        snprintf(reply, sizeof(reply), "%s CAMERA %s\n", rc == 0 ? "OK" : "WARN", st->camera_pattern);
    } else if (strncasecmp(line, "CLIPBOARD_SET_B64 ", 18) == 0) {
        const char *b64 = line + 18;
        while (*b64 == ' ') ++b64;
        uint8_t decoded[3072];
        size_t len = b64_decode(b64, decoded, sizeof(decoded));
        set_guest_clipboard((const char *)decoded);
        snprintf(reply, sizeof(reply), "OK CLIPBOARD_SET %zu\n", len);
    } else if (strncasecmp(line, "CLIPBOARD_SET ", 14) == 0) {
        const char *txt = line + 14;
        set_guest_clipboard(txt);
        snprintf(reply, sizeof(reply), "OK CLIPBOARD_SET %zu\n", strlen(txt));
    } else if (strcasecmp(line, "CLIPBOARD_GET") == 0) {
        char raw[2048];
        size_t len = get_guest_clipboard(raw, sizeof(raw));
        char b64[3072];
        b64_encode((const uint8_t *)raw, len, b64, sizeof(b64));
        snprintf(reply, sizeof(reply), "CLIPBOARD_B64 %s\n", b64);
    } else if (strncasecmp(line, "TIME ", 5) == 0) {
        uint64_t epoch_ms = strtoull(line + 5, NULL, 10);
        if (epoch_ms > 1700000000000ULL) {
            struct timespec ts;
            ts.tv_sec = (time_t)(epoch_ms / 1000ULL);
            ts.tv_nsec = (long)((epoch_ms % 1000ULL) * 1000000ULL);
            clock_settime(CLOCK_REALTIME, &ts);
            snprintf(reply, sizeof(reply), "OK TIME %llu\n", (unsigned long long)epoch_ms);
        } else {
            snprintf(reply, sizeof(reply), "ERR TIME invalid epoch_ms\n");
        }
    } else if (strcasecmp(line, "STATUS") == 0 || strcasecmp(line, "PING") == 0) {
        snprintf(reply, sizeof(reply),
                 "OK STATUS gnss=%d(ready=%d,seq=%llu,lat=%.4f,lon=%.4f) "
                 "sensor=%d(accel_ready=%d,seq=%llu,rot_ready=%d,head_ready=%d) "
                 "battery=%d:%s thermal=%.1fC camera=%s\n",
                 st->gnss_enabled, st->gnss_ready, (unsigned long long)st->gnss_seq, st->lat, st->lon,
                 st->sensor_enabled, st->accel_ready, (unsigned long long)st->accel_seq, st->rot_ready, st->head_ready,
                 st->battery_level, st->battery_status, st->thermal_c, st->camera_pattern);
    } else {
        snprintf(reply, sizeof(reply), "ERR unknown command: %s\n", line);
    }

    if (reply_fd >= 0 && reply[0]) {
        write(reply_fd, reply, strlen(reply));
    }
}

static int run_client_command(int argc, char **argv) {
    char cmd[2048] = {0};
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--cmd") == 0) continue;
        if (cmd[0]) strncat(cmd, " ", sizeof(cmd) - strlen(cmd) - 1);
        strncat(cmd, argv[i], sizeof(cmd) - strlen(cmd) - 1);
    }
    strncat(cmd, "\n", sizeof(cmd) - strlen(cmd) - 1);

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, CONTROL_SOCK_PATH, sizeof(addr.sun_path) - 1);
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect " CONTROL_SOCK_PATH);
        close(fd);
        return 1;
    }
    write(fd, cmd, strlen(cmd));
    char resp[4096] = {0};
    ssize_t n = read(fd, resp, sizeof(resp) - 1);
    close(fd);
    if (n > 0) {
        resp[n] = '\0';
        fputs(resp, stdout);
        return strncmp(resp, "ERR", 3) == 0 ? 1 : 0;
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "--daemon") != 0) {
        return run_client_command(argc, argv);
    }

    signal(SIGPIPE, SIG_IGN);
    signal(SIGCHLD, SIG_IGN);
    signal(SIGHUP, SIG_IGN);
    setsid();

    mkdir_p_one("/data/vendor", 0771);
    const char *pid_path = "/data/vendor/qemu_hw_bridge.pid";
    FILE *pf = fopen(pid_path, "r");
    if (pf) {
        int old_pid = 0;
        if (fscanf(pf, "%d", &old_pid) == 1 && old_pid > 1 && old_pid != (int)getpid()) {
            if (kill(old_pid, 0) == 0) {
                fclose(pf);
                return 0;
            }
        }
        fclose(pf);
    }
    pf = fopen(pid_path, "w");
    if (pf) {
        fprintf(pf, "%d\n", (int)getpid());
        fclose(pf);
    }

    bridge_state_t st;
    memset(&st, 0, sizeof(st));
    st.gnss_fd = -1;
    st.accel_fd = -1;
    st.rot_fd = -1;
    st.head_fd = -1;
    st.vport_fd = -1;
    st.ctrl_listen_fd = -1;

    /* Default values across all 6 images */
    st.lat = 39.9042;
    st.lon = 116.4074;
    st.alt = 50.0;
    st.hacc = 5.0f;
    st.vacc = 5.0f;
    st.speed = 0.0f;
    st.bearing = 0.0f;

    st.sensor_enabled = 1;
    st.ax = 0.0f;
    st.ay = 9.8f;
    st.az = 0.0f;
    st.rx = 0.0f;
    st.ry = 0.0f;
    st.rz = 0.0f;
    st.rw = 1.0f;
    st.hw = 1.0f;
    st.hx = 0.0f;
    st.hy = 0.0f;
    st.hz = 0.0f;

    st.battery_level = 100;
    strcpy(st.battery_status, "Charging");
    st.thermal_c = 25.0;
    strcpy(st.camera_pattern, "bars");

    parse_cmdline(&st);

    /* Apply initial battery, thermal, camera, and sensor/gnss state immediately */
    apply_battery_and_thermal_files(&st, 0);
    if (st.camera_custom) {
        apply_camera_pattern(st.camera_pattern);
    }
    save_gnss_state(&st);
    save_sensor_state(&st);

    /* Create local UNIX control socket /data/vendor/qemu_hw_bridge.sock */
    mkdir_p_one("/data/vendor", 0771);
    unlink(CONTROL_SOCK_PATH);
    st.ctrl_listen_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (st.ctrl_listen_fd >= 0) {
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, CONTROL_SOCK_PATH, sizeof(addr.sun_path) - 1);
        if (bind(st.ctrl_listen_fd, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
            chmod(CONTROL_SOCK_PATH, 0660);
            listen(st.ctrl_listen_fd, 8);
        } else {
            close(st.ctrl_listen_fd);
            st.ctrl_listen_fd = -1;
        }
    }

    uint64_t last_gnss_tick = 0;
    uint64_t last_sensor_tick = 0;
    uint64_t last_boot_sync_tick = 0;
    uint64_t start_mono = now_monotonic_ms();
    char vport_buf[4096];
    size_t vport_len = 0;

    while (1) {
        if (st.vport_fd < 0) {
            st.vport_fd = find_virtserial_port("ohos.hw.bridge0");
            if (st.vport_fd >= 0) {
                const char *hello = "HELLO qemu-hw-bridge\n";
                (void)write(st.vport_fd, hello, strlen(hello));
            }
        }

        struct pollfd pfds[2];
        int nfds = 0;
        if (st.vport_fd >= 0) {
            pfds[nfds].fd = st.vport_fd;
            pfds[nfds].events = POLLIN;
            pfds[nfds].revents = 0;
            nfds++;
        }
        if (st.ctrl_listen_fd >= 0) {
            pfds[nfds].fd = st.ctrl_listen_fd;
            pfds[nfds].events = POLLIN;
            pfds[nfds].revents = 0;
            nfds++;
        }

        if (nfds > 0) {
            poll(pfds, nfds, 200);
        } else {
            usleep(200000);
        }

        /* Check virtserial port input */
        if (st.vport_fd >= 0) {
            ssize_t n = read(st.vport_fd, vport_buf + vport_len, sizeof(vport_buf) - 1 - vport_len);
            if (n > 0) {
                vport_len += (size_t)n;
                vport_buf[vport_len] = '\0';
                char *line_start = vport_buf;
                char *nl = NULL;
                while ((nl = strchr(line_start, '\n')) != NULL) {
                    *nl = '\0';
                    handle_command_line(&st, line_start, st.vport_fd);
                    line_start = nl + 1;
                }
                size_t rem = strlen(line_start);
                if (rem > 0 && line_start != vport_buf) {
                    memmove(vport_buf, line_start, rem);
                }
                vport_len = rem;
                if (vport_len >= sizeof(vport_buf) - 2) {
                    vport_len = 0;
                }
            } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                close(st.vport_fd);
                st.vport_fd = -1;
                vport_len = 0;
            }
        }

        /* Check local control socket connections */
        if (st.ctrl_listen_fd >= 0) {
            int cfd = accept4(st.ctrl_listen_fd, NULL, NULL, SOCK_CLOEXEC);
            if (cfd >= 0) {
                struct pollfd cpfd = {.fd = cfd, .events = POLLIN, .revents = 0};
                if (poll(&cpfd, 1, 500) > 0) {
                    char cbuf[2048] = {0};
                    ssize_t cn = read(cfd, cbuf, sizeof(cbuf) - 1);
                    if (cn > 0) {
                        cbuf[cn] = '\0';
                        handle_command_line(&st, cbuf, cfd);
                    }
                }
                close(cfd);
            }
        }

        uint64_t now_ms = now_monotonic_ms();

        /* Periodic sensor frames (every 200ms) */
        if (now_ms - last_sensor_tick >= 200) {
            last_sensor_tick = now_ms;
            send_sensor_frames(&st);
        }

        /* Periodic GNSS frames (every 1000ms) */
        if (now_ms - last_gnss_tick >= 1000) {
            last_gnss_tick = now_ms;
            send_gnss_frame(&st);
        }

        /* Periodically ensure battery/thermal files stay populated during boot; only run hidumper once if custom */
        if (!st.battery_synced_after_boot && (now_ms - last_boot_sync_tick >= 5000)) {
            last_boot_sync_tick = now_ms;
            int notify = 0;
            if ((st.battery_custom || st.thermal_custom) && (now_ms - start_mono >= 30000)) {
                notify = 1;
                st.battery_synced_after_boot = 1;
            } else if (now_ms - start_mono >= 60000) {
                st.battery_synced_after_boot = 1;
            }
            apply_battery_and_thermal_files(&st, notify);
        }
    }
    return 0;
}
