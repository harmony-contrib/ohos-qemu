/* SPDX-License-Identifier: Apache-2.0 */
#include "knowledge_holiday_index.h"
#include "medialibrary_log.h"
#include "rdb_errno.h"
#include "transaction.h"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <map>
#include <mutex>
#include <openssl/sha.h>
#include <set>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>
namespace OHOS::Media {
namespace {
constexpr size_t MAX_BYTES = 1024 * 1024;
constexpr size_t MAX_LINE = 8192;
constexpr size_t MAX_LINES = 131136;
constexpr size_t MAX_EVENTS = 4096;
constexpr size_t MAX_DAYS = 20000;
constexpr int MAX_SPAN = 366;
constexpr size_t MAX_TEXT = 1024;
constexpr const char *DIRECTORY = "/system/etc/knowledge-content";
constexpr const char *FILENAME = "holidays.ics";
constexpr const char *SCHEMA = "CREATE TABLE IF NOT EXISTS KnowledgeHoliday("
    "uid TEXT NOT NULL,instance_start TEXT NOT NULL,civil_date TEXT NOT NULL,name TEXT NOT NULL,"
    "entity_id TEXT NOT NULL,PRIMARY KEY(uid,instance_start,civil_date))";
constexpr const char *META = "CREATE TABLE IF NOT EXISTS KnowledgeHolidayResource("
    "id INTEGER PRIMARY KEY CHECK(id=1),schema_version INTEGER NOT NULL,sha256 TEXT NOT NULL,"
    "present INTEGER NOT NULL CHECK(present IN(0,1)),row_count INTEGER NOT NULL)";
struct Day { int year; int month; int day; };
struct Event { std::string uid; std::string name; std::string start; std::string end; };
struct Entry { std::string uid; std::string start; std::string day; std::string name; std::string id; };
struct Resource { bool present = false; std::string hash = "absent"; std::vector<Entry> entries; };
bool Leap(int year) { return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0); }
int MonthDays(int year, int month)
{
    constexpr int DAYS[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    return DAYS[month - 1] + (month == 2 && Leap(year) ? 1 : 0);
}
bool Date(const std::string &text, Day &value)
{
    if (text.size() != 8 || !std::all_of(text.begin(), text.end(), [](char c) {return c >= '0' && c <= '9';})) return false;
    value = {std::stoi(text.substr(0, 4)), std::stoi(text.substr(4, 2)), std::stoi(text.substr(6, 2))};
    return value.year >= 1600 && value.year <= 9999 && value.month >= 1 && value.month <= 12 &&
        value.day >= 1 && value.day <= MonthDays(value.year, value.month);
}
std::string Format(const Day &value)
{
    char text[9]{};
    if (snprintf(text, sizeof(text), "%04d%02d%02d", value.year, value.month, value.day) != 8) return {};
    return text;
}
bool Next(Day &value)
{
    if (++value.day > MonthDays(value.year, value.month)) {
        value.day = 1;
        if (++value.month > 12) {value.month = 1; ++value.year;}
    }
    return value.year <= 9999;
}
bool Utf8(const std::string &text)
{
    size_t index = 0;
    while (index < text.size()) {
        uint32_t code = static_cast<unsigned char>(text[index++]);
        if (code == 0 || code == '\r' || (code < 0x20 && code != '\n' && code != '\t')) return false;
        if (code < 0x80) continue;
        int tails;
        uint32_t minimum;
        if (code >= 0xc2 && code <= 0xdf) {tails = 1; minimum = 0x80; code &= 0x1f;}
        else if (code >= 0xe0 && code <= 0xef) {tails = 2; minimum = 0x800; code &= 0x0f;}
        else if (code >= 0xf0 && code <= 0xf4) {tails = 3; minimum = 0x10000; code &= 0x07;}
        else return false;
        for (int tail = 0; tail < tails; ++tail) {
            if (index == text.size()) return false;
            unsigned char next = static_cast<unsigned char>(text[index++]);
            if ((next & 0xc0) != 0x80) return false;
            code = (code << 6) | (next & 0x3f);
        }
        if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return false;
    }
    return true;
}
std::string Upper(std::string text)
{
    for (char &c : text) if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
    return text;
}
bool Text(const std::string &encoded, std::string &value)
{
    value.clear();
    for (size_t i = 0; i < encoded.size(); ++i) {
        char c = encoded[i];
        if (c == '\\') {
            if (++i == encoded.size()) return false;
            c = encoded[i];
            if (c == 'N' || c == 'n') c = '\n';
            else if (c != '\\' && c != ',' && c != ';') return false;
        }
        value += c;
        if (value.size() > MAX_TEXT) return false;
    }
    return !value.empty() && Utf8(value);
}
bool Lines(const std::string &bytes, std::vector<std::string> &lines)
{
    if (bytes.empty() || bytes.size() > MAX_BYTES || bytes.find('\0') != std::string::npos) return false;
    size_t start = 0;
    while (start < bytes.size()) {
        size_t end = bytes.find('\n', start);
        if (end == std::string::npos) end = bytes.size();
        std::string line = bytes.substr(start, end - start);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.find('\r') != std::string::npos || line.size() > MAX_LINE) return false;
        if (!line.empty() && (line[0] == ' ' || line[0] == '\t')) {
            if (lines.empty() || lines.back().size() + line.size() - 1 > MAX_LINE) return false;
            lines.back().append(line.substr(1));
        } else if (!line.empty()) {
            if (lines.size() >= MAX_LINES) return false;
            lines.push_back(std::move(line));
        }
        start = end + 1;
    }
    return !lines.empty() && std::all_of(lines.begin(),lines.end(),[](const std::string &line) {return Utf8(line);});
}
bool Expand(const Event &event, std::vector<Entry> &entries)
{
    Day start{}, end{};
    if (event.uid.empty() || event.name.empty() || !Date(event.start, start)) return false;
    if (event.end.empty()) {end = start; if (!Next(end)) return false;}
    else if (!Date(event.end, end)) return false;
    const std::string exclusive = Format(end);
    if (exclusive <= event.start) return false;
    Day current = start;
    int span = 0;
    while (Format(current) < exclusive) {
        if (++span > MAX_SPAN || entries.size() >= MAX_DAYS) return false;
        // Length prefix prevents a UID containing delimiters from aliasing another instance.
        const std::string id = std::to_string(event.uid.size()) + ":" + event.uid + ":" + event.start;
        entries.push_back({event.uid,event.start,Format(current),event.name,id});
        if (!Next(current)) return false;
    }
    return true;
}
bool ParseCalendar(const std::string &bytes, std::vector<Entry> &entries)
{
    std::vector<std::string> lines;
    if (!Lines(bytes, lines) || Upper(lines.front()) != "BEGIN:VCALENDAR" ||
        Upper(lines.back()) != "END:VCALENDAR") return false;
    bool inside = false, version = false;
    Event event;
    std::set<std::string> properties;
    std::map<std::string, Event> events;
    const std::set<std::string> harmless = {"DTSTAMP","CREATED","LAST-MODIFIED","SEQUENCE","DESCRIPTION", "TRANSP", "CLASS"};
    for (size_t index = 1; index + 1 < lines.size(); ++index) {
        const std::string &line = lines[index];
        const size_t colon = line.find(':');
        if (colon == std::string::npos) return false;
        const std::string property = Upper(line.substr(0, colon));
        const std::string value = line.substr(colon + 1);
        if (property == "BEGIN") {
            if (inside || Upper(value) != "VEVENT") return false;
            inside = true; event = {}; properties.clear(); continue;
        }
        if (property == "END") {
            if (!inside || Upper(value) != "VEVENT" || event.uid.empty() || event.start.empty() || event.name.empty()) return false;
            auto previous = events.find(event.uid);
            if (previous != events.end()) {
                if (previous->second.start != event.start || previous->second.end != event.end || previous->second.name != event.name) return false;
            } else {
                if (events.size() >= MAX_EVENTS) return false;
                events.emplace(event.uid,event);
            }
            inside = false; continue;
        }
        if (!inside) {
            if (property == "VERSION") {if (version || value != "2.0") return false; version = true;}
            else if (property == "CALSCALE") {if (Upper(value) != "GREGORIAN") return false;}
            else if (property == "METHOD") {if (Upper(value) != "PUBLISH") return false;}
            else if (property != "PRODID" && property.rfind("X-", 0) != 0) return false;
            continue;
        }
        const size_t semicolon = property.find(';');
        const std::string key = property.substr(0, semicolon);
        if (!properties.insert(key).second) return false;
        if (key == "UID") {
            if (property != "UID" || !Text(value,event.uid) || event.uid.find('\n') != std::string::npos) return false;
        } else if (key == "SUMMARY") {
            if (semicolon != std::string::npos) {
                const std::string language = property.substr(semicolon + 1);
                if (language.rfind("LANGUAGE=", 0) != 0 || language.size() == 9 ||
                    !std::all_of(language.begin()+9,language.end(),[](char c) {return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-';})) return false;
            }
            if (!Text(value,event.name)) return false;
        } else if (key == "DTSTART" || key == "DTEND") {
            Day parsed{};
            if (property != key + ";VALUE=DATE" || !Date(value,parsed)) return false;
            if (key == "DTSTART") event.start = value;
            else event.end = value;
        } else if (key == "STATUS") {
            if (property != "STATUS" || Upper(value) != "CONFIRMED") return false;
        } else if (harmless.count(key) == 0) {
            // RRULE/RDATE/EXDATE/RECURRENCE-ID, timed/TZID dates and nested components
            // are unsupported resources; never silently drop or invent occurrences.
            return false;
        }
    }
    if (inside || !version) return false;
    std::vector<Entry> parsed;
    for (const auto &[uid,item] : events) {
        (void)uid;
        if (!Expand(item,parsed)) return false;
    }
    entries = std::move(parsed);
    return true;
}
bool Trusted(const struct stat &info, bool directory)
{
    return (directory ? S_ISDIR(info.st_mode) : S_ISREG(info.st_mode)) &&
        (info.st_uid == 0 || info.st_uid == 1000) && (info.st_mode & (S_IWGRP | S_IWOTH)) == 0;
}
int Load(Resource &resource)
{
    int directory = open(DIRECTORY, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) return errno == ENOENT ? NativeRdb::E_OK : NativeRdb::E_ERROR;
    struct stat parent{};
    if (fstat(directory,&parent) != 0 || !Trusted(parent,true)) {close(directory); return NativeRdb::E_ERROR;}
    int fd = openat(directory,FILENAME,O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    const int saved = errno;
    close(directory);
    if (fd < 0) return saved == ENOENT ? NativeRdb::E_OK : NativeRdb::E_ERROR;
    struct stat before{}, after{};
    if (fstat(fd,&before) != 0 || !Trusted(before,false) || before.st_size <= 0 || static_cast<uint64_t>(before.st_size) > MAX_BYTES) {
        close(fd); return NativeRdb::E_ERROR;
    }
    std::string bytes(static_cast<size_t>(before.st_size),'\0');
    size_t offset = 0;
    while (offset < bytes.size()) {
        const ssize_t count = read(fd,bytes.data()+offset,bytes.size()-offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) {close(fd); return NativeRdb::E_ERROR;}
        offset += static_cast<size_t>(count);
    }
    char extra;
    ssize_t extraCount;
    do {extraCount = read(fd,&extra,1);} while (extraCount < 0 && errno == EINTR);
    const bool stable = extraCount == 0 && fstat(fd,&after) == 0 && before.st_dev == after.st_dev &&
        before.st_ino == after.st_ino && before.st_size == after.st_size && before.st_mtime == after.st_mtime &&
        before.st_ctime == after.st_ctime && Trusted(after,false)
#if defined(__APPLE__)
        && before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec && before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec
#else
        && before.st_mtim.tv_nsec == after.st_mtim.tv_nsec && before.st_ctim.tv_nsec == after.st_ctim.tv_nsec
#endif
        ;
    if (close(fd) != 0 || !stable || !ParseCalendar(bytes,resource.entries)) return NativeRdb::E_ERROR;
    unsigned char digest[SHA256_DIGEST_LENGTH];
    if (SHA256(reinterpret_cast<const unsigned char *>(bytes.data()),bytes.size(),digest) == nullptr) return NativeRdb::E_ERROR;
    constexpr char HEX[] = "0123456789abcdef";
    resource.hash.clear();
    for (unsigned char byte : digest) {resource.hash += HEX[byte >> 4]; resource.hash += HEX[byte & 15];}
    resource.present = true;
    return NativeRdb::E_OK;
}
int Synchronize(NativeRdb::RdbStore &store)
{
    const auto created = store.CreateTransaction(NativeRdb::Transaction::IMMEDIATE);
    const auto transaction = created.second;
    if (created.first != NativeRdb::E_OK || transaction == nullptr) {
        return created.first == NativeRdb::E_OK ? NativeRdb::E_ERROR : created.first;
    }
    struct TransactionScope {
        std::shared_ptr<NativeRdb::Transaction> value;
        bool committed = false;
        bool closed = false;
        int Close() {closed = true; return value->Close();}
        ~TransactionScope() {if (!committed) value->Rollback(); if (!closed) value->Close();}
    } scope{transaction};
    auto execute = [&](const std::string &sql, const std::vector<NativeRdb::ValueObject> &args = {}) {
        return transaction->Execute(sql,args).first;
    };
    for (const char *sql : {SCHEMA,META,"CREATE INDEX IF NOT EXISTS idx_knowledge_holiday_day ON KnowledgeHoliday(civil_date)"}) {
        const int result = execute(sql);
        if (result != NativeRdb::E_OK) return result;
    }
    // Serialize resource snapshots with the native IMMEDIATE transaction rather
    // than holding an application/lifecycle mutex across external RDB calls.
    Resource resource;
    const int loaded = Load(resource);
    if (loaded != NativeRdb::E_OK) {
        // An old database still gains the schema. Invalid/I/O-denied resources
        // cannot replace a committed index or its acknowledged resource hash.
        const int committed = transaction->Commit();
        if (committed != NativeRdb::E_OK) return committed;
        scope.committed = true;
        const int closed = scope.Close();
        if (closed != NativeRdb::E_OK) return closed;
        MEDIA_ERR_LOG("Knowledge holiday resource unavailable; retaining committed index: %{public}d", loaded);
        return loaded;
    }
    // A source version is acknowledged only with the complete data transaction.
    int result = execute("DELETE FROM KnowledgeHoliday");
    if (result != NativeRdb::E_OK) return result;
    for (const auto &entry : resource.entries) {
        result = execute("INSERT INTO KnowledgeHoliday(uid,instance_start,civil_date,name,entity_id) VALUES(?,?,?,?,?)",
            {entry.uid,entry.start,entry.day,entry.name,entry.id});
        if (result != NativeRdb::E_OK) return result;
    }
    result = execute("INSERT OR REPLACE INTO KnowledgeHolidayResource(id,schema_version,sha256,present,row_count) VALUES(1,1,?,?,?)",
        {resource.hash,static_cast<int64_t>(resource.present),static_cast<int64_t>(resource.entries.size())});
    if (result != NativeRdb::E_OK) return result;
    result = transaction->Commit();
    if (result != NativeRdb::E_OK) return result;
    scope.committed = true;
    return scope.Close();
}
// The service owns one observer for its static shared RDB. No callback captures
// MediaLibraryRdbStore/this or a raw RdbStore. A weak reference becomes strong
// only during an import and is released before the cancellable wait.
struct ObserverState {
    std::mutex mutex;
    std::condition_variable wake;
    bool cancelled = false;
    std::weak_ptr<NativeRdb::RdbStore> store;
    void Cancel()
    {
        {std::lock_guard<std::mutex> lock(mutex); cancelled = true;}
        wake.notify_all();
    }
};
class ObserverOwner final {
public:
    ~ObserverOwner() {Stop();}
    int Stop()
    {
        std::thread previous;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            if (state_ != nullptr) state_->Cancel();
            // A re-entrant RDB callback cannot join its own worker, including
            // when an external Stop has already moved that worker for joining.
            const auto caller = std::this_thread::get_id();
            if ((worker_.joinable() && worker_.get_id() == caller) ||
                (joining_ && joiningId_ == caller)) return NativeRdb::E_ERROR;
            joined_.wait(lock,[this] {return !joining_;});
            if (state_ != nullptr) state_->Cancel();
            previous = std::move(worker_);
            state_.reset();
            joining_ = previous.joinable();
            joiningId_ = previous.get_id();
        }
        if (previous.joinable()) previous.join(); // no lock needed by worker held
        {
            std::lock_guard<std::mutex> lock(mutex_);
            joining_ = false;
            joiningId_ = {};
        }
        joined_.notify_all();
        return NativeRdb::E_OK;
    }
    int Start(const std::shared_ptr<NativeRdb::RdbStore> &store)
    {
        if (store == nullptr || Stop() != NativeRdb::E_OK) return NativeRdb::E_ERROR;
        try {
            auto state = std::make_shared<ObserverState>();
            state->store = store;
            std::lock_guard<std::mutex> lock(mutex_);
            if (worker_.joinable() || joining_) return NativeRdb::E_ERROR;
            state_ = state;
            worker_ = std::thread([state] {
                std::string lastHash;
                bool lastPresent = false;
                bool acknowledged = false;
                std::unique_lock<std::mutex> wait(state->mutex);
                while (!state->wake.wait_for(wait,std::chrono::seconds(5),[&state] {return state->cancelled;})) {
                    wait.unlock();
                    auto live = state->store.lock();
                    if (live == nullptr) return;
                    Resource observed;
                    int result = NativeRdb::E_ERROR;
                    try {
                        result = Load(observed);
                        if (result == NativeRdb::E_OK && (!acknowledged ||
                            observed.hash != lastHash || observed.present != lastPresent)) {
                            result = KnowledgeHolidayIndex::Refresh(*live);
                            if (result == NativeRdb::E_OK) {
                                lastHash = observed.hash;
                                lastPresent = observed.present;
                                acknowledged = true;
                            }
                        }
                    } catch (...) {result = NativeRdb::E_ERROR;}
                    if (result != NativeRdb::E_OK) MEDIA_ERR_LOG("Knowledge calendar configuration refresh failed: %{public}d", result);
                    live.reset();
                    wait.lock();
                }
            });
        } catch (...) {return NativeRdb::E_ERROR;}
        return NativeRdb::E_OK;
    }
private:
    std::mutex mutex_;
    std::condition_variable joined_;
    bool joining_ = false;
    std::thread::id joiningId_;
    std::shared_ptr<ObserverState> state_;
    std::thread worker_;
};
ObserverOwner &Observer()
{
    static ObserverOwner owner;
    return owner;
}
}
int32_t KnowledgeHolidayIndex::Refresh(NativeRdb::RdbStore &store)
{
    try {
        return Synchronize(store);
    } catch (...) {
        MEDIA_ERR_LOG("Knowledge holiday import allocation/parser failure; retaining committed index");
        return NativeRdb::E_ERROR;
    }
}
int32_t KnowledgeHolidayIndex::Observe(const std::shared_ptr<NativeRdb::RdbStore> &store)
{
    // Bounded fixed-path polling also covers absent/replaced directories and
    // watcher invalidation. It does not provide any write/update API or bypass
    // the system partition's read-only policy.
    return Observer().Start(store);
}
int32_t KnowledgeHolidayIndex::StopObserver()
{
    return Observer().Stop();
}
}
