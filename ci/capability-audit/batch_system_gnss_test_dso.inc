// Only the host DSO factory uses an explicit host UID/path. Provider functions and input source are shipped code.
#include <cstdlib>
#include <fstream>
#include <unistd.h>
namespace GnssHostFactory {
using P=OHOS::QemuGnss::Provider;
using C=OHOS::HDI::Location::GnssCallbackStruct;
P& Provider(){static P value({std::getenv("GNSS_TEST_SOCKET"),geteuid()});return value;}
int Enable(C* callbacks){return Provider().Enable(callbacks);}
int Disable(){return Provider().Disable();}
int Start(uint32_t value){return Provider().Start(value);}
int Stop(uint32_t value){return Provider().Stop(value);}
int Config(OHOS::HDI::Location::GnssConfigParameter* value){return Provider().Configure(value);}
const OHOS::HDI::Location::GnssVendorInterface table={sizeof(OHOS::HDI::Location::GnssVendorInterface),
    Enable,Disable,Start,Stop,OHOS::QemuGnss::Reference,Config,OHOS::QemuGnss::DeleteAuxiliary,
    OHOS::QemuGnss::Ephemeris,nullptr,nullptr,OHOS::QemuGnss::Module};
const OHOS::HDI::Location::GnssVendorInterface* Get(){return &table;}
__attribute__((destructor)) void Unloaded(){
    const char* path=std::getenv("GNSS_TEST_UNLOADED");if(path)std::ofstream(path,std::ios::app)<<"unloaded\n";
}
}
extern "C" {
__attribute__((visibility("default"))) OHOS::HDI::Location::GnssVendorDevice GnssVendorInterface={
    sizeof(OHOS::HDI::Location::GnssVendorDevice),GnssHostFactory::Get};
}
