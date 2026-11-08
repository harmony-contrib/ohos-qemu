/*
 * Virtual Bluetooth HCI Vendor Library (libbt_vendor.z.so) for OpenHarmony QEMU.
 *
 * Self-containedfreestanding shared library implementing BLUETOOTH_VENDOR_LIB_INTERFACE
 * (BtVendorInterfaceT) expected by drivers/peripheral/bluetooth/hci/hdi_service (blue_host).
 * Provides an in-process H4 HCI virtual controller over socketpair() so
 * VendorInterface::Initialize() and the OpenHarmony Bluetooth stack complete
 * HCI bring-up cleanly in QEMU.
 */

typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef __SIZE_TYPE__ size_t;
typedef __PTRDIFF_TYPE__ ssize_t;
typedef __INTPTR_TYPE__ intptr_t;
typedef void *pthread_t;

#define NULL ((void *)0)
#define EINTR 4
#define AF_UNIX 1
#define SOCK_STREAM 1
#define SHUT_RDWR 2

extern int *__errno_location(void);
#define errno (*__errno_location())

extern void *memcpy(void *dst, const void *src, size_t n);
extern void *memset(void *s, int c, size_t n);
extern ssize_t read(int fd, void *buf, size_t count);
extern ssize_t write(int fd, const void *buf, size_t count);
extern int close(int fd);
extern int socketpair(int domain, int type, int protocol, int sv[2]);
extern int shutdown(int sockfd, int how);
extern int pthread_create(pthread_t *thread, const void *attr, void *(*start_routine)(void *), void *arg);
extern int pthread_join(pthread_t thread, void **retval);

typedef struct {
    long fds_bits[1024 / (8 * sizeof(long))];
} ohos_fd_set;

struct ohos_timeval {
    long tv_sec;
    long tv_usec;
};

extern int select(int nfds, ohos_fd_set *readfds, ohos_fd_set *writefds, ohos_fd_set *exceptfds,
                  struct ohos_timeval *timeout);

static void fd_zero(ohos_fd_set *set)
{
    memset(set, 0, sizeof(*set));
}

static void fd_set_bit(int fd, ohos_fd_set *set)
{
    int bits_per_word = (int)(8 * sizeof(long));
    set->fds_bits[fd / bits_per_word] |= (1UL << (fd % bits_per_word));
}

typedef enum {
    BT_OP_POWER_ON = 0,
    BT_OP_POWER_OFF,
    BT_OP_HCI_CHANNEL_OPEN,
    BT_OP_HCI_CHANNEL_CLOSE,
    BT_OP_INIT,
    BT_OP_GET_LPM_TIMER,
    BT_OP_LPM_ENABLE,
    BT_OP_LPM_DISABLE,
    BT_OP_WAKEUP_LOCK,
    BT_OP_WAKEUP_UNLOCK,
    BT_OP_EVENT_CALLBACK
} BtOpcodeT;

typedef enum {
    BTC_OP_RESULT_SUCCESS = 0,
    BTC_OP_RESULT_FAIL,
} BtOpResultT;

typedef void *(*MallocCallback)(int size);
typedef void (*FreeCallback)(void *buf);
typedef size_t (*CmdXmitCallback)(uint16_t opcode, void *pbuf);
typedef void (*InitCallback)(BtOpResultT result);

typedef struct {
    size_t size;
    MallocCallback malloc_cb;
    FreeCallback free_cb;
    CmdXmitCallback cmd_xmit_cb;
    InitCallback init_cb;
} BtVendorCallbacksT;

typedef struct {
    size_t size;
    int (*init)(const BtVendorCallbacksT *callbacks, unsigned char *localBdaddr);
    int (*op)(BtOpcodeT opcode, void *param);
    void (*close)(void);
} BtVendorInterfaceT;

#define HCI_PACKET_TYPE_COMMAND 0x01
#define HCI_PACKET_TYPE_ACL_DATA 0x02
#define HCI_PACKET_TYPE_SCO_DATA 0x03
#define HCI_PACKET_TYPE_EVENT 0x04
#define HCI_PACKET_TYPE_ISO_DATA 0x05

