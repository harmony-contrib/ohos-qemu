/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
#ifndef OHOS_CONTACT_PICKER_PROTOCOL_H
#define OHOS_CONTACT_PICKER_PROTOCOL_H

#include <algorithm>
#include <array>
#include <cstdint>
#include <mutex>
#include <string>
#include "nlohmann/json.hpp"

namespace OHOS::ContactsApi {
// A result is published only after a terminal frame and a complete, consistent
// set of data frames. This class owns no NAPI values, windows or caller context.
class ContactPickerProtocol {
public:
    static constexpr int32_t SYSTEM_ERROR = 16700001;
    static constexpr int32_t MAX_CONTACTS = 10000;
    static constexpr int32_t CONTACTS_PER_FRAME = 100;
    static constexpr int32_t MAX_FRAMES = MAX_CONTACTS / CONTACTS_PER_FRAME;
    static constexpr size_t MAX_FRAME_BYTES = 16 * 1024 * 1024;
    static constexpr size_t MAX_RESULT_BYTES = 128 * 1024 * 1024;
    struct Result {
        bool ready = false;
        int32_t code = SYSTEM_ERROR;
        int32_t total = 0;
        std::string data = "[]";
    };

    bool Receive(bool validTypes, int32_t index, int32_t total, const std::string &data)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (result_.ready) { return false; }
        // Check types and every bound BEFORE accessing a frame or parsing JSON.
        if (!validTypes || total < 0 || total > MAX_CONTACTS || index < 0 || index >= MAX_FRAMES) {
            return FailLocked(SYSTEM_ERROR);
        }
        const int32_t count = total == 0 ? 1 : (total + CONTACTS_PER_FRAME - 1) / CONTACTS_PER_FRAME;
        if (index >= count || seen_[index] || (total_ >= 0 && total_ != total) ||
            data.size() > MAX_FRAME_BYTES || bytes_ > MAX_RESULT_BYTES - data.size() || !BoundedDepth(data)) {
            return FailLocked(SYSTEM_ERROR);
        }
        auto frame = nlohmann::json::parse(data, nullptr, false);
        const int32_t expected = total == 0 ? 0 : std::min(CONTACTS_PER_FRAME, total - index * CONTACTS_PER_FRAME);
        if (!frame.is_array() || frame.size() != static_cast<size_t>(expected)) {
            return FailLocked(SYSTEM_ERROR);
        }
        for (const auto &contact : frame) {
            if (!contact.is_object()) { return FailLocked(SYSTEM_ERROR); }
        }
        frames_[index] = std::move(frame);
        seen_[index] = true;
        ++received_;
        total_ = total;
        bytes_ += data.size();
        return false;
    }

    bool Finish(int32_t code)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (result_.ready) { return false; }
        if (code == 1 && received_ == 0) {
            result_.code = 1;
            result_.ready = true;
            return true;
        }
        if (code != 0) { return FailLocked(NormalizeError(code)); }
        const int32_t count = total_ == 0 ? 1 : (total_ + CONTACTS_PER_FRAME - 1) / CONTACTS_PER_FRAME;
        if (total_ < 0 || received_ != count) { return FailLocked(SYSTEM_ERROR); }
        auto contacts = nlohmann::json::array();
        for (int32_t i = 0; i < count; ++i) {
            if (!seen_[i]) { return FailLocked(SYSTEM_ERROR); }
            for (auto &contact : frames_[i]) { contacts.push_back(std::move(contact)); }
        }
        if (contacts.size() != static_cast<size_t>(total_)) { return FailLocked(SYSTEM_ERROR); }
        result_.data = contacts.dump();
        if (result_.data.size() > MAX_RESULT_BYTES) { return FailLocked(SYSTEM_ERROR); }
        result_.code = 0;
        result_.total = total_;
        result_.ready = true;
        ClearFrames();
        return true;
    }

    bool Fail(int32_t code = SYSTEM_ERROR)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return result_.ready ? false : FailLocked(NormalizeError(code));
    }

    Result Snapshot() const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return result_;
    }

private:
    static int32_t NormalizeError(int32_t code)
    {
        switch (code) {
            case 201:
            case 202:
            case 401:
            case 801:
            case SYSTEM_ERROR:
            case 16700002:
            case 16700004:
            case 16700101:
                return code;
            default:
                return SYSTEM_ERROR;
        }
    }

    static bool BoundedDepth(const std::string &text)
    {
        int depth = 0;
        bool quoted = false;
        bool escaped = false;
        for (char c : text) {
            if (quoted) {
                if (escaped) { escaped = false; }
                else if (c == '\\') { escaped = true; }
                else if (c == '"') { quoted = false; }
            } else if (c == '"') { quoted = true; }
            else if (c == '[' || c == '{') { if (++depth > 64) { return false; } }
            else if (c == ']' || c == '}') { if (--depth < 0) { return false; } }
        }
        return !quoted && depth == 0;
    }

    void ClearFrames()
    {
        for (auto &frame : frames_) { frame = nullptr; }
    }

    bool FailLocked(int32_t code)
    {
        result_ = { true, code, 0, "[]" };
        ClearFrames();
        return true;
    }

    mutable std::mutex mutex_;
    Result result_;
    std::array<nlohmann::json, MAX_FRAMES> frames_;
    std::array<bool, MAX_FRAMES> seen_ {};
    int32_t total_ = -1;
    int32_t received_ = 0;
    size_t bytes_ = 0;
};
} // namespace OHOS::ContactsApi
#endif
