"""Round 375 three-UID observer protocol; never creates guest/resource ownership.

This is separate from the frozen round 22 and current 74-phase protocols. BMS
supplies UID, AccessToken supplies the tuple and grants, and TIME is a passive
getter bounded by a root-owned stop file. No row proves audio output onset.
"""
import json
import re
import shlex

from hap_identity_binding import HAP_IDENTITY_FIELDS, bms_application_identity, verify_hap_token_identity
from run_normal_hap_probe import require_normal_identity

PROTOCOL = 'audio-haptic-three-uid/375-v1'
BOOT = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate observer key')
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite observer value')))


def bms_identity(raw, bundle):
    identity = bms_application_identity(raw, bundle)
    require(require_normal_identity(raw, bundle) == identity['uid'], 'ordinary BMS identity required')
    return identity


def actual_token(raw, *, run, boot, bundle, identity, permission, expected):
    value = loads(raw)
    require(set(value) == HAP_IDENTITY_FIELDS | {'protocol', 'kind', 'run_id', 'boot_id',
        'bundle', 'token_id', 'permission', 'before', 'after', 'before_ns', 'after_ns'},
        'exact independent BMS/AccessToken schema required')
    verify_hap_token_identity(value, bundle=bundle, uid=identity['uid'], token_id=identity['token_id'])
    require(value['protocol'] == PROTOCOL and value['kind'] == 'token' and
        value['run_id'] == run and value['boot_id'] == boot and value['permission'] == permission and
        all(type(value[k]) is int and value[k] == expected for k in ('before', 'after')) and
        all(type(value[k]) is int for k in ('before_ns', 'after_ns')) and
        0 < value['before_ns'] <= value['after_ns'], 'actual token grant/boot/monotonic bracket differs')
    return value


def token_script(remote, run, boot, bundle, uid, permission):
    require(re.fullmatch('/data/local/tmp/audio-haptic-[a-f0-9]{32}', remote) and
        remote.endswith(run) and re.fullmatch('[a-f0-9]{32}', run) and BOOT.fullmatch(boot) and
        re.fullmatch('org.harmonycontrib.audiohaptic(?:contender|denied)?', bundle) and
        type(uid) is int and 20010000 <= uid <= 20199999 and
        permission in ('ohos.permission.VIBRATE', 'ohos.permission.KEEP_BACKGROUND_RUNNING'),
        'fixed three-UID observer arguments required')
    return 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + ' '.join((remote+'/token', run, boot, str(uid), bundle, permission))


def observer_script(remote, run, boot, marker):
    require(re.fullmatch('/data/local/tmp/audio-haptic-[a-f0-9]{32}', remote) and remote.endswith(run) and
        re.fullmatch('[a-f0-9]{32}', run) and BOOT.fullmatch(boot) and
        re.fullmatch('__HAPTIC375_EXIT_[a-f0-9]{32}__=', marker), 'exact owned passive observer arguments required')
    script = 'umask 077; set -C; echo $$ > '+remote+'/observer.pid || exit 1; '
    script += 'awk \'{print $22}\' /proc/$$/stat > '+remote+'/observer.start || exit 1; '
    script += 'unset LD_LIBRARY_PATH LD_PRELOAD; exec '+remote+'/passive '+run+' '+boot+' 900000 10 '+remote+'/sampler-stop'
    return 'sh -c '+shlex.quote(script)+'; task_haptic_rc=$?; printf "\\n'+marker+'%s\\n" "$task_haptic_rc"'


def verify_token_binding(item, *, run, boot, role, bundle, identity, permission, expected, observed, command_index):
    require(set(item) == {'role', 'permission', 'bms_before', 'raw', 'bms_after', 'value'} and
        item['role'] == role and item['permission'] == permission, 'exact token binding required')
    before = bms_identity(observed(item['bms_before'], 'bm dump -n '+bundle), bundle)
    raw = observed(item['raw'], token_script('/data/local/tmp/audio-haptic-'+run, run, boot,
        bundle, identity['uid'], permission))
    after = bms_identity(observed(item['bms_after'], 'bm dump -n '+bundle), bundle)
    require(before == identity == after, 'BMS identity changed around AccessToken query')
    require(command_index(item['bms_before']) < command_index(item['raw']) < command_index(item['bms_after']),
        'original BMS commands must bracket the actual token command')
    value = actual_token(raw, run=run, boot=boot, bundle=bundle, identity=identity,
        permission=permission, expected=expected)
    require(value == item['value'], 'token summary differs from original command stdout')
    return value