#define HCI_EVENT_INQUIRY_COMPLETE 0x01
#define HCI_EVENT_COMMAND_COMPLETE 0x0E
#define HCI_EVENT_COMMAND_STATUS 0x0F

static const BtVendorCallbacksT *g_callbacks = NULL;
static uint8_t g_bdaddr[6] = {0x66, 0x55, 0x44, 0x33, 0x22, 0x22};
static uint8_t g_local_name[248] = "OpenHarmony QEMU BT";
static uint8_t g_class_of_device[3] = {0x0C, 0x02, 0x5A};
static uint8_t g_scan_enable = 0x00;
static int g_sv[2] = {-1, -1};
static volatile int g_running = 0;
static pthread_t g_worker_thread = NULL;
static int g_thread_started = 0;

static int write_all(int fd, const uint8_t *buf, size_t len)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, buf + off, len - off);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (n == 0) {
            return -1;
        }
        off += (size_t)n;
    }
    return 0;
}

static int read_exact(int fd, uint8_t *buf, size_t len)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = read(fd, buf + off, len - off);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (n == 0) {
            return -1;
        }
        off += (size_t)n;
    }
    return 0;
}

static void send_cmd_complete(int fd, uint16_t opcode, const uint8_t *ret_params, uint8_t ret_len)
{
    uint8_t pkt[264];
    pkt[0] = HCI_PACKET_TYPE_EVENT;
    pkt[1] = HCI_EVENT_COMMAND_COMPLETE;
    pkt[2] = (uint8_t)(3 + ret_len);
    pkt[3] = 0x01; /* Num_HCI_Command_Packets */
    pkt[4] = (uint8_t)(opcode & 0xFF);
    pkt[5] = (uint8_t)((opcode >> 8) & 0xFF);
    if (ret_len > 0 && ret_params != NULL) {
        memcpy(&pkt[6], ret_params, ret_len);
    }
    (void)write_all(fd, pkt, 6 + (size_t)ret_len);
}

static void send_cmd_status(int fd, uint16_t opcode, uint8_t status)
{
    uint8_t pkt[7];
    pkt[0] = HCI_PACKET_TYPE_EVENT;
    pkt[1] = HCI_EVENT_COMMAND_STATUS;
    pkt[2] = 0x04;
    pkt[3] = status;
    pkt[4] = 0x01;
    pkt[5] = (uint8_t)(opcode & 0xFF);
    pkt[6] = (uint8_t)((opcode >> 8) & 0xFF);
    (void)write_all(fd, pkt, sizeof(pkt));
}

