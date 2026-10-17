// Exact consumer functions are inserted below. Service/BMS doubles are host-only.
#include <cassert>
#include <memory>
#include <string>
#include <vector>
#include "reminder_calendar_share_table.h"
using OHOS::Notification::ReminderCalendarShareTable;
template<class T> using sptr = std::shared_ptr<T>;
#define ANSR_LOGI(...) ((void)0)
#define ANSR_LOGE(...) ((void)0)
#define NOTIFICATION_HITRACE(...) ((void)0)
using ErrCode = int;
static constexpr ErrCode ERR_OK = 0;
static constexpr int8_t CALENDAR_RDB_V1 = 1;
static constexpr int8_t CALENDAR_RDB_V2 = 2;
namespace AppExecFwk {
struct Metadata { std::string name, value; };
struct HapModuleInfo { std::vector<Metadata> metadata; };
struct BundleInfo { std::vector<HapModuleInfo> hapModuleInfos; };
enum class BundleFlag { GET_BUNDLE_WITH_EXTENSION_INFO };
}
struct ReminderRequest {
    enum class RingChannel { NOTIFICATION };
    struct WantAgentInfo { std::string pkgName, abilityName, uri; };
    std::shared_ptr<WantAgentInfo> want = std::make_shared<WantAgentInfo>();
    int uid = -1, creatorUid = -1, userId = -1;
    std::string bundle, creator;
    void SetRingDuration(int) {}
    void SetRingLoop(bool) {}
    void SetRingChannel(RingChannel) {}
    void InitUserId(int value) { userId = value; }
    void InitUid(int value) { uid = value; }
    void InitCreatorUid(int value) { creatorUid = value; }
    void SetShare(bool) {}
    void InitBundleName(const char* value) { bundle = value; }
    void InitCreatorBundleName(const char* value) { creator = value; }
    void SetSystemApp(bool) {}
    void SetTapDismissed(bool) {}
    auto GetWantAgentInfo() { return want; }
};
struct ReminderBundleManagerHelper {
    std::string schemaName = "ohos.calendardata.reminderDbVersion", schemaVersion = "2";
    bool bundleAvailable = true;
    static ReminderBundleManagerHelper& GetInstance() { static ReminderBundleManagerHelper instance; return instance; }
    int GetDefaultUidByBundleName(const char* name, int userId) {
        assert(userId == 100);
        return std::string(name) == "com.ohos.calendardata" ? 3001 : -1;
    }
    bool GetBundleInfo(const char* name, AppExecFwk::BundleFlag, int uid, AppExecFwk::BundleInfo& info) {
        assert(std::string(name) == "com.ohos.calendardata" && uid == 3001);
        if (!bundleAvailable) return false;
        info.hapModuleInfos = {{{{schemaName, schemaVersion}}}};
        return true;
    }
};
struct ReminderDataShareHelper {
    int userId_ = 100, uid_ = -1, dataUid_ = 3001;
    int8_t rdbVersion_ = 0;
    int resets = 0;
    static ReminderDataShareHelper& GetInstance() { static ReminderDataShareHelper instance; return instance; }
    void ResetUid() { ++resets; uid_ = -1; }
    void InitNormalInfo(sptr<ReminderRequest>& reminder);
    void CheckWantAgent(sptr<ReminderRequest>& reminder);
    void UpdateCalendarUid();
};
struct ReminderDataManager {
    std::string cancelled;
    void CancelRemindersImplLocked(const std::string& bundle, int userId, int uid) {
        assert(userId == 100 && uid == 3001); cancelled = bundle;
    }
    ErrCode CancelAllReminders(const std::string& bundleName, const int32_t userId,
                              const int32_t callingUid, const bool isUninstallApp);
};
// ACTUAL_FUNCTIONS
int main(int argc, char** argv) {
    assert(argc == 2);
    bool fixed = std::string(argv[1]) == "fixed";
    ReminderDataShareHelper helper;
    helper.UpdateCalendarUid();
    assert(helper.rdbVersion_ == (fixed ? 2 : 0));
    auto& bms = ReminderBundleManagerHelper::GetInstance();
    for (const auto& name : {"ohos.calendardata.reminderDbVersion", "hmos.calendardata.reminderDbVersion"}) {
        for (const auto& version : {"1", "2", "3", "invalid"}) {
            bms.schemaName = name; bms.schemaVersion = version;
            ReminderDataShareHelper check; check.UpdateCalendarUid();
            bool supported = fixed || std::string(name).starts_with("hmos.");
            int expected = supported && std::string(version) == "1" ? 1 :
                supported && std::string(version) == "2" ? 2 : 0;
            assert(check.rdbVersion_ == expected);
        }
    }
    bms.bundleAvailable = false;
    ReminderDataShareHelper missing; missing.UpdateCalendarUid(); assert(missing.rdbVersion_ == 0);
    bms.bundleAvailable = true;
    auto reminder = std::make_shared<ReminderRequest>();
    reminder->want->pkgName = "com.ohos.calendardata";
    reminder->want->abilityName = "MainAbility";
    const std::string uri = "calendar://com.ohos.calendar?event_id=42&start=100&end=200";
    reminder->want->uri = uri;
    helper.InitNormalInfo(reminder);
    helper.CheckWantAgent(reminder);
    assert(reminder->creatorUid == 3001 && reminder->creator == "com.ohos.calendardata");
    if (fixed) {
        assert(reminder->uid == 3001 && reminder->bundle == "com.ohos.calendardata");
        assert(reminder->want->pkgName == "com.ohos.calendardata");
        assert(reminder->want->abilityName == "MainAbility" && reminder->want->uri == uri);
    } else {
        assert(reminder->uid == -1 && reminder->bundle == "com.ohos.calendar");
        assert(reminder->want->uri.empty());
    }
    reminder->want.reset(); helper.CheckWantAgent(reminder);
    reminder->want = std::make_shared<ReminderRequest::WantAgentInfo>();
    reminder->want->pkgName = "malicious.other";
    reminder->want->uri = "https://untrusted.invalid";
    helper.CheckWantAgent(reminder);
    assert(reminder->want->uri.empty());
    ReminderDataManager manager;
    auto& singleton = ReminderDataShareHelper::GetInstance();
    assert(manager.CancelAllReminders("com.ohos.calendardata", 100, 3001, true) == ERR_OK);
    assert(manager.cancelled == "com.ohos.calendardata");
    assert(singleton.resets == (fixed ? 1 : 0));
    manager.CancelAllReminders("another.bundle", 100, 3001, true);
    manager.CancelAllReminders("com.ohos.calendardata", 100, 3001, false);
    assert(singleton.resets == (fixed ? 1 : 0));
}
