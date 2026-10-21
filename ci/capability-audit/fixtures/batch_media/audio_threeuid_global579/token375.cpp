/* Read-only BMS-bound AccessToken observer; UID is not transported by this parcel. */
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