static void handle_hci_command(int fd, uint16_t opcode, const uint8_t *params, uint8_t plen)
{
    uint8_t rsp[255];
    memset(rsp, 0, sizeof(rsp));
    rsp[0] = 0x00; /* Status: Success */

    switch (opcode) {
        case 0x0401: { /* HCI_Inquiry */
            send_cmd_status(fd, opcode, 0x00);
            uint8_t inq_done[4] = {HCI_PACKET_TYPE_EVENT, HCI_EVENT_INQUIRY_COMPLETE, 0x01, 0x00};
            (void)write_all(fd, inq_done, sizeof(inq_done));
            return;
        }
        case 0x0402: /* HCI_Inquiry_Cancel */
            send_cmd_complete(fd, opcode, rsp, 1);
            return;
        case 0x0C13: /* HCI_Write_Local_Name */
            if (plen > 0) {
                size_t copy_len = plen < sizeof(g_local_name) ? plen : sizeof(g_local_name) - 1;
                memset(g_local_name, 0, sizeof(g_local_name));
                memcpy(g_local_name, params, copy_len);
            }
            send_cmd_complete(fd, opcode, rsp, 1);
            return;
        case 0x0C14: /* HCI_Read_Local_Name */
            memcpy(&rsp[1], g_local_name, 248);
            send_cmd_complete(fd, opcode, rsp, 249);
            return;
        case 0x0C19: /* HCI_Read_Scan_Enable */
            rsp[1] = g_scan_enable;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C1A: /* HCI_Write_Scan_Enable */
            if (plen >= 1) {
                g_scan_enable = params[0];
            }
            send_cmd_complete(fd, opcode, rsp, 1);
            return;
        case 0x0C23: /* HCI_Read_Class_Of_Device */
            memcpy(&rsp[1], g_class_of_device, 3);
            send_cmd_complete(fd, opcode, rsp, 4);
            return;
        case 0x0C24: /* HCI_Write_Class_Of_Device */
            if (plen >= 3) {
                memcpy(g_class_of_device, params, 3);
            }
            send_cmd_complete(fd, opcode, rsp, 1);
            return;
        case 0x0C25: /* HCI_Read_Voice_Setting */
            rsp[1] = 0x60;
            rsp[2] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 3);
            return;
        case 0x0C38: /* HCI_Read_Number_Of_Supported_IAC */
            rsp[1] = 0x02;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C39: /* HCI_Read_Current_IAC_LAP */
            rsp[1] = 0x01;
            rsp[2] = 0x33;
            rsp[3] = 0x8B;
            rsp[4] = 0x9E;
            send_cmd_complete(fd, opcode, rsp, 5);
            return;
        case 0x0C44: /* HCI_Read_Inquiry_Mode */
            rsp[1] = 0x02;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C46: /* HCI_Read_Page_Scan_Type */
            rsp[1] = 0x01;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C51: /* HCI_Read_Extended_Inquiry_Response */
            rsp[1] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 242);
            return;
        case 0x0C55: /* HCI_Read_Simple_Pairing_Mode */
            rsp[1] = 0x01;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C58: /* HCI_Read_Inquiry_Response_Transmit_Power_Level */
            rsp[1] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x0C6C: /* HCI_Read_LE_Host_Support */
            rsp[1] = 0x01;
            rsp[2] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 3);
            return;
        case 0x1001: /* HCI_Read_Local_Version_Information */
            rsp[1] = 0x0B; /* HCI Version: Bluetooth 5.2 */
            rsp[2] = 0x01;
            rsp[3] = 0x00;
            rsp[4] = 0x0B; /* LMP Version: Bluetooth 5.2 */
            rsp[5] = 0x0F; /* Manufacturer: Broadcom / Virtual */
            rsp[6] = 0x00;
            rsp[7] = 0x01;
            rsp[8] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 9);
            return;
        case 0x1002: /* HCI_Read_Local_Supported_Commands */
            memset(&rsp[1], 0xFF, 44);
            send_cmd_complete(fd, opcode, rsp, 65);
            return;
        case 0x1003: { /* HCI_Read_Local_Supported_Features */
            const uint8_t feats[8] = {0xFF, 0xFF, 0x8F, 0xFE, 0xD8, 0x3F, 0x5B, 0x87};
            memcpy(&rsp[1], feats, 8);
            send_cmd_complete(fd, opcode, rsp, 9);
            return;
        }
        case 0x1004: { /* HCI_Read_Local_Extended_Features */
            uint8_t page = (plen >= 1) ? params[0] : 0;
            rsp[1] = page;
            rsp[2] = 0x01; /* Maximum page number */
            if (page == 0) {
                const uint8_t feats0[8] = {0xFF, 0xFF, 0x8F, 0xFE, 0xD8, 0x3F, 0x5B, 0x87};
                memcpy(&rsp[3], feats0, 8);
            } else {
                const uint8_t feats1[8] = {0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
                memcpy(&rsp[3], feats1, 8);
            }
            send_cmd_complete(fd, opcode, rsp, 11);
            return;
        }
        case 0x1005: /* HCI_Read_Buffer_Size */
            rsp[1] = 0xFD; /* ACL MTU = 1021 */
            rsp[2] = 0x03;
            rsp[3] = 0x40; /* SCO MTU = 64 */
            rsp[4] = 0x08; /* ACL Total Pkts = 8 */
            rsp[5] = 0x00;
            rsp[6] = 0x08; /* SCO Total Pkts = 8 */
            rsp[7] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 8);
            return;
        case 0x1009: /* HCI_Read_BD_ADDR */
            memcpy(&rsp[1], g_bdaddr, 6);
            send_cmd_complete(fd, opcode, rsp, 7);
            return;
        case 0x100B: /* HCI_Read_Local_Supported_Codecs */
            rsp[1] = 0x02;
            rsp[2] = 0x00;
            rsp[3] = 0x01;
            rsp[4] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 5);
            return;
        case 0x2002: /* HCI_LE_Read_Buffer_Size */
            rsp[1] = 0xFB; /* LE ACL MTU = 251 */
            rsp[2] = 0x00;
            rsp[3] = 0x08; /* LE Total Pkts = 8 */
            send_cmd_complete(fd, opcode, rsp, 4);
            return;
        case 0x2003: /* HCI_LE_Read_Local_Supported_Features */
            rsp[1] = 0xFF;
            send_cmd_complete(fd, opcode, rsp, 9);
            return;
        case 0x2007: /* HCI_LE_Read_Advertising_Physical_Channel_Tx_Power */
            rsp[1] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x200F: /* HCI_LE_Read_Filter_Accept_List_Size */
            rsp[1] = 0x10;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x201C: { /* HCI_LE_Read_Supported_States */
            const uint8_t states[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x03, 0x00, 0x00};
            memcpy(&rsp[1], states, 8);
            send_cmd_complete(fd, opcode, rsp, 9);
            return;
        }
        case 0x2023: /* HCI_LE_Read_Suggested_Default_Data_Length */
            rsp[1] = 0xFB;
            rsp[2] = 0x00;
            rsp[3] = 0x48;
            rsp[4] = 0x08;
            send_cmd_complete(fd, opcode, rsp, 5);
            return;
        case 0x202A: /* HCI_LE_Read_Resolving_List_Size */
            rsp[1] = 0x10;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        case 0x202F: { /* HCI_LE_Read_Maximum_Data_Length */
            const uint8_t max_len[8] = {0xFB, 0x00, 0x48, 0x08, 0xFB, 0x00, 0x48, 0x08};
            memcpy(&rsp[1], max_len, 8);
            send_cmd_complete(fd, opcode, rsp, 9);
            return;
        }
        case 0x2036: /* HCI_LE_Read_Maximum_Advertising_Data_Length */
            rsp[1] = 0x1F;
            rsp[2] = 0x00;
            send_cmd_complete(fd, opcode, rsp, 3);
            return;
        case 0x203B: /* HCI_LE_Read_Number_of_Supported_Advertising_Sets */
            rsp[1] = 0x04;
            send_cmd_complete(fd, opcode, rsp, 2);
            return;
        default:
            send_cmd_complete(fd, opcode, rsp, 1);
            return;
    }
}

