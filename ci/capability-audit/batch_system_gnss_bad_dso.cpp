#include "location_vendor_lib.h"
#include <cstdlib>
#include <fstream>
namespace {
const OHOS::HDI::Location::GnssVendorInterface bad={};
[[maybe_unused]] const OHOS::HDI::Location::GnssVendorInterface* Get(){return &bad;}
__attribute__((destructor)) void Unloaded(){const char* path=std::getenv("GNSS_TEST_UNLOADED");if(path)std::ofstream(path,std::ios::app)<<"unloaded\n";}
}
#if BAD_GNSS_KIND != 1
extern "C" {
OHOS::HDI::Location::GnssVendorDevice GnssVendorInterface={
#if BAD_GNSS_KIND == 2
    0,
#else
    sizeof(OHOS::HDI::Location::GnssVendorDevice),
#endif
    Get};
}
#endif
