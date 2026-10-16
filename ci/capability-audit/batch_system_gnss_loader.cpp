#include "location_vendor_lib.h"
#include <dlfcn.h>
#include <cerrno>
int main(int argc,char**argv){
    if(argc!=2)return 1;
    void* handle=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!handle)return 2;
    auto* device=static_cast<OHOS::HDI::Location::GnssVendorDevice*>(dlsym(handle,"GnssVendorInterface"));
    if(!device||device->size!=sizeof(*device)||!device->getGnssInterface)return 3;
    auto* iface=device->getGnssInterface();if(!iface||iface->size!=sizeof(*iface))return 4;
    if(!iface->enableGnss||!iface->disableGnss||!iface->startGnss||!iface->stopGnss||!iface->injectsGnssReferenceInfo||
       !iface->setGnssConfigPara||!iface->removeAuxiliaryData||!iface->injectExtendedEphemeris||!iface->getGnssModuleIface)return 5;
    if(iface->getCachedLocationsSize||iface->flushCachedGnssLocations)return 6;
    if(iface->enableGnss(nullptr)!=-EINVAL||iface->getGnssModuleIface(1)!=nullptr)return 7;
    iface->disableGnss();return dlclose(handle)!=0;
}