static void *hci_controller_thread(void *arg)
{
    int fd = (int)(intptr_t)arg;
    uint8_t pkt_type = 0;
    uint8_t hdr[4];
    uint8_t payload[1024];

    while (g_running && fd >= 0) {
        ohos_fd_set rfds;
        fd_zero(&rfds);
        fd_set_bit(fd, &rfds);
        struct ohos_timeval tv = {.tv_sec = 0, .tv_usec = 200000};
        int r = select(fd + 1, &rfds, NULL, NULL, &tv);
        if (r < 0) {
            if (errno == EINTR) {
                continue;
            }
            break;
        }
        if (r == 0) {
            continue;
        }
        if (read_exact(fd, &pkt_type, 1) < 0) {
            break;
        }
        if (pkt_type == HCI_PACKET_TYPE_COMMAND) {
            if (read_exact(fd, hdr, 3) < 0) {
                break;
            }
            uint16_t opcode = (uint16_t)hdr[0] | ((uint16_t)hdr[1] << 8);
            uint8_t plen = hdr[2];
            if (plen > 0) {
                if (read_exact(fd, payload, plen) < 0) {
                    break;
                }
            }
            handle_hci_command(fd, opcode, payload, plen);
        } else if (pkt_type == HCI_PACKET_TYPE_ACL_DATA) {
            if (read_exact(fd, hdr, 4) < 0) {
                break;
            }
            uint16_t dlen = (uint16_t)hdr[2] | ((uint16_t)hdr[3] << 8);
            while (dlen > 0) {
                size_t chunk = dlen > sizeof(payload) ? sizeof(payload) : dlen;
                if (read_exact(fd, payload, chunk) < 0) {
                    return NULL;
                }
                dlen -= (uint16_t)chunk;
            }
        } else if (pkt_type == HCI_PACKET_TYPE_SCO_DATA) {
            if (read_exact(fd, hdr, 3) < 0) {
                break;
            }
            uint8_t dlen = hdr[2];
            if (dlen > 0 && read_exact(fd, payload, dlen) < 0) {
                break;
            }
        } else if (pkt_type == HCI_PACKET_TYPE_ISO_DATA) {
            if (read_exact(fd, hdr, 4) < 0) {
                break;
            }
            uint16_t dlen = ((uint16_t)hdr[2] | ((uint16_t)hdr[3] << 8)) & 0x3FFF;
            while (dlen > 0) {
                size_t chunk = dlen > sizeof(payload) ? sizeof(payload) : dlen;
                if (read_exact(fd, payload, chunk) < 0) {
                    return NULL;
                }
                dlen -= (uint16_t)chunk;
            }
        }
    }
    return NULL;
}

