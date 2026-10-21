/* Passive TIME getter only. Root-owned stop file, never vibration mutation. */
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
