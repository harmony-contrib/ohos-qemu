/*
* Copyright (C) 2022 Huawei Device Co., Ltd.
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
#define MLOG_TAG "MtpDriver"
#include "mtp_driver.h"
#include <cinttypes>
#include "media_log.h"
#include "media_mtp_utils.h"
#include "medialibrary_tracer.h"
#include "mtp_dfx_reporter.h"
#include "mtp_operation_utils.h"
#include "mtp_packet_tools.h"
#include <fcntl.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>
#include <sys/ioctl.h>
#include "v1_0/iusb_interface.h"

#define MTP_SEND_FILE              _IOW('M', 0, struct MtpFileRange)
/*
 * Receives data from the host and writes it to a file.
 * The file is created if it does not exist.
 */
#define MTP_RECEIVE_FILE           _IOW('M', 1, struct MtpFileRange)
/* Sends an event to the host via the interrupt endpoint */
#define MTP_SEND_EVENT             _IOW('M', 3, struct EventMtp)
/*
 * Sends the specified file range to the host,
 * with a 12 byte MTP data packet header at the beginning.
 */
#define MTP_SEND_FILE_WITH_HEADER  _IOW('M', 4, struct MtpFileRange)

using namespace std;
using namespace OHOS::HDI::Usb::Gadget::Mtp::V1_0;
namespace OHOS {
namespace Media {
const int READ_SIZE = 10240;

MtpDriver::MtpDriver()
{
}

MtpDriver::~MtpDriver()
{
    CloseDriver();
}

int MtpDriver::OpenDriver()
{
    MEDIA_INFO_LOG("MtpDriver::OpenDriver start");
    usbfnMtpInterface = IUsbfnMtpInterface::Get();
    CHECK_AND_RETURN_RET_LOG(usbfnMtpInterface != nullptr, HDF_DEV_ERR_DEV_INIT_FAIL,
        "IUsbfnMtpInterface::Get() failed.");

    auto ret = usbfnMtpInterface->Start();
    CHECK_AND_RETURN_RET_LOG(ret == 0, ret, "MtpDriver::OpenDriver Start() failed error = %{public}d", ret);
    usbOpenFlag = true;
    MEDIA_INFO_LOG("MtpDriver::OpenDriver end");
    return MTP_SUCCESS;
}

int MtpDriver::CloseDriver()
{
    usbOpenFlag = false;
    usbfnMtpInterface = nullptr;
    return MTP_SUCCESS;
}

int MtpDriver::Read(std::vector<uint8_t> &outBuffer, uint32_t &outReadSize)
{
    MediaLibraryTracer tracer;
    tracer.Start("MTP MtpDriver::Read");
    if (usbOpenFlag == false) {
        int ret = OpenDriver();
        if (ret < 0) {
            return ret;
        }
    }

    CHECK_AND_RETURN_RET_LOG(usbfnMtpInterface != nullptr, E_ERR, "Read: usbfnMtpInterface is nullptr");
    if (outReadSize == 0) {
        outReadSize = READ_SIZE;
    }

    MEDIA_DEBUG_LOG("MtpDriver::Read start");
    outBuffer.resize(outReadSize);

    tracer.Start("MTP usbfnMtpInterface->Read");
    auto startTime = std::chrono::high_resolution_clock::now();
    auto ret = usbfnMtpInterface->Read(outBuffer);
    auto endTime = std::chrono::high_resolution_clock::now();
    std::chrono::duration<uint16_t, std::milli> duration =
        std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime);
    tracer.Finish();