def parse_time(raw, run, boot, exit_code):
    require(type(exit_code) is int and exit_code == 0 and re.fullmatch('[a-f0-9]{32}', run) and
        BOOT.fullmatch(boot), 'actual observer exit/run/boot required')
    require(type(raw) is str and 0 < len(raw.encode()) <= 16*1024**2 and raw.endswith('\n'),
        'complete bounded TIME stream required')
    rows = [loads(line) for line in raw.splitlines()]
    require(5 <= len(rows) <= 180004, 'bounded complete TIME stream required')
    begin, complete = rows[0], rows[-1]
    common = {'protocol', 'kind', 'run_id', 'boot_id'}
    require(set(begin) == common | {'pid', 'uid', 'duration_ms', 'period_ms', 'device_id', 'vibrator_id',
        'before_ns', 'after_ns', 'result', 'time_delay', 'hd_haptic', 'preset_mapping'} and
        set(complete) == common | {'samples', 'owner_stop'}, 'exact TIME envelopes required')
    for row in rows:
        require(row.get('protocol') == PROTOCOL and row.get('run_id') == run and row.get('boot_id') == boot,
            'mixed TIME protocol/run/boot')
    require(begin['kind'] == 'begin' and type(begin['pid']) is int and begin['pid'] > 1 and
        type(begin['uid']) is int and begin['uid'] == 0 and
        all(type(begin[k]) is int and begin[k] == 0 for k in ('device_id', 'vibrator_id', 'result')) and
        begin['time_delay'] is True and begin['hd_haptic'] is False and begin['preset_mapping'] is False and
        type(begin['duration_ms']) is int and 100 <= begin['duration_ms'] <= 900000 and
        type(begin['period_ms']) is int and 5 <= begin['period_ms'] <= 100 and
        all(type(begin[k]) is int for k in ('before_ns', 'after_ns')) and
        0 < begin['before_ns'] <= begin['after_ns'], 'actual passive virtual TIME capacity differs')
    samples = rows[1:-1]
    previous = begin['after_ns']
    realtime_previous = None
    offsets = []
    for sequence, row in enumerate(samples, 1):
        require(set(row) == common | {'sequence', 'before_ns', 'after_ns', 'realtime_ns', 'result', 'running'} and
            row['kind'] == 'sample' and type(row['sequence']) is int and row['sequence'] == sequence and
            type(row['result']) is int and row['result'] == 0 and type(row['running']) is bool and
            all(type(row[k]) is int for k in ('before_ns', 'after_ns', 'realtime_ns')) and
            0 < previous <= row['before_ns'] <= row['after_ns'] and row['realtime_ns'] > 0,
            'failed/reordered actual TIME getter or clock')
        require(row['after_ns'] - begin['after_ns'] <= begin['duration_ms']*1000000+1000000000,
            'TIME observer exceeded declared duration bound')
        if realtime_previous is not None:
            require(row['realtime_ns'] >= realtime_previous, 'guest realtime moved backward during TIME collection')
        # Both clocks are read between the same before..after bracket. A clock
        # step must not be hidden by relabeling realtime as uptime.
        offsets.append((row['realtime_ns']-row['after_ns'], row['realtime_ns']-row['before_ns']))
        previous, realtime_previous = row['after_ns'], row['realtime_ns']
    require(max(row[0] for row in offsets) <= min(row[1] for row in offsets),
        'guest realtime/monotonic mapping changed; synchronization remains unproven')
    require(complete['kind'] == 'complete' and complete['owner_stop'] is True and
        type(complete['samples']) is int and complete['samples'] == len(samples), 'owner stop or samples missing')
    return samples


def parse_time_transport(raw, run, boot, exit_code, marker):
    from guest_ui import command_exit
    require(type(marker) is str and re.fullmatch('__HAPTIC375_EXIT_[a-f0-9]{32}__=', marker),
        'fresh passive native exit marker required')
    body, native_code = command_exit(raw.replace('\r', ''), marker)
    require(native_code == 0, 'actual passive native helper exited nonzero')
    return parse_time(body, run, boot, exit_code)


