"""Exercise actual consumer functions and exact provider composition; no guest claim."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import test_calendar_main_integration as composition_tests

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/notification/distributed_notification_service/calendar_provider_owner'
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())
HEADER = 'services/reminder/include/reminder_calendar_share_table.h'
HELPER = 'services/reminder/src/reminder_datashare_helper.cpp'


class CalendarReminderOwnerTests(unittest.TestCase):
    def prepare(self):
        composition = composition_tests.CalendarMainIntegrationTests('runTest')
        self.addCleanup(composition.doCleanups)
        case = composition.prepare()
        target = case.root / MANIFEST['project'] / HEADER
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((COMPONENT / 'tests/reminder_calendar_share_table.h.before').read_bytes())
        helper = case.root / MANIFEST['project'] / HELPER
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_bytes(gzip.decompress(base64.b64decode((COMPONENT / 'tests/reminder_datashare_helper.cpp.gz.b64').read_bytes())))
        return case, target

    def apply(self, case):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(case.root)],
                              capture_output=True, text=True, timeout=15)

    def test_real_provider_then_exact_owner_idempotence(self):
        case, target = self.prepare()
        for _ in range(2):
            result = self.apply(case)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), MANIFEST['files'][HEADER]['after_sha256'])

    def test_unknown_owner_or_incomplete_main_cannot_be_overwritten(self):
        case, target = self.prepare()
        original = target.read_bytes()
        target.write_bytes(original + b'// unknown edit\n')
        before = target.read_bytes()
        self.assertNotEqual(self.apply(case).returncode, 0)
        self.assertEqual(target.read_bytes(), before)
        target.write_bytes(original)
        route = case.project / 'entry/src/main/ets/calendar/CalendarRoute.ets'
        route.unlink()
        self.assertNotEqual(self.apply(case).returncode, 0)
        self.assertEqual(target.read_bytes(), original)

    def test_actual_consumer_old_owner_fails_and_fixed_owner_preserves_real_uri(self):
        case, target = self.prepare()
        module = json.loads((case.project / 'entry/src/main/module.json5').read_text())['module']
        self.assertEqual([entry for entry in module['metadata']
                          if entry['name'] == 'ohos.calendardata.reminderDbVersion'],
                         [{'name': 'ohos.calendardata.reminderDbVersion', 'value': '2'}])
        self.assertEqual(json.loads((case.project / 'AppScope/app.json5').read_text())['app']['bundleName'],
                         'com.ohos.calendardata')
        fixture = gzip.decompress(base64.b64decode((COMPONENT / 'tests/reminder_datashare_helper.cpp.gz.b64').read_bytes()))
        self.assertEqual(hashlib.sha256(fixture).hexdigest(), MANIFEST['source_consumer_fixture']['uncompressed_sha256'])
        def actual_functions(source):
            functions = []
            for begin, end in (
                ('void ReminderDataShareHelper::UpdateCalendarUid()', '\nstd::map<std::string, sptr<ReminderRequest>> ReminderDataShareHelper::GetCacheReminders()'),
                ('void ReminderDataShareHelper::InitNormalInfo(', '\nvoid ReminderDataShareHelper::InitBaseInfo('),
                ('void ReminderDataShareHelper::CheckWantAgent(', '\nReminderDataShareHelper::ReminderDataShareHelper()')):
                start = source.index(begin)
                functions.append(source[start:source.index(end, start)])
            return '\n'.join(functions)
        code = r'''
#include <memory>
#include <string>
#include <vector>
#include <cstdio>
#include "OWNER_HEADER"
#define ANSR_LOGI(...) ((void)0)
#define ANSR_LOGE(...) ((void)0)
namespace OHOS::AppExecFwk {
enum class BundleFlag { GET_BUNDLE_WITH_EXTENSION_INFO };
struct Metadata { std::string name; std::string value; };
struct Module { std::vector<Metadata> metadata; };
struct BundleInfo { std::vector<Module> hapModuleInfos; };
}
namespace OHOS::Notification {
template<class T> using sptr=std::shared_ptr<T>;
class ReminderBundleManagerHelper {
public:
 static ReminderBundleManagerHelper &GetInstance(){static ReminderBundleManagerHelper value;return value;}
 int GetDefaultUidByBundleName(const std::string &bundle,int user){return bundle=="com.ohos.calendardata"&&user==100?123456:-1;}
 bool GetBundleInfo(const std::string &bundle,AppExecFwk::BundleFlag,int uid,AppExecFwk::BundleInfo &info){
   if(bundle!="com.ohos.calendardata"||uid!=123456)return false;
   info.hapModuleInfos={{{{"ohos.calendardata.reminderDbVersion","2"}}}};return true;
 }
};
class ReminderRequest {
public:
 enum class RingChannel { NOTIFICATION };
 struct WantAgentInfo{std::string pkgName;std::string abilityName;std::string uri;};
 int uid=-1,creatorUid=-1,user=-1;std::string bundle,creator;bool shared=false,system=false,tap=false;
 std::shared_ptr<WantAgentInfo> want;
 void SetRingDuration(int){}void SetRingLoop(bool){}void SetRingChannel(RingChannel){}
 void InitUserId(int v){user=v;}void InitUid(int v){uid=v;}void InitCreatorUid(int v){creatorUid=v;}
 void SetShare(bool v){shared=v;}void InitBundleName(const std::string &v){bundle=v;}
 void InitCreatorBundleName(const std::string &v){creator=v;}void SetSystemApp(bool v){system=v;}
 void SetTapDismissed(bool v){tap=v;}std::shared_ptr<WantAgentInfo> GetWantAgentInfo(){return want;}
};
class ReminderDataShareHelper {
public:
 int uid_=-1,dataUid_=-1,userId_=100,rdbVersion_=0;
 void UpdateCalendarUid();void InitNormalInfo(sptr<ReminderRequest>&);void CheckWantAgent(sptr<ReminderRequest>&);
};
static constexpr int8_t CALENDAR_RDB_V1=1,CALENDAR_RDB_V2=2;
ACTUAL_FUNCTIONS
}
int main(){
 using namespace OHOS::Notification;
 ReminderDataShareHelper helper;helper.UpdateCalendarUid();
 sptr<ReminderRequest> reminder=std::make_shared<ReminderRequest>();helper.InitNormalInfo(reminder);
 if(reminder->uid!=123456||reminder->creatorUid!=123456||reminder->user!=100||
    reminder->bundle!="com.ohos.calendardata"||reminder->creator!=reminder->bundle||
    !reminder->shared||!reminder->system||!reminder->tap)return 7;
 if(helper.rdbVersion_!=2)return 10;
 helper.CheckWantAgent(reminder);
 reminder->want=std::make_shared<ReminderRequest::WantAgentInfo>();
 reminder->want->pkgName="com.ohos.calendardata";reminder->want->abilityName="MainAbility";
 const std::string uri="calendar://com.ohos.calendardata?event_id=19&start=1000&end=2000";
 reminder->want->uri=uri;helper.CheckWantAgent(reminder);
 if(reminder->want->uri!=uri||reminder->want->pkgName!=reminder->bundle)return 8;
 reminder->want->pkgName="untrusted.foreign";helper.CheckWantAgent(reminder);
 if(reminder->want->pkgName!="com.ohos.calendardata"||reminder->want->abilityName!="MainAbility"||
    !reminder->want->uri.empty())return 9;
 std::puts("PASS actual owner UID, creator, original URI and foreign fallback");
}
'''.replace('OWNER_HEADER', str(target))
        cpp = case.root / 'consumer.cpp'
        binary = case.root / 'consumer'
        original = target.read_bytes()
        for state, expected_exit in (('old', 7), ('owner-only', 10), ('complete', 0)):
            if state == 'owner-only':
                target.write_bytes(original.replace(b'NAME = "com.ohos.calendar";', b'NAME = "com.ohos.calendardata";'))
                # A real component replay must refuse this incomplete pair.
                self.assertNotEqual(self.apply(case).returncode, 0)
            if state == 'complete':
                target.write_bytes(original)
                result = self.apply(case)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            native = (case.root / MANIFEST['project'] / HELPER).read_text()
            cpp.write_text(code.replace('ACTUAL_FUNCTIONS', actual_functions(native)))
            built = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O1',
                                    str(cpp), '-o', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, expected_exit, result.stdout + result.stderr)
            if state == 'complete': self.assertIn('PASS actual owner UID', result.stdout)


if __name__ == '__main__':
    unittest.main()