    MEDIA_DEBUG_LOG("MtpDriver::Read end ret:%{public}d", ret);
    if (ret != 0) {
        outReadSize = 0;
        int offset = 0;
        uint16_t operationCode = MtpPacketTool::GetUInt16(outBuffer[offset + OFFSET_6], outBuffer[offset + OFFSET_7]);
        MtpDfxReporter::GetInstance().DoSendResponseResultDfxReporter(operationCode, ret,
            duration.count(), OperateMode::readmode);
        MEDIA_ERR_LOG("MtpDriver::Read Out Error: %{public}d", ret);
        return ret;
    }
    outReadSize = outBuffer.size();
    MtpPacketTool::DumpPacket(outBuffer);
    return MTP_SUCCESS;
}

void MtpDriver::Write(std::vector<uint8_t> &buffer, uint32_t &bufferSize, int32_t &result)
{
    MediaLibraryTracer tracer;
    tracer.Start("MTP MtpDriver::Write");
    CHECK_AND_RETURN_LOG(usbfnMtpInterface != nullptr, "Write: usbfnMtpInterface is nullptr");
    MtpPacketTool::DumpPacket(buffer);
    MEDIA_DEBUG_LOG("MtpDriver::Write start, buffer.size:%{public}zu", buffer.size());

    tracer.Start("MTP usbfnMtpInterface->Write");
    auto ret = usbfnMtpInterface->Write(buffer);
    tracer.Finish();

    bufferSize = static_cast<uint32_t>(ret);
    result = ret;
    MEDIA_DEBUG_LOG("MtpDriver::Write end, ret:%{public}d", ret);
}

int MtpDriver::ReceiveObj(MtpFileRange &mfr)
{
    MediaLibraryTracer tracer;
    tracer.Start("MTP MtpDriver::ReceiveObj");
    CHECK_AND_RETURN_RET_LOG(usbfnMtpInterface != nullptr, E_ERR, "ReceiveObj: usbfnMtpInterface is nullptr");
    MEDIA_DEBUG_LOG("MtpDriver::ReceiveObj start");
    struct UsbFnMtpFileSlice mfs = {
        .fd = mfr.fd,
        .offset = mfr.offset,
        .length = mfr.length,
        .command = mfr.command,
        .transactionId = mfr.transaction_id,
    };

    MEDIA_INFO_LOG("MtpDriver::ReceiveObj fd:%{public}d offset:%{public}" PRId64 ", length:%{public}" PRId64,
        mfs.fd, mfs.offset, mfs.length);
    tracer.Start("MTP usbfnMtpInterface->ReceiveFile");
    auto ret = usbfnMtpInterface->ReceiveFile(mfs);
    tracer.Finish();

    MEDIA_INFO_LOG("MtpDriver::ReceiveObj end ret:%{public}d", ret);
    return ret;
}

int MtpDriver::SendObj(MtpFileRange &mfr)
{
    MediaLibraryTracer tracer;
    tracer.Start("MTP MtpDriver::SendObj");
    CHECK_AND_RETURN_RET_LOG(usbfnMtpInterface != nullptr, E_ERR, "SendObj: usbfnMtpInterface is nullptr");
    MEDIA_DEBUG_LOG("MtpDriver::SendObj start");
    struct UsbFnMtpFileSlice mfs = {
        .fd = mfr.fd,
        .offset = mfr.offset,
        .length = mfr.length,
        .command = mfr.command,
        .transactionId = mfr.transaction_id,
    };

    tracer.Start("MTP usbfnMtpInterface->SendFile");
    auto ret = usbfnMtpInterface->SendFile(mfs);
    tracer.Finish();

    MEDIA_DEBUG_LOG("MtpDriver::SendObj end ret:%{public}d", ret);
    return ret;
}

int MtpDriver::WriteEvent(EventMtp &em)
{
    MediaLibraryTracer tracer;
    tracer.Start("MTP MtpDriver::WriteEvent");
    CHECK_AND_RETURN_RET_LOG(usbfnMtpInterface != nullptr, E_ERR, "WriteEvent: usbfnMtpInterface is nullptr");
    MtpPacketTool::DumpPacket(em.data);
    MEDIA_DEBUG_LOG("MtpDriver::WriteEvent start");

    tracer.Start("MTP usbfnMtpInterface->SendEvent");
    auto ret =  usbfnMtpInterface->SendEvent(em.data);
    tracer.Finish();

    MEDIA_DEBUG_LOG("MtpDriver::WriteEvent end ret:%{public}d", ret);
    return ret;
}
} // namespace Media
} // namespace OHOS