TOKEN_SOURCE = r'''/* Read-only BMS-bound AccessToken observer; UID is not transported by this parcel. */
#include "accesstoken_kit.h"
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <time.h>
#include <unistd.h>
using namespace OHOS::Security::AccessToken;
static bool Now(unsigned long long &ns) {
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t) != 0 || t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000 ||
      static_cast<unsigned long long>(t.tv_sec) > (ULLONG_MAX-static_cast<unsigned long long>(t.tv_nsec))/1000000000ULL) return false;
  ns=static_cast<unsigned long long>(t.tv_sec)*1000000000ULL+static_cast<unsigned long long>(t.tv_nsec); return ns > 0;
}
static bool Boot(const std::string &expected) {
  std::ifstream file("/proc/sys/kernel/random/boot_id"); std::string actual;
  return expected.size()==36 && std::getline(file,actual) && actual==expected;
}
int main(int argc, char **argv) {
  if (argc!=6 || getuid()!=0 || geteuid()!=0) return 2;
  const std::string run(argv[1]), boot(argv[2]), uidText(argv[3]), bundle(argv[4]), permission(argv[5]);
  if (run.size()!=32 || run.find_first_not_of("0123456789abcdef")!=std::string::npos || !Boot(boot) ||
      uidText.empty() || uidText.size()>10 || uidText.find_first_not_of("0123456789")!=std::string::npos ||
      (bundle!="org.harmonycontrib.audiohaptic" && bundle!="org.harmonycontrib.audiohapticcontender" &&
       bundle!="org.harmonycontrib.audiohapticdenied") ||
      (permission!="ohos.permission.VIBRATE" && permission!="ohos.permission.KEEP_BACKGROUND_RUNNING")) return 2;
  errno=0; char *end=nullptr; const unsigned long uid=strtoul(argv[3],&end,10);
  if (errno!=0 || *end!='\0' || uid>INT_MAX || uid/200000!=100 || uid%200000<10000) return 2;
  const AccessTokenID token=AccessTokenKit::GetHapTokenID(100,bundle,0); HapTokenInfo info{};
  const int queried=AccessTokenKit::GetHapTokenInfo(token,info);
  if (token==0 || queried!=0 || info.tokenID!=token || info.userID!=100 || info.instIndex!=0 || info.bundleName!=bundle) return 1;
  unsigned long long a=0,b=0; if (!Now(a)) return 1;
  const int first=AccessTokenKit::VerifyAccessToken(token,permission,true);
  const int second=AccessTokenKit::VerifyAccessToken(token,permission,true);
  if (!Now(b) || b<a || !Boot(boot) || first!=second || (second!=PERMISSION_GRANTED && second!=PERMISSION_DENIED)) return 1;
  printf("{\"protocol\":\"audio-haptic-three-uid/375-v1\",\"kind\":\"token\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
         "\"expected_uid\":%lu,\"identity_schema\":\"hap-bms-access-token/v1\",\"bundle\":\"%s\","
         "\"at_reported_uid\":%d,\"at_query_rc\":%d,\"at_token_id\":%u,\"at_user_id\":%d,\"at_inst_index\":%d,\"at_bundle\":\"%s\","
         "\"token_id\":%u,\"permission\":\"%s\",\"before\":%d,\"after\":%d,\"before_ns\":%llu,\"after_ns\":%llu}\n",
         run.c_str(),boot.c_str(),uid,bundle.c_str(),info.uid,queried,info.tokenID,info.userID,info.instIndex,
         info.bundleName.c_str(),token,permission.c_str(),first,second,a,b);
  return fflush(stdout)==0 && !ferror(stdout)?0:1;
}
'''


