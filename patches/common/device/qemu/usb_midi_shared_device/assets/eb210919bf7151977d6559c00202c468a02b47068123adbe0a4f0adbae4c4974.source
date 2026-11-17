/*
 * Copyright (c) 2022-2023 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "usbfn_mtp_impl.h"
#include <unistd.h>
#include <cinttypes>
#include <string>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

#include "hdf_base.h"
#include "hdf_device_desc.h"
#include "hdf_log.h"
#include "hitrace_meter.h"
#include "scope_guard.h"

#define HDF_LOG_TAG usbfn_mtp_impl
#define UDC_NAME "invalid_udc_name"
#undef  LOG_DOMAIN
#define LOG_DOMAIN 0xD002518
#define MTP_FUNCTION ("MTP_" + std::string(__func__))

/* Compatible: Microsoft MTP OS String */
static uint8_t g_mtpOsString[] = {18, /* sizeof(mtp_os_string) */
    USB_DDK_DT_STRING,
    /* Signature field: "MSFT100" (4D00530046005400310030003000) */
    'M', 0, 'S', 0, 'F', 0, 'T', 0, '1', 0, '0', 0, '0', 0,
    /* Vendor code to fetch other OS feature descriptors */
    1,
    /* padding */
    0};

/* Microsoft Extended Configuration Descriptor Header Section */
struct UsbMtpExtConfigDescHeader {
    uint32_t dwLength;
    uint16_t bcdVersion;
    uint16_t wIndex;
    uint8_t bCount;
    uint8_t reserved[7]; /* reserved */
};

/* Microsoft Extended Configuration Descriptor Function Section */
struct UsbMtpExtConfigDescFunction {
    uint8_t bFirstInterfaceNumber;
    uint8_t bInterfaceCount;
    uint8_t compatibleID[8];    /* The function’s compatible ID */
    uint8_t subCompatibleID[8]; /* The function’s subcompatible ID */
    uint8_t reserved[6];        /* reserved */
};

/* Compatible: MTP Extended Configuration Descriptor */
static struct {
    struct UsbMtpExtConfigDescHeader header;
    struct UsbMtpExtConfigDescFunction function;
} g_mtpExtConfigDesc = {
    .header = {
        .dwLength = CPU_TO_LE32(sizeof(g_mtpExtConfigDesc)),
        /* The descriptor’s version number in Binary Coded Decimal (for example, version 1.00 is 0100H) */
        .bcdVersion = CPU_TO_LE16(0x0100),
        /* set to 0x04 for extended compat ID descriptors */
        .wIndex = CPU_TO_LE16(4),
        /* Number of function sections */
        .bCount = CPU_TO_LE16(1),
        .reserved = {0},
    },
    .function = {
        .bFirstInterfaceNumber = 0,
        .bInterfaceCount = 1,
        /* Media Transfer Protocol */
        .compatibleID = {'M', 'T', 'P'},
        .subCompatibleID = {0},
        .reserved = {0},
    },
};

struct UsbMtpDeviceStatus {
    uint16_t wLength;
    uint16_t wCode;
};