static void stop_controller_thread(void)
{
    g_running = 0;
    if (g_sv[1] >= 0) {
        shutdown(g_sv[1], SHUT_RDWR);
    }
    if (g_thread_started) {
        pthread_join(g_worker_thread, NULL);
        g_thread_started = 0;
    }
    if (g_sv[1] >= 0) {
        close(g_sv[1]);
        g_sv[1] = -1;
    }
    if (g_sv[0] >= 0) {
        close(g_sv[0]);
        g_sv[0] = -1;
    }
}

static int vendor_init(const BtVendorCallbacksT *callbacks, unsigned char *localBdaddr)
{
    g_callbacks = callbacks;
    if (localBdaddr != NULL) {
        int non_zero = 0;
        for (int i = 0; i < 6; i++) {
            if (localBdaddr[i] != 0) {
                non_zero = 1;
                break;
            }
        }
        if (non_zero) {
            for (int i = 0; i < 6; i++) {
                g_bdaddr[i] = localBdaddr[5 - i];
            }
        }
    }
    return 0;
}

static int vendor_op(BtOpcodeT opcode, void *param)
{
    switch (opcode) {
        case BT_OP_POWER_ON:
            return 0;
        case BT_OP_POWER_OFF:
            return 0;
        case BT_OP_HCI_CHANNEL_OPEN: {
            if (param == NULL) {
                return -1;
            }
            stop_controller_thread();
            if (socketpair(AF_UNIX, SOCK_STREAM, 0, g_sv) != 0) {
                return -1;
            }
            g_running = 1;
            if (pthread_create(&g_worker_thread, NULL, hci_controller_thread, (void *)(intptr_t)g_sv[1]) == 0) {
                g_thread_started = 1;
            }
            int *channel = (int *)param;
            channel[0] = g_sv[0];
            return 1; /* 1 H4 channel */
        }
        case BT_OP_HCI_CHANNEL_CLOSE:
            stop_controller_thread();
            return 0;
        case BT_OP_INIT:
            if (g_callbacks != NULL && g_callbacks->init_cb != NULL) {
                g_callbacks->init_cb(BTC_OP_RESULT_SUCCESS);
            }
            return 0;
        case BT_OP_GET_LPM_TIMER:
            if (param != NULL) {
                *(uint32_t *)param = 0;
            }
            return 0;
        case BT_OP_LPM_ENABLE:
        case BT_OP_LPM_DISABLE:
        case BT_OP_WAKEUP_LOCK:
        case BT_OP_WAKEUP_UNLOCK:
        case BT_OP_EVENT_CALLBACK:
        default:
            return 0;
    }
}

static void vendor_close(void)
{
    stop_controller_thread();
    g_callbacks = NULL;
}

__attribute__((visibility("default"))) const BtVendorInterfaceT BLUETOOTH_VENDOR_LIB_INTERFACE = {
    .size = sizeof(BtVendorInterfaceT),
    .init = vendor_init,
    .op = vendor_op,
    .close = vendor_close,
};