PASSIVE_SOURCE = r'''/* Passive TIME getter only. Root-owned stop file, never vibration mutation. */
#include "v2_0/ivibrator_interface.h"
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
using namespace OHOS::HDI::Vibrator::V2_0;
static bool Now(clockid_t clock, unsigned long long &ns) {
  timespec t{};
  if (clock_gettime(clock,&t)!=0 || t.tv_sec<0 || t.tv_nsec<0 || t.tv_nsec>=1000000000 ||
      static_cast<unsigned long long>(t.tv_sec)>(ULLONG_MAX-static_cast<unsigned long long>(t.tv_nsec))/1000000000ULL) return false;
  ns=static_cast<unsigned long long>(t.tv_sec)*1000000000ULL+static_cast<unsigned long long>(t.tv_nsec); return ns>0;
}
static bool Boot(const std::string &expected) {
  std::ifstream file("/proc/sys/kernel/random/boot_id"); std::string actual;
  return expected.size()==36 && std::getline(file,actual) && actual==expected;
}
static bool Number(const char *text, unsigned long minimum, unsigned long maximum, unsigned long &value) {
  if (*text=='\0' || strlen(text)>6 || strspn(text,"0123456789")!=strlen(text)) return false;
  errno=0; char *end=nullptr; value=strtoul(text,&end,10);
  return errno==0 && *end=='\0' && value>=minimum && value<=maximum;
}
int main(int argc, char **argv) {
  if (argc!=6 || getuid()!=0 || geteuid()!=0) return 2;
  const std::string run(argv[1]),boot(argv[2]),stop(argv[5]); unsigned long duration=0,period=0;
  if (run.size()!=32 || run.find_first_not_of("0123456789abcdef")!=std::string::npos || !Boot(boot) ||
      !Number(argv[3],100,900000,duration) || !Number(argv[4],5,100,period) ||
      stop!="/data/local/tmp/audio-haptic-"+run+"/sampler-stop") return 2;
  struct stat entry{};
  if (lstat(stop.c_str(),&entry)==0 || errno!=ENOENT) return 2;
  auto driver=IVibratorInterface::Get(); if (driver==nullptr) return 1;
  const DeviceVibratorInfo device{0,0}; HapticCapacity capacity{};
  unsigned long long before=0,after=0,realtime=0;
  if (!Now(CLOCK_MONOTONIC,before)) return 1;
  const int result=driver->GetHapticCapacity(device,capacity);
  if (!Now(CLOCK_MONOTONIC,after) || after<before) return 1;
  printf("{\"protocol\":\"audio-haptic-three-uid/375-v1\",\"kind\":\"begin\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
    "\"pid\":%d,\"uid\":%u,\"duration_ms\":%lu,\"period_ms\":%lu,\"device_id\":0,\"vibrator_id\":0,"
    "\"before_ns\":%llu,\"after_ns\":%llu,\"result\":%d,\"time_delay\":%s,\"hd_haptic\":%s,\"preset_mapping\":%s}\n",
    run.c_str(),boot.c_str(),getpid(),getuid(),duration,period,before,after,result,
    result==0 && capacity.isSupportTimeDelay?"true":"false",result==0 && capacity.isSupportHdHaptic?"true":"false",
    result==0 && capacity.isSupportPresetMapping?"true":"false");
  if (fflush(stdout)!=0 || result!=0 || !capacity.isSupportTimeDelay) return 1;
  const auto began=after; unsigned long count=0; bool ownerStop=false;
  while (true) {
    if (!Now(CLOCK_MONOTONIC,before) || before<began || before-began>=duration*1000000ULL) break;
    errno=0;
    if (lstat(stop.c_str(),&entry)==0) {
      if (!S_ISREG(entry.st_mode) || entry.st_uid!=0 || entry.st_nlink!=1 || (entry.st_mode&0777)!=0600) return 1;
      ownerStop=true; break;
    }
    if (errno!=ENOENT || !Now(CLOCK_REALTIME,realtime)) return 1;
    bool running=false; const int status=driver->IsVibratorRunning(device,running);
    if (!Now(CLOCK_MONOTONIC,after) || after<before) return 1;
    printf("{\"protocol\":\"audio-haptic-three-uid/375-v1\",\"kind\":\"sample\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
      "\"sequence\":%lu,\"before_ns\":%llu,\"after_ns\":%llu,\"realtime_ns\":%llu,\"result\":%d,\"running\":%s}\n",
      run.c_str(),boot.c_str(),++count,before,after,realtime,status,status==0?(running?"true":"false"):"null");
    if (fflush(stdout)!=0 || status!=0) return 1;
    timespec wait{static_cast<time_t>(period/1000),static_cast<long>((period%1000)*1000000)};
    while (nanosleep(&wait,&wait)!=0) if (errno!=EINTR) return 1;
  }
  if (!Boot(boot)) return 1;
  printf("{\"protocol\":\"audio-haptic-three-uid/375-v1\",\"kind\":\"complete\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"samples\":%lu,\"owner_stop\":%s}\n",
    run.c_str(),boot.c_str(),count,ownerStop?"true":"false");
  return ownerStop && count>0 && fflush(stdout)==0 && !ferror(stdout)?0:1;
}
'''