namespace OHOS {
namespace HDI {
namespace Usb {
namespace Gadget {
namespace Mtp {
namespace V1_0 {
sptr<IUsbfnMtpInterface> g_instance = nullptr;
std::mutex g_instanceLock;
extern "C" void *UsbfnMtpInterfaceImplGetInstance(void)
{
    std::lock_guard<std::mutex> guard(g_instanceLock);
    if (g_instance == nullptr) {
        sptr<IUsbfnMtpInterface> tmp(new (std::nothrow) UsbfnMtpImpl);
        g_instance = tmp;
    }

    return g_instance;
}

struct UsbMtpDevice *UsbfnMtpImpl::mtpDev_ = nullptr;
struct UsbMtpPort *UsbfnMtpImpl::mtpPort_ = nullptr;
pthread_rwlock_t UsbfnMtpImpl::mtpRunrwLock_ = PTHREAD_RWLOCK_INITIALIZER;
std::mutex UsbfnMtpImpl::startMutex_;
std::mutex UsbfnMtpImpl::readMutex_;
std::mutex UsbfnMtpImpl::writeMutex_;
std::mutex UsbfnMtpImpl::eventMutex_;
std::mutex UsbfnMtpImpl::asyncMutex_;
sem_t UsbfnMtpImpl::asyncReq_ {0};

constexpr uint32_t BULK_IN_TIMEOUT_JIFFIES = 0;  /* sync timeout, set to 0 means wait forever */
constexpr uint32_t BULK_OUT_TIMEOUT_JIFFIES = 0; /* sync timeout, set to 0 means wait forever */
constexpr uint32_t INTR_IN_TIMEOUT_JIFFIES = 0;  /* sync timeout, set to 0 means wait forever */
constexpr uint64_t MTP_MAX_FILE_SIZE = 0xFFFFFFFFULL;
constexpr uint32_t WRITE_FILE_TEMP_SLICE = 16 * 100 * 1024; /* 16*100KB */
constexpr uint32_t ZERO_LENGTH_PACKET_JIFFIES = 100;  /* sync timeout, set to 0 means wait forever */
constexpr uint32_t ZERO_LENGTH_PACKET = 0;
static constexpr int32_t WAIT_UDC_MAX_LOOP = 3;
static constexpr uint32_t WAIT_UDC_TIME = 300000;
static constexpr uint32_t REQ_ACTUAL_DEFAULT_LENGTH = 0;
static constexpr uint32_t REQ_ACTUAL_MAX_LENGTH = 128;
static constexpr uint32_t REQ_ACTUAL_MININUM_LENGTH = 5;
static constexpr int32_t  HDF_ERROR_ECANCEL = -20;
static constexpr int32_t  WRITE_SPLIT_MININUM_LENGTH = 81920;
static constexpr int32_t  MTP_PROTOCOL_PACKET_SIZE = 4;
static constexpr int32_t  MTP_BUFFER_SIZE = 16384;
enum UsbMtpNeedZeroLengthPacket {
    ZLP_NO_NEED = 0, /* no need send ZLP */
    ZLP_NEED,        /* need send ZLP */
    ZLP_TRY,         /* try send ZLP */
    ZLP_DONE,        /* send ZLP done */
};

enum UsbMtpAsyncXferState {
    ASYNC_XFER_FILE_NORMAL = 0,
    ASYNC_XFER_FILE_DONE,
};

UsbfnMtpImpl::UsbfnMtpImpl() : deviceObject_(nullptr) {}

void UsbfnMtpImpl::UsbFnRequestReadComplete(uint8_t pipe, struct UsbFnRequest *req)
{
    (void)pipe;
    if (req == nullptr || req->context == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION + " " + std::to_string(req->reqId));
    FinishAsyncTrace(HITRACE_TAG_HDF, "asyncIO", req->reqId);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    struct UsbMtpPort *mtpPort = static_cast<struct UsbMtpPort *>(req->context);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr ||
        mtpPort == nullptr || mtpPort->mtpDev == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: invalid content", __func__);
        return;
    }
    UsbMtpPortReleaseRxReq(mtpPort, req);
    if (mtpPort->mtpDev->mtpState == MTP_STATE_CANCELED) {
        CopyReqToStandbyReqPool(req, mtpPort->standbyReq);
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGD("%{public}s, mtpState: %{public}d.", __func__, mtpPort->mtpDev->mtpState);
        return;
    }
    if (!mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: dev is release", __func__);
        return;
    }
    int32_t ret = UsbMtpPortRxPush(mtpPort, req);
    if (ret != HDF_SUCCESS) {
        HDF_LOGW("%{public}s: rx push failed: %{public}d, state=%{public}d", __func__, ret, mtpPort->mtpDev->mtpState);
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
}

static void RemoveReqFromList(struct UsbFnRequest *req)
{
    if (req->list.prev != NULL && req->list.next != NULL) {
        DListRemove(&req->list);
    } else {
        HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
    }
}

void UsbfnMtpImpl::UsbMtpPortReleaseRxReq(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    std::lock_guard<std::mutex> guard(asyncMutex_);

    if (mtpPort->suspended) {
        return;
    }
    if (req->list.prev != NULL && req->list.next != NULL) {
        DListRemove(&req->list);
    } else {
        HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
    }
    DListInsertTail(&req->list, &mtpPort->readPool);
    mtpPort->readStarted--;
}

void UsbfnMtpImpl::UsbMtpPortReleaseTxReq(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    std::lock_guard<std::mutex> guard(asyncMutex_);

    if (mtpPort->suspended) {
        return;
    }
    if (req->list.prev != NULL && req->list.next != NULL) {
        DListRemove(&req->list);
    } else {
        HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
    }
    DListInsertTail(&req->list, &mtpPort->writePool);
    mtpPort->writeStarted--;
}

void UsbfnMtpImpl::UsbFnRequestWriteComplete(uint8_t pipe, struct UsbFnRequest *req)
{
    (void)pipe;
    if (req == nullptr || req->context == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION + " " + std::to_string(req->reqId));
    FinishAsyncTrace(HITRACE_TAG_HDF, "asyncIO", req->reqId);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    struct UsbMtpPort *mtpPort = static_cast<struct UsbMtpPort *>(req->context);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr ||
        mtpPort == nullptr || mtpPort->mtpDev == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: invalid content", __func__);
        return;
    }
    UsbMtpPortReleaseTxReq(mtpPort, req);
    if (mtpPort->mtpDev->mtpState == MTP_STATE_CANCELED || !mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGD("%{public}s, mtpState: %{public}d.", __func__, mtpPort->mtpDev->mtpState);
        return;
    }
    int32_t ret = UsbMtpPortTxReqCheck(mtpPort, req);
    if (ret != HDF_SUCCESS) {
        HDF_LOGW("%{public}s: tx check failed(%{%{public}d/%{public}d}): %{public}d, state=%{public}hhu", __func__,
            mtpPort->readStarted, mtpPort->readAllocated, ret, mtpPort->mtpDev->mtpState);
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
}

void UsbfnMtpImpl::UsbFnRequestNotifyComplete(uint8_t pipe, struct UsbFnRequest *req)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    (void)pipe;
    if (req == nullptr || req->context == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
}

void UsbfnMtpImpl::UsbFnRequestCtrlComplete(uint8_t pipe, struct UsbFnRequest *req)
{
    (void)pipe;
    if (req == nullptr || req->context == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION + " " + std::to_string(req->reqId));
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    struct CtrlInfo *ctrlInfo = static_cast<struct CtrlInfo *>(req->context);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr ||
        ctrlInfo == nullptr || ctrlInfo->mtpDev == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: invalid content", __func__);
        return;
    }
    struct UsbMtpDevice *mtpDev = ctrlInfo->mtpDev;
    switch (req->status) {
        case USB_REQUEST_COMPLETED:
            break;
        case USB_REQUEST_NO_DEVICE:
            HDF_LOGW("%{public}s: usb mtpDev device was disconnected", __func__);
            mtpDev->mtpState = MTP_STATE_OFFLINE;
            break;
        default:
            HDF_LOGW("%{public}s: unexpected status %{public}d", __func__, req->status);
            break;
    }
    DListInsertTail(&req->list, &mtpDev->ctrlPool);
    pthread_rwlock_unlock(&mtpRunrwLock_);
}

int32_t UsbfnMtpImpl::UsbMtpPortTxReqCheck(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    switch (req->status) {
        case USB_REQUEST_COMPLETED:
            mtpDev->asyncSendFileActual += static_cast<uint64_t>(req->actual);
            if (mtpDev->asyncSendFileActual == mtpDev->xferFileLength &&
                ((req->actual == 0 && mtpDev->needZLP == ZLP_TRY) || mtpDev->needZLP == ZLP_NO_NEED)) {
                HDF_LOGD("%{public}s: async tx done: req(%{public}d/%{public}d)%{public}u/%{public}u, send "
                    "%{public}" PRIu64 "/%{public}" PRIu64 "/%{public}" PRIu64 ", ZLP=%{public}hhu", __func__,
                    mtpPort->writeStarted, mtpPort->writeAllocated, req->actual, req->length,
                    mtpDev->asyncSendFileExpect, mtpDev->asyncSendFileActual, mtpDev->xferFileLength, mtpDev->needZLP);
                sem_post(&asyncReq_);
                return HDF_SUCCESS;
            }
            return UsbMtpPortStartTxAsync(mtpPort, true);
        case USB_REQUEST_NO_DEVICE:
            HDF_LOGW("%{public}s: tx req return disconnected", __func__);
            mtpPort->mtpDev->mtpState = MTP_STATE_OFFLINE;
            sem_post(&asyncReq_);
            return HDF_DEV_ERR_NO_DEVICE;
        default:
            HDF_LOGW("%{public}s: unexpected status %{public}d", __func__, req->status);
            sem_post(&asyncReq_);
            return HDF_ERR_IO;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortProcessLastTxPacket(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    int32_t ret = HDF_SUCCESS;
    if (mtpPort->mtpDev->needZLP == ZLP_NEED) {
        mtpPort->mtpDev->needZLP = ZLP_TRY;
        req->length = 0;
        HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestAsync " + std::to_string(req->reqId));
        StartAsyncTrace(HITRACE_TAG_HDF, "asyncIO", req->reqId);
        ret = UsbFnSubmitRequestAsync(req);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: submit bulk-in zlp req error: %{public}d", __func__, ret);
            sem_post(&asyncReq_);
        }
        mtpPort->writeStarted++;
    }
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortSubmitAsyncTxReq(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    ssize_t readRet = read(mtpPort->mtpDev->xferFd, req->buf, static_cast<size_t>(req->length));
    if (readRet != static_cast<ssize_t>(req->length)) {
        HDF_LOGE("%{public}s: read failed: %{public}zd < %{public}u", __func__, readRet, req->length);
        return HDF_FAILURE;
    }
    if (req->list.prev != NULL && req->list.next != NULL) {
        DListRemove(&req->list);
    } else {
        HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
    }
    DListInsertTail(&req->list, &mtpPort->writeQueue);
    HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestAsync " + std::to_string(req->reqId));
    StartAsyncTrace(HITRACE_TAG_HDF, "asyncIO", req->reqId);
    int32_t ret = UsbFnSubmitRequestAsync(req);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: submit bulk-in req error: %{public}d", __func__, ret);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        DListInsertTail(&req->list, &mtpPort->writePool);
        return ret;
    }
    mtpPort->writeStarted++;
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortStartTxAsync(struct UsbMtpPort *mtpPort, bool callByComplete)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    if (mtpPort == nullptr || mtpPort->mtpDev == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    std::lock_guard<std::mutex> guard(asyncMutex_);

    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    struct DListHead *pool = &mtpPort->writePool;
    uint64_t reqMax = static_cast<uint64_t>(MTP_BUFFER_SIZE);
    while (!DListIsEmpty(pool)) {
        if (mtpDev->needZLP == ZLP_NO_NEED) {
            if (mtpDev->asyncSendFileExpect >= mtpDev->xferFileLength) {
                return HDF_SUCCESS;
            }
        } else {
            if (mtpDev->needZLP == ZLP_TRY) {
                return HDF_SUCCESS;
            }
        }
        struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
        if (mtpDev->asyncSendFileExpect + reqMax < mtpDev->xferFileLength) {
            req->length = static_cast<uint32_t>(MTP_BUFFER_SIZE);
        } else {
            req->length = static_cast<uint32_t>(mtpDev->xferFileLength - mtpDev->asyncSendFileExpect);
        }
        if (mtpDev->xferFileLength == mtpDev->asyncSendFileExpect) {
            return UsbMtpPortProcessLastTxPacket(mtpPort, req);
        }
        int32_t ret = UsbMtpPortSubmitAsyncTxReq(mtpPort, req);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: submit bulk-in req error: %{public}d", __func__, ret);
            sem_post(&asyncReq_);
            return ret;
        }
        mtpDev->asyncSendFileExpect += static_cast<uint64_t>(req->length);
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceAllocCtrlRequests(int32_t num)
{
    struct DListHead *head = &mtpDev_->ctrlPool;
    DListHeadInit(head);
    mtpDev_->ctrlReqNum = 0;
    for (int32_t i = 0; i < num; ++i) {
        struct CtrlInfo *ctrlInfo = static_cast<struct CtrlInfo *>(OsalMemCalloc(sizeof(struct CtrlInfo)));
        if (ctrlInfo == nullptr) {
            HDF_LOGE("%{public}s: Allocate ctrlInfo failed", __func__);
            return DListIsEmpty(head) ? HDF_FAILURE : HDF_SUCCESS;
        }
        ctrlInfo->mtpDev = mtpDev_;
        struct UsbFnRequest *req = UsbFnAllocCtrlRequest(mtpDev_->ctrlIface.handle, MTP_CONTROL_XFER_BYTECOUNT);
        if (req == nullptr) {
            HDF_LOGE("%{public}s: Allocate ctrl req failed", __func__);
            (void)OsalMemFree(ctrlInfo);
            return DListIsEmpty(head) ? HDF_FAILURE : HDF_SUCCESS;
        }
        req->complete = UsbFnRequestCtrlComplete;
        req->context = ctrlInfo;
        req->reqId = i;
        DListInsertTail(&req->list, head);
        mtpDev_->ctrlReqNum++;
    }
    return HDF_SUCCESS;
}

void UsbfnMtpImpl::UsbMtpDeviceFreeCtrlRequests()
{
    struct DListHead *head = &mtpDev_->ctrlPool;
    while (!DListIsEmpty(head)) {
        struct UsbFnRequest *req = DLIST_FIRST_ENTRY(head, struct UsbFnRequest, list);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        (void)OsalMemFree(req->context);
        (void)UsbFnFreeRequest(req);
        mtpDev_->ctrlReqNum--;
    }
}

void UsbfnMtpImpl::UsbMtpPortFreeRequests(struct DListHead *head, int32_t &allocated)
{
    while (!DListIsEmpty(head)) {
        struct UsbFnRequest *req = DLIST_FIRST_ENTRY(head, struct UsbFnRequest, list);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        (void)UsbFnFreeRequest(req);
        allocated--;
    }
}

int32_t UsbfnMtpImpl::UsbMtpPortAllocReadWriteRequests(int32_t readSize, int32_t writeSize)
{
    struct UsbFnRequest *req = nullptr;
    int32_t i = 0;
    for (i = 0; i < readSize; ++i) {
        req = UsbFnAllocRequest(mtpDev_->dataIface.handle, mtpDev_->dataOutPipe.id, MTP_BUFFER_SIZE);
        if (req == nullptr) {
            if (DListIsEmpty(&mtpPort_->readPool)) {
                HDF_LOGE("%{public}s: alloc read req failed", __func__);
                return HDF_ERR_MALLOC_FAIL;
            }
            break;
        }
        req->complete = UsbFnRequestReadComplete;
        req->context = mtpPort_;
        req->reqId = i;
        DListInsertTail(&req->list, &mtpPort_->readPool);
        mtpPort_->readAllocated++;
    }
    mtpPort_->standbyReq = UsbFnAllocRequest(mtpDev_->dataIface.handle,
        mtpDev_->dataOutPipe.id, MTP_BUFFER_SIZE);
    if (mtpPort_->standbyReq == nullptr) {
        HDF_LOGE("%{public}s: alloc standbyReq failed", __func__);
        return HDF_ERR_MALLOC_FAIL;
    }
    mtpPort_->standbyReq->actual = REQ_ACTUAL_DEFAULT_LENGTH;
    for (i = 0; i < writeSize; ++i) {
        req = UsbFnAllocRequest(mtpDev_->dataIface.handle, mtpDev_->dataInPipe.id, MTP_BUFFER_SIZE);
        if (req == nullptr) {
            HDF_LOGE("%{public}s: alloc write req failed", __func__);
            return HDF_ERR_MALLOC_FAIL;
        }
        req->complete = UsbFnRequestWriteComplete;
        req->context = mtpPort_;
        req->reqId = i + readSize;
        DListInsertTail(&req->list, &mtpPort_->writePool);
        mtpPort_->writeAllocated++;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortInitIo()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    int32_t ret = HDF_SUCCESS;
    if (mtpPort_->readAllocated == 0 || mtpPort_->writeAllocated == 0) {
        HDF_LOGI("%{public}s: rx_req=%{public}d tx_req=%{public}d, alloc req", __func__, mtpPort_->readAllocated,
            mtpPort_->writeAllocated);
        ret = UsbMtpPortAllocReadWriteRequests(READ_QUEUE_SIZE, WRITE_QUEUE_SIZE);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: allocate requests for read/write failed: %{public}d", __func__, ret);
            UsbMtpPortFreeRequests(&mtpPort_->readPool, mtpPort_->readAllocated);
            if (mtpPort_->standbyReq) {
                (void)UsbFnFreeRequest(mtpPort_->standbyReq);
                mtpPort_->standbyReq = NULL;
            }
            UsbMtpPortFreeRequests(&mtpPort_->writePool, mtpPort_->writeAllocated);
            return HDF_ERR_MALLOC_FAIL;
        }
    }
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortCancelAndFreeReq(
    struct DListHead *queueHead, struct DListHead *poolHead, int32_t &allocated, bool freeReq)
{
    while (!DListIsEmpty(queueHead)) {
        struct UsbFnRequest *req = DLIST_FIRST_ENTRY(queueHead, struct UsbFnRequest, list);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        DListInsertTail(&req->list, poolHead);
    }
    while (!DListIsEmpty(poolHead)) {
        struct UsbFnRequest *req = DLIST_FIRST_ENTRY(poolHead, struct UsbFnRequest, list);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        (void)UsbFnCancelRequest(req);
        if (freeReq) {
            (void)UsbFnFreeRequest(req);
        }
        allocated--;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortCancelPlusFreeIo(struct UsbMtpPort *mtpPort, bool freeReq)
{
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: mtpPort is null", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    HDF_LOGI("%{public}s: cancel and free read req: %{public}d/%{public}d", __func__, mtpPort->readStarted,
        mtpPort->readAllocated);
    (void)UsbMtpPortCancelAndFreeReq(&mtpPort->readQueue, &mtpPort->readPool, mtpPort->readAllocated, freeReq);
    HDF_LOGI("%{public}s: cancel and free write req: %{public}d/%{public}d", __func__, mtpPort->writeStarted,
        mtpPort->writeAllocated);
    (void)UsbMtpPortCancelAndFreeReq(&mtpPort->writeQueue, &mtpPort->writePool, mtpPort->writeAllocated, freeReq);

    if (mtpPort && mtpPort->standbyReq) {
        (void)UsbFnCancelRequest(mtpPort->standbyReq);
        (void)UsbFnFreeRequest(mtpPort->standbyReq);
        mtpPort->standbyReq = NULL;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortCancelRequest(struct UsbMtpPort *mtpPort)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    DListHead *queueHead = &(mtpPort->readQueue);
    if (!DListIsEmpty(queueHead)) {
        HDF_LOGD("%{public}s: readQueue is not empty", __func__);
        struct UsbFnRequest *queueReq = nullptr;
        struct UsbFnRequest *queueReqTmp = nullptr;
        DLIST_FOR_EACH_ENTRY_SAFE(queueReq, queueReqTmp, queueHead, struct UsbFnRequest, list) {
            (void)UsbFnCancelRequest(queueReq);
            HDF_LOGD("%{public}s:cancel read", __func__);
        }
    }
    DListHead *writeQueue = &(mtpPort->writeQueue);
    if (!DListIsEmpty(writeQueue)) {
        HDF_LOGD("%{public}s: writeQueue is not empty", __func__);
        struct UsbFnRequest *queueReq = nullptr;
        struct UsbFnRequest *queueReqTmp = nullptr;
        DLIST_FOR_EACH_ENTRY_SAFE(queueReq, queueReqTmp, writeQueue, struct UsbFnRequest, list) {
            (void)UsbFnCancelRequest(queueReq);
            HDF_LOGD("%{public}s:cancel write", __func__);
        }
    }

    if (mtpPort->mtpDev != NULL && mtpPort->mtpDev->notifyReq != NULL) {
        struct UsbFnRequest *notifyReq = mtpPort->mtpDev->notifyReq;
        (void)UsbFnCancelRequest(notifyReq);
        HDF_LOGD("%{public}s:cancel notifyReq", __func__);
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortReleaseIo()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    return UsbMtpPortCancelPlusFreeIo(mtpPort_, true);
}

struct UsbFnRequest *UsbfnMtpImpl::UsbMtpDeviceGetCtrlReq(struct UsbMtpDevice *mtpDev)
{
    struct DListHead *pool = &mtpDev->ctrlPool;
    if (DListIsEmpty(pool)) {
        return nullptr;
    }
    struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
    if (req->list.prev != NULL && req->list.next != NULL) {
        DListRemove(&req->list);
    } else {
        HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
    }
    return req;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceStandardRequest(
    struct UsbMtpDevice *mtpDev, struct UsbFnCtrlRequest *setup, struct UsbFnRequest *req)
{
    uint16_t wValue = LE16_TO_CPU(setup->value);
    int32_t responseBytes = 0;
    uint8_t mtpOsStringReqType = (USB_DDK_DIR_IN | USB_DDK_TYPE_STANDARD | USB_DDK_RECIP_DEVICE);
    /* wValue specified descriptor type(high 8 bit) and index(low 8 bit) when request is GET_DESCRIPTOR */
    uint16_t mtpOsStringWValue = (USB_DDK_DT_STRING << 8 | USB_MTP_OS_STRING_ID);
    if (setup->request == USB_DDK_REQ_GET_DESCRIPTOR && setup->reqType == mtpOsStringReqType &&
        wValue == mtpOsStringWValue) {
        /* Handle MTP OS string */
        HDF_LOGI("%{public}s: Standard Request-Get Descriptor(String)", __func__);
        responseBytes = (wValue < sizeof(g_mtpOsString)) ? wValue : sizeof(g_mtpOsString);
        if (memcpy_s(req->buf, responseBytes, g_mtpOsString, responseBytes) != EOK) {
            HDF_LOGE("%{public}s: memcpy_s failed: Get Descriptor", __func__);
            return HDF_FAILURE;
        }
    } else {
        HDF_LOGW("%{public}s: Standard Request-unknown: %{public}d", __func__, setup->request);
    }
    return responseBytes;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceClassRequest(
    struct UsbMtpDevice *mtpDev, struct UsbFnCtrlRequest *setup, struct UsbFnRequest *req)
{
    int32_t responseBytes = 0;
    if (setup->request == USB_MTP_REQ_CANCEL && setup->index == 0 && setup->value == 0) {
        HDF_LOGI("%{public}s: Class Request-MTP_REQ_CANCEL", __func__);
        if (mtpDev->mtpState == MTP_STATE_BUSY) {
            mtpDev->mtpState = MTP_STATE_CANCELED;
            DListHead *queueHead = &(mtpDev->mtpPort->readQueue);
            if (!DListIsEmpty(queueHead)) {
                HDF_LOGD("%{public}s: readQueue is not empty", __func__);
                struct UsbFnRequest *queueReq = nullptr;
                struct UsbFnRequest *queueReqTmp = nullptr;
                DLIST_FOR_EACH_ENTRY_SAFE(queueReq, queueReqTmp, queueHead, struct UsbFnRequest, list) {
                    (void)UsbFnCancelRequest(queueReq);
                    HDF_LOGD("%{public}s:cancel read", __func__);
                }
            }
            DListHead *writeQueue = &(mtpDev->mtpPort->writeQueue);
            if (!DListIsEmpty(writeQueue)) {
                HDF_LOGD("%{public}s: writeQueue is not empty", __func__);
                struct UsbFnRequest *queueReq = nullptr;
                struct UsbFnRequest *queueReqTmp = nullptr;
                DLIST_FOR_EACH_ENTRY_SAFE(queueReq, queueReqTmp, writeQueue, struct UsbFnRequest, list) {
                    (void)UsbFnCancelRequest(queueReq);
                    HDF_LOGD("%{public}s:cancel write", __func__);
                }
            }
            HDF_LOGD("%{public}s:async post, readStart:%{public}d", __func__, mtpDev->mtpPort->readStarted);
            sem_post(&asyncReq_);
        }
    } else if (setup->request == USB_MTP_REQ_GET_DEVICE_STATUS && setup->index == 0 && setup->value == 0) {
        HDF_LOGI("%{public}s: Class Request-MTP_REQ_GET_DEVICE_STATUS", __func__);
        struct UsbMtpDeviceStatus mtpStatus;
        mtpStatus.wLength = CPU_TO_LE16(sizeof(mtpStatus));
        if (mtpDev->mtpState == MTP_STATE_CANCELED) {
            mtpStatus.wCode = CPU_TO_LE16(MTP_RESPONSE_DEVICE_BUSY);
        } else {
            mtpStatus.wCode = CPU_TO_LE16(MTP_RESPONSE_OK);
        }
        responseBytes = static_cast<int32_t>(sizeof(mtpStatus));
        if (memcpy_s(req->buf, responseBytes, &mtpStatus, responseBytes) != EOK) {
            HDF_LOGE("%{public}s: memcpy_s failed: MTP_REQ_GET_DEVICE_STATUS", __func__);
            return HDF_FAILURE;
        }
    } else {
        HDF_LOGW("%{public}s: Class Request-UNKNOWN: %{public}d", __func__, setup->request);
    }
    return responseBytes;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceVendorRequest(
    struct UsbMtpDevice *mtpDev, struct UsbFnCtrlRequest *setup, struct UsbFnRequest *req)
{
    uint16_t wIndex = LE16_TO_CPU(setup->index);
    uint16_t wLength = LE16_TO_CPU(setup->length);
    int32_t responseBytes = 0;
    if (setup->request == USB_MTP_BMS_VENDORCODE && (setup->reqType & USB_DDK_DIR_IN) &&
        (wIndex == USB_MTP_EXTENDED_COMPAT_ID || wIndex == USB_MTP_EXTENDED_PROPERTIES)) {
        /* Handle MTP OS descriptor */
        HDF_LOGI("%{public}s: Vendor Request-Get Descriptor(MTP OS)", __func__);
        responseBytes = (wLength < sizeof(g_mtpExtConfigDesc)) ? wLength : sizeof(g_mtpExtConfigDesc);
        if (memcpy_s(req->buf, responseBytes, &g_mtpExtConfigDesc, responseBytes) != EOK) {
            HDF_LOGE("%{public}s: memcpy_s failed: Get Descriptor(MTP OS)", __func__);
            return HDF_FAILURE;
        }
    } else {
        HDF_LOGW("%{public}s: Vendor Request-UNKNOWN: %{public}d", __func__, setup->request);
    }
    return responseBytes;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceSetup(struct UsbMtpDevice *mtpDev, struct UsbFnCtrlRequest *setup)
{
    if (mtpDev == nullptr || mtpDev->mtpPort == nullptr || setup == nullptr) {
        return HDF_ERR_INVALID_PARAM;
    }
    HDF_LOGD(
        "%{public}s: Setup: reqType=0x%{public}X, req=0x%{public}X, idx=%{public}d, val=%{public}d, len=%{public}d",
        __func__, setup->reqType, setup->request, LE16_TO_CPU(setup->index), LE16_TO_CPU(setup->value),
        LE16_TO_CPU(setup->length));

    struct UsbFnRequest *req = UsbMtpDeviceGetCtrlReq(mtpDev);
    if (req == nullptr) {
        HDF_LOGE("%{public}s: control req pool is empty", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    int32_t responseBytes = 0;
    switch (setup->reqType & USB_DDK_TYPE_MASK) {
        case USB_DDK_TYPE_STANDARD:
            responseBytes = UsbMtpDeviceStandardRequest(mtpDev, setup, req);
            break;
        case USB_DDK_TYPE_CLASS:
            responseBytes = UsbMtpDeviceClassRequest(mtpDev, setup, req);
            break;
        case USB_DDK_TYPE_VENDOR:
            responseBytes = UsbMtpDeviceVendorRequest(mtpDev, setup, req);
            break;
        default:
            HDF_LOGW("%{public}s: Reserved Request: %{public}d", __func__, (setup->reqType & USB_DDK_TYPE_MASK));
            break;
    }

    struct CtrlInfo *ctrlInfo = static_cast<struct CtrlInfo *>(req->context);
    ctrlInfo->request = setup->request;
    ctrlInfo->mtpDev = mtpDev;
    if (responseBytes >= 0) {
        req->length = static_cast<uint32_t>(responseBytes);
        HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestAsync " + std::to_string(req->reqId));
        int32_t ret = UsbFnSubmitRequestAsync(req);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: mtpDev send setup response error", __func__);
            return ret;
        }
    }
    return HDF_SUCCESS;
}

void UsbfnMtpImpl::UsbMtpDeviceSuspend(struct UsbMtpDevice *mtpDev)
{
    struct UsbMtpPort *mtpPort = mtpDev->mtpPort;
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
    std::lock_guard<std::mutex> guard(asyncMutex_);
    mtpPort->suspended = true;
    (void)UsbMtpPortCancelRequest(mtpPort);
}

void UsbfnMtpImpl::UsbMtpDeviceResume(struct UsbMtpDevice *mtpDev)
{
    struct UsbMtpPort *mtpPort = mtpDev->mtpPort;
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return;
    }
    mtpPort->suspended = false;
    if (!mtpPort->startDelayed) {
        return;
    }
    mtpPort->startDelayed = false;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceEnable(struct UsbMtpDevice *mtpDev)
{
    if (mtpDev == nullptr || !mtpDev->initFlag) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    struct UsbMtpPort *mtpPort = mtpDev->mtpPort;
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    /* the mtpDev is enabled, ready for transfer */
    mtpDev->mtpState = MTP_STATE_READY;
    mtpPort->startDelayed = true;
    mtpPort->suspended = false;
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceDisable(struct UsbMtpDevice *mtpDev)
{
    if (mtpDev == nullptr || !mtpDev->initFlag) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    struct UsbMtpPort *mtpPort = mtpDev->mtpPort;
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    /* Disable event: The USB Device Controller has been disabled due to some problem */
    mtpPort->startDelayed = false;
    mtpDev->mtpState = MTP_STATE_OFFLINE;
    return HDF_SUCCESS;
}

void UsbfnMtpImpl::UsbMtpDeviceEp0EventDispatch(struct UsbFnEvent *event)
{
    if (event == nullptr || event->context == nullptr) {
        HDF_LOGE("%{public}s: invalid param event", __func__);
        return;
    }

    struct UsbMtpDevice *mtpDev = static_cast<struct UsbMtpDevice *>(event->context);
    HDF_LOGI("%{public}s EP0 event: [%{public}d], state=%{public}hhu", __func__, event->type, mtpDev->mtpState);
    switch (event->type) {
        case USBFN_STATE_BIND:
            HDF_LOGI("%{public}s: EP0 [bind] ignore", __func__);
            break;
        case USBFN_STATE_UNBIND:
            HDF_LOGI("%{public}s: EP0 [unbind] ignore", __func__);
            break;
        case USBFN_STATE_ENABLE:
            HDF_LOGI("%{public}s: EP0 [enable]", __func__);
            (void)UsbMtpDeviceEnable(mtpDev);
            break;
        case USBFN_STATE_DISABLE:
            HDF_LOGI("%{public}s: EP0 [disable]", __func__);
            (void)UsbMtpDeviceDisable(mtpDev);
            break;
        case USBFN_STATE_SETUP:
            HDF_LOGI("%{public}s: EP0 [setup]", __func__);
            if (event->setup != nullptr) {
                (void)UsbMtpDeviceSetup(mtpDev, event->setup);
            }
            break;
        case USBFN_STATE_SUSPEND:
            HDF_LOGI("%{public}s: EP0 [suspend]", __func__);
            UsbMtpDeviceSuspend(mtpDev);
            break;
        case USBFN_STATE_RESUME:
            HDF_LOGI("%{public}s: EP0 [resume]", __func__);
            UsbMtpDeviceResume(mtpDev);
            break;
        default:
            HDF_LOGI("%{public}s: EP0 ignore or unknown: %{public}d", __func__, event->type);
            break;
    }
}

void UsbfnMtpImpl::CopyReqToStandbyReqPool(const struct UsbFnRequest *req, struct UsbFnRequest *standbyReq)
{
    if (req->actual < REQ_ACTUAL_MININUM_LENGTH || req->actual > REQ_ACTUAL_MAX_LENGTH) {
        HDF_LOGE("%{public}s: actual: %{public}d", __func__, req->actual);
        return;
    }

    standbyReq->actual = req->actual;
    standbyReq->type = req->type;
    if (memcpy_s(standbyReq->buf, req->actual, req->buf, req->actual) != EOK) {
        HDF_LOGE("%{public}s: memcpy_s failed", __func__);
        return;
    }
}

int32_t UsbfnMtpImpl::UsbMtpDeviceParseEachPipe(struct UsbMtpInterface &iface)
{
    struct UsbFnInterface *fnIface = iface.fn;
    if (fnIface == nullptr || fnIface->info.numPipes == 0) {
        HDF_LOGE("%{public}s: ifce is invalid", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    HDF_LOGI("%{public}s: interface: idx=%{public}hhu numPipes=%{public}hhu ifClass=%{public}hhu subclass=%{public}hhu "
        "protocol=%{public}hhu cfgIndex=%{public}hhu", __func__, fnIface->info.index, fnIface->info.numPipes,
        fnIface->info.interfaceClass, fnIface->info.subclass, fnIface->info.protocol, fnIface->info.configIndex);
    uint32_t repetIdx = 0;
    for (int32_t i = 0; i < fnIface->info.numPipes; ++i) {
        struct UsbFnPipeInfo pipeInfo;
        (void)memset_s(&pipeInfo, sizeof(pipeInfo), 0, sizeof(pipeInfo));
        int32_t ret = UsbFnGetInterfacePipeInfo(fnIface, static_cast<uint8_t>(i), &pipeInfo);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: get pipe info error", __func__);
            if (repetIdx < WAIT_UDC_MAX_LOOP) {
                usleep(WAIT_UDC_TIME);
                i--;
            }
            repetIdx++;
            continue;
        }
        HDF_LOGI("%{public}s: pipe: id=%{public}d type=%{public}d dir=%{public}d max=%{public}d interval=%{public}d",
            __func__, pipeInfo.id, pipeInfo.type, pipeInfo.dir, pipeInfo.maxPacketSize, pipeInfo.interval);
        switch (pipeInfo.type) {
            case USB_PIPE_TYPE_INTERRUPT:
                mtpDev_->notifyPipe.id = pipeInfo.id;
                mtpDev_->notifyPipe.maxPacketSize = pipeInfo.maxPacketSize;
                mtpDev_->ctrlIface = iface; /* MTP device only have one interface, record here */
                mtpDev_->intrIface = iface;
                break;
            case USB_PIPE_TYPE_BULK:
                if (pipeInfo.dir == USB_PIPE_DIRECTION_IN) {
                    mtpDev_->dataInPipe.id = pipeInfo.id;
                    mtpDev_->dataInPipe.maxPacketSize = pipeInfo.maxPacketSize;
                    mtpDev_->dataIface = iface;
                } else {
                    mtpDev_->dataOutPipe.id = pipeInfo.id;
                    mtpDev_->dataOutPipe.maxPacketSize = pipeInfo.maxPacketSize;
                }
                break;
            default:
                HDF_LOGE("%{public}s: pipe type %{public}d don't support", __func__, pipeInfo.type);
                break;
        }
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceParseMtpIface(struct UsbFnInterface *fnIface)
{
    UsbFnInterfaceHandle handle = UsbFnOpenInterface(fnIface);
    if (handle == nullptr) {
        HDF_LOGE("%{public}s: open interface failed", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    struct UsbMtpInterface iface;
    iface.fn = fnIface;
    iface.handle = handle;
    int32_t ret = UsbMtpDeviceParseEachPipe(iface);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: parse each pipe failed", __func__);
    }
    return ret;
}

bool UsbfnMtpImpl::UsbFnInterfaceIsUsbMtpPtpDevice(struct UsbFnInterface *iface)
{
    HDF_LOGI("%{public}s: iIf=%{public}d ifClass=%{public}d, subclass=%{public}d, protocol=%{public}d", __func__,
        iface->info.configIndex, iface->info.interfaceClass, iface->info.subclass, iface->info.protocol);
    if (iface->info.interfaceClass == USB_MTP_DEVICE_CLASS && iface->info.subclass == USB_MTP_DEVICE_SUBCLASS &&
        iface->info.protocol == USB_MTP_DEVICE_PROTOCOL) {
        HDF_LOGI("%{public}s: this is mtp device", __func__);
        return true;
    }
    if (iface->info.interfaceClass == USB_PTP_DEVICE_CLASS && iface->info.subclass == USB_PTP_DEVICE_SUBCLASS &&
        iface->info.protocol == USB_PTP_DEVICE_PROTOCOL) {
        HDF_LOGI("%{public}s: this is ptp device", __func__);
        return true;
    }
    return false;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceParseEachIface(struct UsbFnDevice *fnDev)
{
    for (int32_t i = 0; i < fnDev->numInterfaces; ++i) {
        struct UsbFnInterface *fnIface = const_cast<struct UsbFnInterface *>(UsbFnGetInterface(fnDev, i));
        if (fnIface == nullptr) {
            HDF_LOGE("%{public}s: get interface failed: %{public}d/%{public}d", __func__, i, fnDev->numInterfaces);
            return HDF_ERR_INVALID_PARAM;
        }
        if (UsbFnInterfaceIsUsbMtpPtpDevice(fnIface)) {
            /* MTP/PTP device only have one interface, only parse once */
            HDF_LOGI("%{public}s: found mtp/ptp interface: %{public}d/%{public}d", __func__, i, fnDev->numInterfaces);
            (void)UsbMtpDeviceParseMtpIface(fnIface);
            return HDF_SUCCESS;
        }
    }
    return HDF_FAILURE;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceCreateFuncDevice()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    struct DeviceResourceIface *iface = DeviceResourceGetIfaceInstance(HDF_CONFIG_SOURCE);
    if (iface == NULL) {
        HDF_LOGE("%{public}s: DeviceResourceGetIfaceInstance failed", __func__);
        return HDF_FAILURE;
    }
    const char *udcName = nullptr;
    if (deviceObject_ != nullptr) {
        if (iface->GetString(deviceObject_->property, "udc_name", &udcName, UDC_NAME) != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: read udc_name failed, use default: %{public}s", __func__, UDC_NAME);
            return HDF_ERR_INVALID_PARAM;
        }
    }
    struct UsbFnDevice *fnDev = nullptr;
    if (udcName != nullptr) {
        fnDev = const_cast<struct UsbFnDevice *>(UsbFnGetDevice(udcName));
    } else {
        HDF_LOGW("%{public}s: udcName invalid, use default", __func__);
        fnDev = const_cast<struct UsbFnDevice *>(UsbFnGetDevice(UDC_NAME));
    }
    if (fnDev == NULL) {
        HDF_LOGE("%{public}s: create usb function device failed", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    HDF_LOGI("%{public}s: getDevice interface count=%{public}d", __func__, fnDev->numInterfaces);
    int32_t ret = UsbMtpDeviceParseEachIface(fnDev);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: get pipes failed", __func__);
        return ret;
    }
    mtpDev_->fnDev = fnDev;
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceReleaseFuncDevice()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    if (mtpDev_->fnDev == nullptr) {
        HDF_LOGE("%{public}s: fnDev is null", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    (void)UsbMtpDeviceFreeCtrlRequests();
    (void)UsbMtpDeviceFreeNotifyRequest();
    int32_t finalRet = HDF_SUCCESS;
    /* mtp/ptp have one interface include bulk/intr, ctrl is default, release once */
    int32_t ret = UsbFnCloseInterface(mtpDev_->ctrlIface.handle);
    if (ret != HDF_SUCCESS) {
        finalRet = ret;
        HDF_LOGW("%{public}s: close usb ctrl/bulk/intr interface failed", __func__);
    }
    ret = UsbFnStopRecvInterfaceEvent(mtpDev_->ctrlIface.fn);
    if (ret != HDF_SUCCESS) {
        finalRet = ret;
        HDF_LOGW("%{public}s: stop usb ep0 event handle failed", __func__);
    }
    return finalRet;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceAlloc()
{
    struct UsbMtpPort *mtpPort = static_cast<struct UsbMtpPort *>(OsalMemCalloc(sizeof(struct UsbMtpPort)));
    if (mtpPort == nullptr) {
        HDF_LOGE("%{public}s: Alloc usb mtpDev mtpPort failed", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    mtpPort->isActive = false;
    DListHeadInit(&mtpPort->readPool);
    DListHeadInit(&mtpPort->readQueue);
    DListHeadInit(&mtpPort->writePool);
    DListHeadInit(&mtpPort->writeQueue);
    mtpDev_->mtpPort = mtpPort;
    mtpPort->mtpDev = mtpDev_;
    mtpPort_ = mtpPort;
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceAllocNotifyRequest()
{
    mtpDev_->notifyReq =
        UsbFnAllocRequest(mtpDev_->intrIface.handle, mtpDev_->notifyPipe.id, MTP_EVENT_PACKET_MAX_BYTES);
    if (mtpDev_->notifyReq == nullptr) {
        HDF_LOGE("%{public}s: allocate notify request failed", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    mtpDev_->notifyReq->complete = UsbFnRequestNotifyComplete;
    mtpDev_->notifyReq->context = mtpDev_;
    return HDF_SUCCESS;
}

void UsbfnMtpImpl::UsbMtpDeviceFreeNotifyRequest()
{
    int32_t ret = UsbFnFreeRequest(mtpDev_->notifyReq);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: free notify request failed", __func__);
        return;
    }
    mtpDev_->notifyReq = nullptr;
}

int32_t UsbfnMtpImpl::UsbMtpDeviceFree()
{
    if (mtpDev_->mtpPort == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    (void)OsalMemFree(mtpDev_->mtpPort);
    mtpDev_->mtpPort = nullptr;
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::Init()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    HDF_LOGI("%{public}s: Init", __func__);
    pthread_rwlock_wrlock(&mtpRunrwLock_);
    if (mtpDev_ != nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGI("%{public}s: mtpDev_ is init success", __func__);
        return HDF_SUCCESS;
    }
    mtpDev_ = static_cast<struct UsbMtpDevice *>(OsalMemCalloc(sizeof(struct UsbMtpDevice)));
    if (mtpDev_ == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: usb mtpDev device failed or not initialized", __func__);
        return HDF_ERR_MALLOC_FAIL;
    }
    mtpDev_->initFlag = false;
    int32_t ret = UsbfnMtpImpl::UsbMtpDeviceCreateFuncDevice();
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: UsbMtpDeviceCreateFuncDevice failed", __func__);
        (void)OsalMemFree(mtpDev_);
        mtpDev_ = nullptr;
        pthread_rwlock_unlock(&mtpRunrwLock_);
        return ret;
    }
    ret = InitMtpPort();
    if (ret != HDF_SUCCESS) {
        goto ERR;
    }
    mtpDev_->initFlag = true;
    pthread_rwlock_unlock(&mtpRunrwLock_);
    HDF_LOGI("%{public}s: Init success", __func__);
    return HDF_SUCCESS;
ERR:
    (void)UsbMtpDeviceReleaseFuncDevice();
    (void)UsbMtpDeviceFree();
    (void)OsalMemFree(mtpDev_);
    mtpDev_ = nullptr;
    pthread_rwlock_unlock(&mtpRunrwLock_);
    return ret;
}

int32_t UsbfnMtpImpl::InitMtpPort()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    /* init mtpPort */
    int32_t ret = UsbMtpDeviceAlloc();
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: UsbMtpDeviceAlloc failed", __func__);
        return HDF_FAILURE;
    }
    ret = UsbMtpDeviceAllocCtrlRequests(MTP_CTRL_REQUEST_NUM);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: UsbMtpDeviceAllocCtrlRequests failed: %{public}d", __func__, MTP_CTRL_REQUEST_NUM);
        return HDF_FAILURE;
    }
    ret = UsbMtpDeviceAllocNotifyRequest();
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: UsbMtpDeviceAllocNotifyRequest failed", __func__);
        return HDF_FAILURE;
    }
    ret = UsbFnStartRecvInterfaceEvent(mtpDev_->ctrlIface.fn, 0xff, UsbMtpDeviceEp0EventDispatch, mtpDev_);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: register event callback failed", __func__);
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::Release()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    HDF_LOGI("%{public}s: Release", __func__);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    mtpDev_->initFlag = false;
    sem_post(&asyncReq_);
    {
        std::lock_guard<std::mutex> guard(asyncMutex_);
        (void)UsbMtpPortCancelRequest(mtpPort_);
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
    pthread_rwlock_wrlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    (void)UsbMtpPortReleaseIo();
    int32_t ret = UsbMtpDeviceReleaseFuncDevice();
    if (ret != HDF_SUCCESS) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: release device failed: %{public}d", __func__, ret);
        return ret;
    }
    ret = UsbMtpDeviceFree();
    if (ret != HDF_SUCCESS) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: free device failed: %{public}d", __func__, ret);
        return ret;
    }
    (void)OsalMemFree(mtpDev_);
    mtpDev_ = nullptr;
    pthread_rwlock_unlock(&mtpRunrwLock_);
    HDF_LOGI("%{public}s: Release success", __func__);
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::Start()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    HDF_LOGI("%{public}s: start", __func__);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    if (mtpPort_->isActive) {
        sem_post(&asyncReq_);
        (void)UsbMtpPortCancelRequest(mtpPort_);
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGI("%{public}s: is active end", __func__);
        return HDF_SUCCESS;
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);

    pthread_rwlock_wrlock(&mtpRunrwLock_);
    std::lock_guard<std::mutex> guard(startMutex_);
    int32_t ret = UsbMtpPortInitIo();
    if (ret != HDF_SUCCESS) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: request failed: %{public}d", __func__, ret);
        return ret;
    }
    mtpDev_->mtpState = MTP_STATE_READY;
    mtpPort_->startDelayed = true;
    mtpPort_->isActive = true;
    pthread_rwlock_unlock(&mtpRunrwLock_);
    HDF_LOGI("%{public}s: end", __func__);
    return ret;
}

int32_t UsbfnMtpImpl::Stop()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    HDF_LOGI("%{public}s: start", __func__);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    sem_post(&asyncReq_);
    (void)UsbMtpPortCancelRequest(mtpPort_);
    pthread_rwlock_unlock(&mtpRunrwLock_);

    pthread_rwlock_wrlock(&mtpRunrwLock_);
    std::lock_guard<std::mutex> guard(startMutex_);
    (void)UsbMtpPortReleaseIo();
    mtpPort_->startDelayed = false;
    mtpPort_->isActive = false;
    if (mtpDev_ != nullptr) {
        mtpDev_->mtpState = MTP_STATE_OFFLINE;
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
    HDF_LOGI("%{public}s: end", __func__);
    return HDF_SUCCESS;
}

uint32_t UsbfnMtpImpl::BufCopyToVector(void *buf, uint32_t bufSize, std::vector<uint8_t> &vectorData)
{
    uint8_t *addr = static_cast<uint8_t *>(buf);
    vectorData.assign(addr, addr + bufSize);
    return bufSize;
}

uint32_t UsbfnMtpImpl::BufCopyFromVector(
    void *buf, uint32_t bufSize, const std::vector<uint8_t> &vectorData, uint32_t vectorOffset)
{
    uint32_t count = (bufSize + vectorOffset) < vectorData.size() ? bufSize : vectorData.size() - vectorOffset;
    uint8_t *addr = static_cast<uint8_t *>(buf);
    for (size_t i = 0; i < count; i++) {
        addr[i] = vectorData.at(vectorOffset + i);
    }
    return count;
}

int32_t UsbfnMtpImpl::Read(std::vector<uint8_t> &data)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    if (mtpDev_->mtpState == MTP_STATE_OFFLINE || mtpDev_->mtpPort == nullptr || mtpDev_->mtpPort->suspended) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: device disconnect, no-operation, mtpState is %{public}u", __func__, mtpDev_->mtpState);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        mtpDev_->mtpState = MTP_STATE_READY;
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: states is ecanceled", __func__);
        return HDF_ERROR_ECANCEL;
    }
    std::lock_guard<std::mutex> guard(readMutex_);
    if (!mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: dev is release", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    mtpDev_->mtpState = MTP_STATE_BUSY;
    int32_t ret = ReadImpl(data);
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: running, states is ecanceled", __func__);
        ret = HDF_ERROR_ECANCEL;
    } else if (mtpDev_->mtpState != MTP_STATE_OFFLINE) {
        mtpDev_->mtpState = MTP_STATE_READY;
    }
    writeActualLen_ = 0;
    vectorSplited_.clear();
    pthread_rwlock_unlock(&mtpRunrwLock_);
    return ret;
}

void UsbfnMtpImpl::ReadZLP(uint32_t length, uint32_t actual)
{
    if (actual != length || actual != MTP_BUFFER_SIZE) {
        return;
    }
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    struct DListHead *pool = &mtpPort_->readPool;
    if (pool == nullptr || DListIsEmpty(pool)) {
        HDF_LOGE("%{public}s: invalid readPool", __func__);
        return;
    }
    struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
    if (req == nullptr) {
        HDF_LOGE("%{public}s: req invalid", __func__);
        return;
    }
    RemoveReqFromList(req);
    DListInsertTail(&req->list, &mtpPort_->readQueue);
    req->length = ZERO_LENGTH_PACKET;
    (void)UsbFnSubmitRequestSync(req, ZERO_LENGTH_PACKET_JIFFIES);
    RemoveReqFromList(req);
    DListInsertTail(&req->list, pool);
}

int32_t UsbfnMtpImpl::ReadImpl(std::vector<uint8_t> &data)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    int32_t ret = HDF_FAILURE;
    struct UsbFnRequest *req = nullptr;
    if (mtpPort_->standbyReq != nullptr && mtpPort_->standbyReq->actual >= REQ_ACTUAL_MININUM_LENGTH) {
        req = mtpPort_->standbyReq;
    } else {
        struct DListHead *pool = &mtpPort_->readPool;
        if (pool == nullptr || DListIsEmpty(pool)) {
            HDF_LOGE("%{public}s: invalid readPool", __func__);
            return HDF_DEV_ERR_DEV_INIT_FAIL;
        }
        req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
        if (req == nullptr) {
            HDF_LOGE("%{public}s: req invalid", __func__);
            return HDF_DEV_ERR_DEV_INIT_FAIL;
        }
        RemoveReqFromList(req);
        DListInsertTail(&req->list, &mtpPort_->readQueue);
        req->length = static_cast<uint32_t>(MTP_BUFFER_SIZE);
        ret = UsbFnSubmitRequestSync(req, BULK_OUT_TIMEOUT_JIFFIES);
        RemoveReqFromList(req);
        DListInsertTail(&req->list, pool);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: send bulk-out sync req failed: %{public}d", __func__, ret);
            return ret;
        }
    }

    switch (req->status) {
        case USB_REQUEST_COMPLETED:
            (void)BufCopyToVector(req->buf, req->actual, data);
            ReadZLP(req->length, getActualLength(data));
            break;
        case USB_REQUEST_NO_DEVICE:
            HDF_LOGE("%{public}s: device disconnect", __func__);
            mtpDev_->mtpState = MTP_STATE_OFFLINE;
            ret = HDF_DEV_ERR_NO_DEVICE;
            break;
        default:
            HDF_LOGE("%{public}s: unexpected status %{public}d", __func__, req->status);
            ret = HDF_ERR_IO;
            break;
    }
    req->actual = REQ_ACTUAL_DEFAULT_LENGTH;
    return ret;
}

int32_t UsbfnMtpImpl::WriteEx(const std::vector<uint8_t> &data, uint8_t needZLP, uint32_t &xferActual)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    struct DListHead *pool = &mtpPort_->writePool;
    struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
    RemoveReqFromList(req);
    DListInsertTail(&req->list, &mtpPort_->writeQueue);
    uint32_t needXferCount = data.size();
    int32_t ret = HDF_SUCCESS;
    while (needXferCount > 0 || needZLP == ZLP_NEED) {
        req->actual = 0;
        uint32_t reqMax = static_cast<uint32_t>(MTP_BUFFER_SIZE);
        req->length = reqMax > needXferCount ? needXferCount : reqMax;
        if (needXferCount == 0) {
            needZLP = ZLP_TRY;
            req->length = 0;
        }
        if (mtpDev_->mtpState != MTP_STATE_BUSY) {
            ret = HDF_ERR_IO;
            break;
        }
        (void)BufCopyFromVector(req->buf, req->length, data, xferActual);
        HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestSync");
        ret = UsbFnSubmitRequestSync(req, BULK_IN_TIMEOUT_JIFFIES);
        if (needZLP == ZLP_TRY) {
            HDF_LOGE("%{public}s: send zero packet done: %{public}d", __func__, ret);
            break;
        }
        switch (req->status) {
            case USB_REQUEST_COMPLETED:
                needXferCount -= req->actual;
                xferActual += req->actual;
                break;
            case USB_REQUEST_NO_DEVICE:
                HDF_LOGE("%{public}s: device disconnected", __func__);
                mtpDev_->mtpState = MTP_STATE_OFFLINE;
                ret = HDF_DEV_ERR_NO_DEVICE;
                break;
            default:
                HDF_LOGE("%{public}s: unexpected status %{public}d", __func__, req->status);
                ret = HDF_ERR_IO;
                break;
        }
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: bulk-in req failed: %{public}d", __func__, ret);
            break;
        } else if (!mtpDev_->initFlag) {
            HDF_LOGE("%{public}s: initFlag is false now.", __func__);
            ret = HDF_DEV_ERR_DEV_INIT_FAIL;
            break;
        }
    }
    RemoveReqFromList(req);
    DListInsertTail(&req->list, pool);
    return ret;
}

uint32_t UsbfnMtpImpl::getActualLength(const std::vector<uint8_t> &data)
{
    if (data.size() < MTP_PROTOCOL_PACKET_SIZE) {
        return data.size();
    }
    uint32_t length;
    std::copy(data.data(), data.data() + MTP_PROTOCOL_PACKET_SIZE,
	    reinterpret_cast<uint8_t*>(&length));
    return length;
}

int32_t UsbfnMtpImpl::WriteSplitPacket(const std::vector<uint8_t> &data)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    if (data.size() > WRITE_SPLIT_MININUM_LENGTH && writeActualLen_ == 0) {
        uint32_t writeLen = getActualLength(data);
        if (writeLen > data.size()) {
            vectorSplited_.resize(writeLen);
            std::copy(data.begin(), data.end(), vectorSplited_.begin());
            writeActualLen_ = data.size();
            return HDF_SUCCESS;
        }
    }
    if (vectorSplited_.size() > WRITE_SPLIT_MININUM_LENGTH &&
        (data.size() < vectorSplited_.size() - writeActualLen_)) {
        std::copy(data.begin(), data.end(), vectorSplited_.begin() + writeActualLen_);
        writeActualLen_ += data.size();
        return HDF_SUCCESS;
    } else if (vectorSplited_.size() > WRITE_SPLIT_MININUM_LENGTH &&
        (data.size() > vectorSplited_.size() - writeActualLen_)) {
        vectorSplited_.clear();
        writeActualLen_ = 0;
        return HDF_ERR_INVALID_PARAM;
    } else if (vectorSplited_.size() > WRITE_SPLIT_MININUM_LENGTH &&
        (data.size() == vectorSplited_.size() - writeActualLen_)) {
        std::copy(data.begin(), data.end(), vectorSplited_.begin() + writeActualLen_);
        writeActualLen_ += data.size();
    }

    std::lock_guard<std::mutex> guard(writeMutex_);
    if (DListIsEmpty(&mtpPort_->writePool) || !mtpDev_->initFlag) {
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    mtpDev_->mtpState = MTP_STATE_BUSY;
    uint32_t xferActual = 0;
    uint8_t needZLP = ZLP_NO_NEED;
    uint32_t needXferCount = vectorSplited_.size() > WRITE_SPLIT_MININUM_LENGTH ?
        vectorSplited_.size() : data.size();
    if ((needXferCount & (mtpDev_->dataInPipe.maxPacketSize - 1)) == 0) {
        needZLP = ZLP_NEED;
    }
    int32_t ret = HDF_FAILURE;
    if (writeActualLen_ > WRITE_SPLIT_MININUM_LENGTH &&
        vectorSplited_.size() == writeActualLen_) {
        ret = WriteEx(vectorSplited_, needZLP, xferActual);
        vectorSplited_.clear();
        writeActualLen_ = 0;
    } else {
        ret = WriteEx(data, needZLP, xferActual);
    }
    return ret;
}

int32_t UsbfnMtpImpl::Write(const std::vector<uint8_t> &data)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    if (mtpDev_->mtpState == MTP_STATE_OFFLINE || mtpDev_->mtpPort == nullptr || mtpDev_->mtpPort->suspended) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: device disconnect", __func__);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    if (data.size() == 0) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGW("%{public}s: no data need to send", __func__);
        return HDF_SUCCESS;
    }
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        mtpDev_->mtpState = MTP_STATE_READY;
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: states is ecanceled", __func__);
        return HDF_ERROR_ECANCEL;
    }
    int32_t ret = WriteSplitPacket(data);
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: running, states is ecanceled", __func__);
        ret = HDF_ERROR_ECANCEL;
    } else if (mtpDev_->mtpState != MTP_STATE_OFFLINE) {
        mtpDev_->mtpState = MTP_STATE_READY;
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortRxCheckReq(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req, bool &writeToFile)
{
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    switch (req->status) {
        case USB_REQUEST_NO_DEVICE:
            mtpDev->mtpState = MTP_STATE_OFFLINE;
            HDF_LOGE("%{public}s: rx req return disconnected", __func__);
            return HDF_DEV_ERR_NO_DEVICE;
        case USB_REQUEST_COMPLETED:
            break;
        default:
            HDF_LOGE("%{public}s: unexpected status %{public}d", __func__, req->status);
            return HDF_FAILURE;
    }
    if (req->actual == 0) {
        HDF_LOGD("%{public}s: recv ZLP packet, end xfer", __func__);
        mtpDev->asyncXferFile = ASYNC_XFER_FILE_DONE;
        return HDF_SUCCESS;
    }
    if (mtpDev->xferFileLength == MTP_MAX_FILE_SIZE) {
        /* no specific length */
        writeToFile = true;
        if (req->actual < req->length) {
            /* short packet indicate transfer end */
            mtpDev->asyncXferFile = ASYNC_XFER_FILE_DONE;
        }
        /* normal full packet, also write to file */
        return HDF_SUCCESS;
    }
    /* specific length */
    if (req->actual < req->length) {
        HDF_LOGE("%{public}s: normal packet(error): %{public}u < %{public}u", __func__, req->actual, req->length);
        return HDF_FAILURE;
    }
    if (req->actual != 0) {
        writeToFile = true;
    }
    if (mtpDev->asyncRecvFileActual + static_cast<uint64_t>(req->actual) == mtpDev->xferFileLength) {
        if (mtpDev->needZLP != ZLP_NEED) {
            mtpDev->asyncXferFile = ASYNC_XFER_FILE_DONE;
        }
        HDF_LOGD("%{public}s: last packet: req(%{public}d/%{public}d)%{public}u/%{public}u, recv %{public}" PRIu64
            "/%{public}" PRIu64 "/%{public}" PRIu64 ",need zlp:%{public}d", __func__, mtpPort->readStarted,
            mtpPort->readAllocated, req->actual, req->length, mtpDev->asyncRecvFileExpect, mtpDev->asyncRecvFileActual,
            mtpDev->xferFileLength, mtpDev->needZLP);
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortProcessAsyncRxDone(struct UsbMtpPort *mtpPort)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    HDF_LOGD("%{public}s: recv done, ignore other packet(%{public}d/%{public}d):%{public}" PRIu64 "/%{public}" PRIu64
        "/%{public}" PRIu64 "", __func__, mtpPort->readStarted, mtpPort->readAllocated, mtpDev->asyncRecvFileExpect,
        mtpDev->asyncRecvFileActual, mtpDev->xferFileLength);
    if (mtpPort->readStarted == 0) {
        sem_post(&asyncReq_);
    } else if (mtpDev->xferFileLength == MTP_MAX_FILE_SIZE) {
        HDF_LOGD("%{public}s: cancel redundant req", __func__);
        while (!DListIsEmpty(&mtpPort->readQueue)) {
            struct UsbFnRequest *req = DLIST_FIRST_ENTRY(&mtpPort->readQueue, struct UsbFnRequest, list);
            (void)UsbFnCancelRequest(req);
            if (req->list.prev != NULL && req->list.next != NULL) {
                DListRemove(&req->list);
            } else {
                HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
            }
            DListInsertTail(&req->list, &mtpPort->readPool);
        }
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortRxPush(struct UsbMtpPort *mtpPort, struct UsbFnRequest *req)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    if (mtpPort == nullptr || mtpPort->mtpDev == nullptr) {
        HDF_LOGE("%{public}s: invalid param", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    bool writeToFile = false;
    int32_t ret = UsbMtpPortRxCheckReq(mtpPort, req, writeToFile);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: req failed: %{public}d", __func__, ret);
        sem_post(&asyncReq_);
        return HDF_ERR_IO;
    }
    if (writeToFile && mtpDev->asyncRecvWriteTempContent) {
        uint8_t *bufOff = mtpDev->asyncRecvWriteTempContent + mtpDev->asyncRecvWriteTempCount;
        if (memcpy_s(bufOff, req->actual, req->buf, req->actual) != EOK) {
            HDF_LOGE("%{public}s: memcpy_s failed", __func__);
            return HDF_FAILURE;
        }
        mtpDev->asyncRecvWriteTempCount += req->actual;
        if (mtpDev->asyncRecvWriteTempCount >= WRITE_FILE_TEMP_SLICE) {
            ssize_t writeRet = write(mtpDev->xferFd, static_cast<void *>(mtpDev->asyncRecvWriteTempContent),
                static_cast<size_t>(WRITE_FILE_TEMP_SLICE));
            if (writeRet != static_cast<ssize_t>(WRITE_FILE_TEMP_SLICE)) {
                HDF_LOGE("%{public}s: write temp failed: %{public}zd", __func__, writeRet);
                mtpDev->asyncXferFile = ASYNC_XFER_FILE_DONE;
                sem_post(&asyncReq_);
                return HDF_FAILURE;
            }
            mtpDev->asyncRecvWriteTempCount = 0;
        }
        mtpDev->asyncRecvFileActual += static_cast<uint64_t>(req->actual);
    }
    if (mtpDev->asyncXferFile == ASYNC_XFER_FILE_DONE && mtpDev->asyncRecvWriteTempContent) {
        ssize_t writeRet = write(mtpDev->xferFd, static_cast<void *>(mtpDev->asyncRecvWriteTempContent),
            static_cast<size_t>(mtpDev->asyncRecvWriteTempCount));
        if (writeRet != static_cast<ssize_t>(mtpDev->asyncRecvWriteTempCount)) {
            HDF_LOGE("%{public}s: write last failed: %{public}d", __func__, mtpDev->asyncRecvWriteTempCount);
            mtpDev->asyncXferFile = ASYNC_XFER_FILE_DONE;
            sem_post(&asyncReq_);
            return HDF_FAILURE;
        }
        return UsbMtpPortProcessAsyncRxDone(mtpPort);
    }
    if ((mtpDev->xferFileLength == MTP_MAX_FILE_SIZE) || (mtpDev->asyncRecvFileActual == mtpDev->xferFileLength) ||
        (mtpDev->xferFileLength != MTP_MAX_FILE_SIZE && mtpDev->asyncRecvFileExpect != mtpDev->xferFileLength)) {
        ret = UsbMtpPortStartRxAsync(mtpPort);
    }
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortStartSubmitRxReq(struct UsbMtpPort *mtpPort, bool needZLP)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    struct DListHead *pool = &mtpPort->readPool;
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
    uint64_t reqMax = static_cast<uint64_t>(MTP_BUFFER_SIZE);
    if (mtpDev->asyncRecvFileExpect + reqMax < mtpDev->xferFileLength) {
        req->length = static_cast<uint32_t>(MTP_BUFFER_SIZE);
    } else if (mtpDev->xferFileLength == MTP_MAX_FILE_SIZE) {
        req->length = static_cast<uint32_t>(MTP_BUFFER_SIZE);
    } else {
        req->length = static_cast<uint32_t>(mtpDev->xferFileLength - mtpDev->asyncRecvFileExpect);
    }

    if (needZLP) {
        req->length = 0;
    }
    RemoveReqFromList(req);
    DListInsertTail(&req->list, &mtpPort->readQueue);
    HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestAsync " + std::to_string(req->reqId));
    StartAsyncTrace(HITRACE_TAG_HDF, "asyncIO", req->reqId);
    int32_t ret = UsbFnSubmitRequestAsync(req);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: submit bulk-out req error %{public}d", __func__, ret);
        if (req->list.prev != NULL && req->list.next != NULL) {
            DListRemove(&req->list);
        } else {
            HDF_LOGE("%{public}s: The node prev or next is NULL", __func__);
        }
        DListInsertTail(&req->list, pool);
        return ret;
    }
    mtpPort->readStarted++;
    mtpDev->asyncRecvFileExpect += static_cast<uint64_t>(req->length);
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortStartRxAsync(struct UsbMtpPort *mtpPort)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    std::lock_guard<std::mutex> guard(asyncMutex_);
    struct DListHead *pool = &mtpPort->readPool;
    struct UsbMtpDevice *mtpDev = mtpPort->mtpDev;
    int32_t ret = HDF_SUCCESS;
    while (!DListIsEmpty(pool)) {
        if (mtpPort->readStarted >= mtpPort->readAllocated) {
            HDF_LOGW("%{public}s no idle read req(BULK-OUT): %{public}d/%{public}d", __func__, mtpPort->readStarted,
                mtpPort->readAllocated);
            ret = HDF_ERR_DEVICE_BUSY;
            break;
        }
        if (mtpDev->mtpState == MTP_STATE_OFFLINE) {
            HDF_LOGE("%{public}s: device disconnect, stop rx", __func__);
            ret = HDF_DEV_ERR_NO_DEVICE;
            break;
        }
        if (mtpDev->asyncRecvFileActual == mtpDev->xferFileLength) {
            HDF_LOGD("%{public}s: recv a zlp", __func__);
            return UsbMtpPortStartSubmitRxReq(mtpPort, true);
        }
        if ((mtpDev->xferFileLength != MTP_MAX_FILE_SIZE && mtpDev->asyncRecvFileExpect >= mtpDev->xferFileLength) ||
            mtpDev->asyncXferFile == ASYNC_XFER_FILE_DONE) {
            HDF_LOGD("%{public}s: no need rx req[%{public}d/%{public}d]:%{public}" PRIu64 "/%{public}" PRIu64
                "/%{public}" PRIu64 ", xfer=%{public}hhu", __func__, mtpPort->readStarted, mtpPort->readAllocated,
                mtpDev->asyncRecvFileExpect, mtpDev->asyncRecvFileActual, mtpDev->xferFileLength,
                mtpDev->asyncXferFile);
            return ret;
        }
        ret = UsbMtpPortStartSubmitRxReq(mtpPort, false);
        if (ret != HDF_SUCCESS) {
            HDF_LOGE("%{public}s: submit bulk-out req error %{public}d", __func__, ret);
            break;
        }
    }
    return ret;
}

int32_t UsbfnMtpImpl::ReceiveFileEx()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    sem_init(&asyncReq_, 1, 0);
    mtpDev_->asyncXferFile = ASYNC_XFER_FILE_NORMAL;
    mtpDev_->asyncRecvWriteTempContent = static_cast<uint8_t *>(OsalMemCalloc(WRITE_FILE_TEMP_SLICE));
    mtpDev_->asyncRecvWriteTempCount = 0;
    int32_t ret = UsbMtpPortStartRxAsync(mtpPort_);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: start async tx failed: %{public}d", __func__, ret);
        (void)OsalMemFree(mtpDev_->asyncRecvWriteTempContent);
        mtpDev_->asyncRecvWriteTempContent = nullptr;
        return HDF_ERR_IO;
    }
    HDF_LOGD("%{public}s: wait async rx", __func__);
    sem_wait(&asyncReq_);
    (void)OsalMemFree(mtpDev_->asyncRecvWriteTempContent);
    mtpDev_->asyncRecvWriteTempContent = nullptr;
    if (syncfs(mtpDev_->xferFd) != 0) {
        HDF_LOGE("%{public}s: failed: commit filesystem caches to disk", __func__);
        return HDF_ERR_IO;
    }
    if (mtpDev_->xferFileLength == MTP_MAX_FILE_SIZE) {
        HDF_LOGE("%{public}s: no specific length, reset state", __func__);
        mtpDev_->mtpState = MTP_STATE_READY;
        return mtpDev_->asyncXferFile == ASYNC_XFER_FILE_DONE ? HDF_SUCCESS : HDF_ERR_IO;
    }
    return mtpDev_->asyncRecvFileActual == mtpDev_->xferFileLength ? HDF_SUCCESS : HDF_ERR_IO;
}

int32_t UsbfnMtpImpl::ReceiveFile(const UsbFnMtpFileSlice &mfs)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    ON_SCOPE_EXIT(release) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        close(mfs.fd);
    };
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    if (mtpDev_->mtpState == MTP_STATE_OFFLINE || mtpDev_->mtpPort == nullptr || mtpDev_->mtpPort->suspended) {
        HDF_LOGE("%{public}s: device disconnect", __func__);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    if (mfs.length <= 0) {
        return HDF_SUCCESS;
    }
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        mtpDev_->mtpState = MTP_STATE_READY;
        HDF_LOGE("%{public}s: states is ecanceled", __func__);
        return HDF_ERROR_ECANCEL;
    }
    std::lock_guard<std::mutex> guard(readMutex_);
    if (!mtpDev_->initFlag) {
        HDF_LOGE("%{public}s: dev is release", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    mtpDev_->mtpState = MTP_STATE_BUSY;
    mtpDev_->xferFd = mfs.fd;
    mtpDev_->xferFileOffset = mfs.offset;
    mtpDev_->xferFileLength = static_cast<uint64_t>(mfs.length);
    lseek(mfs.fd, mfs.offset, SEEK_SET);
    mtpDev_->asyncRecvFileActual = 0;
    mtpDev_->asyncRecvFileExpect = 0;
    mtpDev_->needZLP = ZLP_NO_NEED;
    if ((mtpDev_->xferFileLength & (mtpDev_->dataInPipe.maxPacketSize - 1)) == 0) {
        mtpDev_->needZLP = ZLP_NEED;
    }
    int32_t ret = ReceiveFileEx();
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: running, states is ecanceled", __func__);
        ret = HDF_ERROR_ECANCEL;
    } else if (mtpDev_->mtpState != MTP_STATE_OFFLINE) {
        mtpDev_->mtpState = MTP_STATE_READY;
    }
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortSendFileFillFirstReq(struct UsbFnRequest *req, uint64_t &oneReqLeft)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    uint64_t hdrSize = static_cast<uint64_t>((mtpDev_->xferSendHeader == 1) ? sizeof(struct UsbMtpDataHeader) : 0);
    uint64_t needXferCount = mtpDev_->xferFileLength + hdrSize;
    uint64_t reqMax = static_cast<uint64_t>(MTP_BUFFER_SIZE);
    req->length = (reqMax > needXferCount) ? static_cast<uint32_t>(needXferCount) : static_cast<uint32_t>(reqMax);
    if (hdrSize != 0) {
        /* write MTP header first */
        struct UsbMtpDataHeader *header = static_cast<struct UsbMtpDataHeader *>(req->buf);
        /* set file size with header according to MTP Specification v1.0 */
        header->length =
            static_cast<uint32_t>(needXferCount > MTP_MAX_FILE_SIZE ? MTP_MAX_FILE_SIZE : CPU_TO_LE32(needXferCount));
        /* type value 2 specified data packet */
        header->type = CPU_TO_LE16(2);
        header->cmdCode = CPU_TO_LE16(mtpDev_->xferCommand);
        header->transactionId = CPU_TO_LE32(mtpDev_->xferTransactionId);
    }
    uint8_t *bufOffset = static_cast<uint8_t *>(req->buf) + hdrSize;
    oneReqLeft = (hdrSize + mtpDev_->xferFileLength < reqMax) ? mtpDev_->xferFileLength : reqMax - hdrSize;
    ssize_t readRet = read(mtpDev_->xferFd, static_cast<void *>(bufOffset), static_cast<size_t>(oneReqLeft));
    if (readRet != static_cast<ssize_t>(oneReqLeft)) {
        HDF_LOGE("%{public}s: read failed: error: %{public}d, %{public}zd vs %{public}" PRId64 "",
            __func__, errno, readRet, oneReqLeft);
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

int32_t UsbfnMtpImpl::UsbMtpPortSendFileEx()
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    if (DListIsEmpty(&mtpPort_->writePool)) {
        HDF_LOGE("%{public}s: writePool is empty.", __func__);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    struct DListHead *pool = &mtpPort_->writePool;
    struct UsbFnRequest *req = DLIST_FIRST_ENTRY(pool, struct UsbFnRequest, list);
    if (req == nullptr) {
        HDF_LOGE("%{public}s: req invalid", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    RemoveReqFromList(req);
    DListInsertTail(&req->list, &mtpPort_->writeQueue);
    uint64_t oneReqLeft = 0;
    int32_t ret = UsbMtpPortSendFileFillFirstReq(req, oneReqLeft);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: fill first sync bulk-in req failed: %{public}d", __func__, ret);
        RemoveReqFromList(req);
        DListInsertTail(&req->list, pool);
        return ret;
    }
    ret = UsbFnSubmitRequestSync(req, BULK_IN_TIMEOUT_JIFFIES);
    RemoveReqFromList(req);
    DListInsertTail(&req->list, pool);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: bulk-in req failed: %{public}d", __func__, ret);
        return ret;
    }
    switch (req->status) {
        case USB_REQUEST_COMPLETED:
            break;
        case USB_REQUEST_NO_DEVICE:
            HDF_LOGE("%{public}s: device disconnected", __func__);
            mtpDev_->mtpState = MTP_STATE_OFFLINE;
            return HDF_DEV_ERR_NO_DEVICE;
        default:
            HDF_LOGD("%{public}s: unexpected status %{public}d", __func__, req->status);
            return HDF_ERR_IO;
    }
    if (!mtpDev_->initFlag || mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: dev is release or canceled", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    if (oneReqLeft != mtpDev_->xferFileLength || mtpDev_->needZLP) {
        ret = UsbMtpPortSendFileLeftAsync(oneReqLeft);
    }
    return ret;
}

int32_t UsbfnMtpImpl::UsbMtpPortSendFileLeftAsync(uint64_t oneReqLeft)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    mtpDev_->xferFileLength -= oneReqLeft;
    mtpDev_->asyncSendFileActual = 0;
    mtpDev_->asyncSendFileExpect = 0;
    sem_init(&asyncReq_, 1, 0);
    mtpDev_->asyncXferFile = ASYNC_XFER_FILE_NORMAL;
    if (UsbMtpPortStartTxAsync(mtpPort_, false) != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: start async tx failed", __func__);
        return HDF_ERR_IO;
    }
    HDF_LOGD("%{public}s: wait async tx", __func__);
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: dev is canceled", __func__);
        return HDF_ERROR_ECANCEL;
    }
    sem_wait(&asyncReq_);
    return (mtpDev_->mtpState == MTP_STATE_ERROR) ? HDF_ERR_IO : HDF_SUCCESS;
}

void UsbfnMtpImpl::UsbMtpSendFileParamSet(const UsbFnMtpFileSlice &mfs)
{
    mtpDev_->xferFd = mfs.fd;
    mtpDev_->xferFileOffset = static_cast<uint64_t>(mfs.offset);
    mtpDev_->xferFileLength = static_cast<uint64_t>(mfs.length);
    mtpDev_->xferCommand = mfs.command;
    mtpDev_->xferTransactionId = mfs.transactionId;
    mtpDev_->xferSendHeader = (mfs.command == 0 && mfs.transactionId == 0) ? 0 : 1;
    return;
}

int32_t UsbfnMtpImpl::SendFile(const UsbFnMtpFileSlice &mfs)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    ON_SCOPE_EXIT(release) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        close(mfs.fd);
    };
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    UsbMtpSendFileParamSet(mfs);
    uint64_t hdrSize = (mtpDev_->xferSendHeader == 1) ? static_cast<uint64_t>(sizeof(struct UsbMtpDataHeader)) : 0;
    uint64_t needXferCount = mfs.length + hdrSize;
    lseek(mfs.fd, mfs.offset, SEEK_SET);

    if (needXferCount == 0 || mfs.length < 0) {
        HDF_LOGW("%{public}s: no data need to send", __func__);
        return HDF_SUCCESS;
    }
    if (mtpDev_->mtpState == MTP_STATE_OFFLINE || mtpDev_->mtpPort == nullptr || mtpDev_->mtpPort->suspended) {
        HDF_LOGE("%{public}s: device disconnect", __func__);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        mtpDev_->mtpState = MTP_STATE_READY;
        HDF_LOGE("%{public}s: states is ecanceled", __func__);
        return HDF_ERROR_ECANCEL;
    }
    std::lock_guard<std::mutex> guard(writeMutex_);
    if (!mtpDev_->initFlag) {
        HDF_LOGE("%{public}s: dev is release", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    mtpDev_->mtpState = MTP_STATE_BUSY;
    mtpDev_->needZLP = ZLP_NO_NEED;
    if ((needXferCount & (mtpDev_->dataInPipe.maxPacketSize - 1)) == 0) {
        mtpDev_->needZLP = ZLP_NEED;
    }
    int32_t ret = UsbMtpPortSendFileEx();
    if (mtpDev_->mtpState == MTP_STATE_CANCELED) {
        HDF_LOGE("%{public}s: running, states is ecanceled", __func__);
        ret = HDF_ERROR_ECANCEL;
    } else if (mtpDev_->mtpState != MTP_STATE_OFFLINE) {
        mtpDev_->mtpState = MTP_STATE_READY;
    }
    return ret;
}

int32_t UsbfnMtpImpl::SendEvent(const std::vector<uint8_t> &eventData)
{
    HITRACE_METER_NAME(HITRACE_TAG_HDF, MTP_FUNCTION);
    pthread_rwlock_rdlock(&mtpRunrwLock_);
    if (mtpPort_ == nullptr || mtpDev_ == nullptr || !mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: no init", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }

    if (eventData.size() > MTP_EVENT_PACKET_MAX_BYTES || eventData.size() == 0) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: length is invald: %{public}zu", __func__, eventData.size());
        return HDF_FAILURE;
    }
    if (mtpDev_->mtpState == MTP_STATE_OFFLINE || mtpDev_->mtpPort == nullptr || mtpDev_->mtpPort->suspended) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: device disconnect, mtpState is %{public}u", __func__, mtpDev_->mtpState);
        return HDF_DEV_ERR_NO_DEVICE;
    }
    std::lock_guard<std::mutex> guard(eventMutex_);
    if (!mtpDev_->initFlag) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: dev is release", __func__);
        return HDF_DEV_ERR_DEV_INIT_FAIL;
    }
    struct UsbFnRequest *req = mtpDev_->notifyReq;
    if (req == nullptr || req->buf == nullptr) {
        pthread_rwlock_unlock(&mtpRunrwLock_);
        HDF_LOGE("%{public}s: notify req is null", __func__);
        return HDF_ERR_INVALID_PARAM;
    }
    if (memcpy_s(req->buf, eventData.size(), eventData.data(), eventData.size()) != EOK) {
        HDF_LOGE("%{public}s: memcpy_s failed", __func__);
        (void)UsbFnFreeRequest(req);
        pthread_rwlock_unlock(&mtpRunrwLock_);
        return HDF_FAILURE;
    }
    req->length = static_cast<uint32_t>(eventData.size());
    HITRACE_METER_NAME(HITRACE_TAG_HDF, "MTP_UsbFnSubmitRequestSync");
    int32_t ret = UsbFnSubmitRequestSync(req, INTR_IN_TIMEOUT_JIFFIES);
    if (ret != HDF_SUCCESS) {
        HDF_LOGE("%{public}s: send notify sync request failed: %{public}d", __func__, ret);
    }
    pthread_rwlock_unlock(&mtpRunrwLock_);
    return ret;
}
} // namespace V1_0
} // namespace Mtp
} // namespace Gadget
} // namespace Usb
} // namespace HDI
} // namespace OHOS
