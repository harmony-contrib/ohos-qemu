"""Exact codec with simulated Parcel primitives; NOT real IPC/DB/guest proof."""
from pathlib import Path
import sqlite3
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_store'
PATCH = COMPONENT / '0001-persist-complete-bounded-network-config-separately-from-credentials.patch'
HEADER = 'foundation/communication/netmanager_ext/interfaces/innerkits/netvpnclient/include/vpn_network_config.h'

MOCK = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
namespace OHOS { namespace NetManagerStandard {
template<typename T> using sptr=std::shared_ptr<T>;
struct Parcel {
    std::vector<uint8_t> bytes;
    size_t position=0, maximum=1024*1024;
    static bool capacityWorks;
    bool SetMaxCapacity(size_t maximum) { this->maximum=maximum; return capacityWorks; }
    bool WriteBuffer(const void* data,size_t size) {
        if(size>maximum-bytes.size()) return false;
        auto begin=static_cast<const uint8_t*>(data); bytes.insert(bytes.end(),begin,begin+size); return true; }
    bool WriteUint32(uint32_t value) {
        uint8_t data[4]; for(unsigned i=0;i<4;++i) data[i]=(value>>(i*8))&255;
        return WriteBuffer(data,4); }
    bool ReadUint32(uint32_t& value) {
        if(bytes.size()-position<4) return false;
        value=0; for(unsigned i=0;i<4;++i) value|=uint32_t(bytes[position++])<<(i*8); return true; }
    bool WriteInt32(int32_t value) { return WriteUint32(static_cast<uint32_t>(value)); }
    bool ReadInt32(int32_t& value) { uint32_t word; if(!ReadUint32(word)) return false; value=word; return true; }
    bool WriteBool(bool value) { return WriteUint32(value); }
    bool ReadBool(bool& value) { uint32_t word; if(!ReadUint32(word)||word>1) return false; value=word; return true; }
    bool WriteString(const std::string& value) {
        return WriteUint32(value.size())&&WriteBuffer(value.data(),value.size()); }
    bool ReadString(std::string& value) {
        uint32_t size; if(!ReadUint32(size)||size>bytes.size()-position) return false;
        value.assign(reinterpret_cast<const char*>(bytes.data()+position),size); position+=size; return true; }
    size_t GetDataSize() const { return bytes.size(); }
    uintptr_t GetData() const { return reinterpret_cast<uintptr_t>(bytes.data()); }
    size_t GetReadPosition() const { return position; }
};
bool Parcel::capacityWorks=true;
struct INetAddr {
    uint8_t family_=0, prefixlen_=0;
    std::string address_;
    uint8_t port_=0;
    bool Marshalling(Parcel& parcel) const {
        return parcel.WriteString(address_)&&parcel.WriteUint32(family_)&&
            parcel.WriteUint32(prefixlen_)&&parcel.WriteUint32(port_); }
    static sptr<INetAddr> Unmarshalling(Parcel& parcel) {
        auto value=std::make_shared<INetAddr>(); uint32_t family,prefix,port;
        if(!parcel.ReadString(value->address_)||!parcel.ReadUint32(family)||family>255||
            !parcel.ReadUint32(prefix)||prefix>255||!parcel.ReadUint32(port)||port>255) return nullptr;
        value->family_=family; value->prefixlen_=prefix; value->port_=port; return value; }
};
struct VpnConfig {
    std::string vpnId_;
    std::vector<INetAddr> addresses_;
    std::vector<std::string> routes_,dnsAddresses_,searchDomains_,acceptedApplications_,refusedApplications_;
    int32_t mtu_=0;
    bool isAcceptIPv4_=true,isAcceptIPv6_=false,isLegacy_=false,isMetered_=false,isBlocking_=false;
    virtual ~VpnConfig()=default;
    bool MarshallingVectorString(Parcel& parcel,const std::vector<std::string>& values,uint32_t maximum) const {
        if(values.size()>maximum||!parcel.WriteUint32(values.size())) return false;
        for(const auto& value:values) if(!parcel.WriteString(value)) return false; return true; }
    static bool UnmarshallingVectorString(Parcel& parcel,std::vector<std::string>& values,uint32_t maximum) {
        uint32_t size; if(!parcel.ReadUint32(size)||size>maximum) return false;
        for(uint32_t i=0;i<size;++i) { std::string value;
            if(!parcel.ReadString(value)) return false; values.push_back(value); } return true; }
    virtual bool Marshalling(Parcel& parcel) const {
        if(!parcel.WriteString(vpnId_)||!parcel.WriteUint32(addresses_.size())) return false;
        for(const auto& address:addresses_) if(!address.Marshalling(parcel)) return false;
        return MarshallingVectorString(parcel,routes_,10000)&&parcel.WriteInt32(mtu_)&&
            parcel.WriteBool(isAcceptIPv4_)&&parcel.WriteBool(isAcceptIPv6_)&&parcel.WriteBool(isLegacy_)&&
            parcel.WriteBool(isMetered_)&&parcel.WriteBool(isBlocking_)&&
            MarshallingVectorString(parcel,dnsAddresses_,64)&&MarshallingVectorString(parcel,searchDomains_,64)&&
            MarshallingVectorString(parcel,acceptedApplications_,256)&&
            MarshallingVectorString(parcel,refusedApplications_,256); }
    static bool UnmarshallingVpnConfig(Parcel& parcel,VpnConfig* config) {
        uint32_t size; if(!parcel.ReadString(config->vpnId_)||!parcel.ReadUint32(size)||size>2000) return false;
        for(uint32_t i=0;i<size;++i) { auto address=INetAddr::Unmarshalling(parcel);
            if(!address) return false; config->addresses_.push_back(*address); }
        return UnmarshallingVectorString(parcel,config->routes_,10000)&&parcel.ReadInt32(config->mtu_)&&
            parcel.ReadBool(config->isAcceptIPv4_)&&parcel.ReadBool(config->isAcceptIPv6_)&&
            parcel.ReadBool(config->isLegacy_)&&parcel.ReadBool(config->isMetered_)&&
            parcel.ReadBool(config->isBlocking_)&&UnmarshallingVectorString(parcel,config->dnsAddresses_,64)&&
            UnmarshallingVectorString(parcel,config->searchDomains_,64)&&
            UnmarshallingVectorString(parcel,config->acceptedApplications_,256)&&
            UnmarshallingVectorString(parcel,config->refusedApplications_,256); }
};
struct SysVpnConfig : VpnConfig {
    std::vector<std::string> remoteAddresses_;
    std::vector<INetAddr> localAddresses_;
    std::string password_="decrypted-marker",userName_="decrypted-user",ipsecPreSharedKey_="hks-psk";
    bool Marshalling(Parcel&) const override { assert(false&&"must not store derived credentials"); return false; }
};
} }
'''


def codec():
    value = '\n'.join(patch_sections(PATCH)[HEADER][0][2])
    return MOCK + value.replace('#include "sysvpn_config.h"', '') + r'''
using namespace OHOS::NetManagerStandard;
void EqualLinks(const std::vector<INetAddr>& a,const std::vector<INetAddr>& b) {
    assert(a.size()==b.size()); for(size_t i=0;i<a.size();++i) {
        assert(a[i].address_==b[i].address_&&a[i].prefixlen_==b[i].prefixlen_&&
            a[i].family_==b[i].family_&&a[i].port_==b[i].port_); }
}
void EqualNetwork(const SysVpnConfig& a,const SysVpnConfig& b) {
    assert(a.vpnId_==b.vpnId_&&a.mtu_==b.mtu_&&a.routes_==b.routes_&&
        a.isAcceptIPv4_==b.isAcceptIPv4_&&a.isAcceptIPv6_==b.isAcceptIPv6_&&a.isLegacy_==b.isLegacy_&&
        a.isMetered_==b.isMetered_&&a.isBlocking_==b.isBlocking_&&a.dnsAddresses_==b.dnsAddresses_&&
        a.searchDomains_==b.searchDomains_&&a.acceptedApplications_==b.acceptedApplications_&&
        a.refusedApplications_==b.refusedApplications_&&a.remoteAddresses_==b.remoteAddresses_);
    EqualLinks(a.addresses_,b.addresses_); EqualLinks(a.localAddresses_,b.localAddresses_);
}
SysVpnConfig Input() {
    SysVpnConfig value; value.vpnId_="audit-uuid"; value.mtu_=1400;
    value.addresses_={{1,24,"198.18.0.2",0},{2,64,"2001:db8::2",255}};
    value.localAddresses_={{1,28,"198.19.0.2",13},{2,96,"2001:db8:1::2",14}};
    value.remoteAddresses_={"198.18.1.1","2001:db8:2::1"};
    value.dnsAddresses_={"198.18.1.53","2001:db8::53"}; value.searchDomains_={"a.example","b.example"};
    value.routes_={"route-0","route-1"}; value.acceptedApplications_={"allowed.0","allowed.1"};
    value.refusedApplications_={"blocked.0","blocked.1"};
    value.isAcceptIPv4_=false; value.isAcceptIPv6_=true; value.isLegacy_=true;
    value.isMetered_=true; value.isBlocking_=true; return value;
}
'''


class VpnStoreTests(unittest.TestCase):
    def test_list_callback_uses_complete_typed_serializer_for_every_item(self):
        name = 'foundation/communication/netmanager_ext/frameworks/js/napi/vpn/src/vpn_exec.cpp'
        body = next(hunk[2] for hunk in patch_sections(PATCH)[name]
                    if any('sptr<SysVpnConfig> nativeConfig = info;' in line for line in hunk[2]))
        start = body.index('    for (const auto &info : context->vpnList_) {')
        end = body.index('    }', start) + 1
        source = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <vector>
struct SysVpnConfig { unsigned nativePrefix; };
template<typename T> using sptr=std::shared_ptr<T>;
using napi_value=SysVpnConfig*;
struct Context { std::vector<sptr<SysVpnConfig>> vpnList_; void* GetEnv() { return nullptr; } };
unsigned calls=0;
struct VpnConfigUtils {
    static napi_value CreateNapiVpnConfig(void*,sptr<SysVpnConfig>& value) { ++calls; return value.get(); }
};
struct NapiUtils {
    static void SetArrayElement(void*,std::vector<napi_value>& array,size_t index,napi_value value) { array.at(index)=value; }
};
void Callback(Context* context,std::vector<napi_value>& array) {
    int32_t index=0;
'''
        source += '\n'.join(body[start:end]) + '\n}\n' + r'''
int main() {
    Context context;
    context.vpnList_={std::make_shared<SysVpnConfig>(SysVpnConfig{24}),std::make_shared<SysVpnConfig>(SysVpnConfig{64})};
    std::vector<napi_value> array(2); Callback(&context,array);
    assert(calls==2&&array[0]==context.vpnList_[0].get()&&array[1]==context.vpnList_[1].get());
    assert(array[0]->nativePrefix==24&&array[1]->nativePrefix==64);
    context.vpnList_.clear(); array.clear(); Callback(&context,array); assert(calls==2);
}
'''
        compile_run(source, language='c++')

    def test_actual_upgrade_branch_sql_preserves_legacy_rows_and_stops_on_error(self):
        name = 'foundation/communication/netmanager_ext/services/vpnmanager/src/vpn_database_helper.cpp'
        body = next(hunk[2] for hunk in patch_sections(PATCH)[name]
                    if any('int32_t VpnDataBaseCallBack::OnUpgrade(' in line for line in hunk[2]))
        source = r'''
#include <cassert>
#include <iostream>
#include <string>
#include <vector>
namespace OHOS { namespace NativeRdb {
constexpr int E_OK=0;
struct RdbStore {
    int failAt=-1;
    std::vector<std::string> sql;
    int ExecuteSql(const std::string& value) {
        sql.push_back(value); return static_cast<int>(sql.size())==failAt ? -73 : 0; }
}; } }
using namespace OHOS;
constexpr int NETMANAGER_EXT_SUCCESS=0,VPN_DATA_DB_VER_2=2,VPN_DATA_DB_VER_3=3;
const std::string VPN_CONFIG_TABLE="T_vpn_config",VPN_REMOTE_ADDR="remoteAddresses",VPN_NETWORK_CONFIG="networkConfig";
#define NETMGR_EXT_LOG_I(...) ((void)0)
struct VpnDataBaseCallBack { int32_t OnUpgrade(NativeRdb::RdbStore&,int32_t,int32_t); };
'''
        source += '\n'.join(body) + '\n}\n' + r'''
int main() {
    VpnDataBaseCallBack callback;
    for(int oldVersion : {1,2,3}) {
        NativeRdb::RdbStore store;
        assert(callback.OnUpgrade(store,oldVersion,3)==0);
        assert(store.sql.size()==static_cast<size_t>(3-oldVersion));
        for(const auto& sql:store.sql) std::cout<<oldVersion<<"|"<<sql<<"\n";
    }
    NativeRdb::RdbStore failFirst; failFirst.failAt=1;
    assert(callback.OnUpgrade(failFirst,1,3)==-73&&failFirst.sql.size()==1);
    NativeRdb::RdbStore failSecond; failSecond.failAt=2;
    assert(callback.OnUpgrade(failSecond,1,3)==-73&&failSecond.sql.size()==2);
}
'''
        output = compile_run(source, language='c++').stdout
        queries = {version: [] for version in (1, 2, 3)}
        for line in output.splitlines():
            version, sql = line.split('|', 1)
            queries[int(version)].append(sql)
        for version in (1, 2, 3):
            with sqlite3.connect(':memory:') as database:
                database.execute('CREATE TABLE T_vpn_config (vpnId TEXT PRIMARY KEY, preserved TEXT NOT NULL)')
                if version >= 2:
                    database.execute("ALTER TABLE T_vpn_config ADD COLUMN remoteAddresses TEXT NOT NULL DEFAULT ''")
                if version >= 3:
                    database.execute("ALTER TABLE T_vpn_config ADD COLUMN networkConfig TEXT NOT NULL DEFAULT ''")
                database.execute("INSERT INTO T_vpn_config (vpnId,preserved) VALUES ('own-uuid','legacy-data')")
                for sql in queries[version]:
                    database.execute(sql)
                self.assertEqual(database.execute('SELECT * FROM T_vpn_config').fetchall(),
                                 [('own-uuid', 'legacy-data', '', '')])
                database.execute("UPDATE T_vpn_config SET networkConfig='new-full-snapshot' WHERE vpnId='own-uuid'")
                self.assertEqual(database.execute('SELECT preserved,networkConfig FROM T_vpn_config').fetchall(),
                                 [('legacy-data', 'new-full-snapshot')])

    def test_empty_multiple_and_boundary_arrays_preserve_all_fields_not_credentials(self):
        compile_run(codec() + r'''
int main() {
    for(unsigned round=0;round<3;++round) {
        auto input=round==0 ? SysVpnConfig() : Input(); input.vpnId_="audit-uuid";
        if(round==2) {
            input.addresses_.resize(2000,input.addresses_[0]);
            input.localAddresses_.resize(2000,input.localAddresses_[1]);
            input.dnsAddresses_.resize(64,"dns.example"); input.searchDomains_.resize(64,"domain.example");
            input.acceptedApplications_.resize(256,"allowed.app"); input.refusedApplications_.resize(256,"blocked.app");
        }
        std::string encoded; assert(VpnNetworkStorage::Encode(input,encoded));
        SysVpnConfig restored; restored.vpnId_=input.vpnId_; restored.password_="existing-decrypted-password";
        assert(VpnNetworkStorage::Restore(encoded,restored)); EqualNetwork(input,restored);
        assert(restored.password_=="existing-decrypted-password"&&restored.userName_=="decrypted-user"&&
            restored.ipsecPreSharedKey_=="hks-psk");
        std::string raw;
        for(size_t i=std::string(VpnNetworkStorage::PREFIX).size();i<encoded.size();i+=2)
            raw.push_back((VpnNetworkStorage::HexDigit(encoded[i])<<4)|VpnNetworkStorage::HexDigit(encoded[i+1]));
        for(const auto& secret:{input.password_,input.userName_,input.ipsecPreSharedKey_}) assert(raw.find(secret)==std::string::npos);
    }
}
''', language='c++')

    def test_malformed_wrong_uuid_truncation_trailing_and_huge_are_atomic_failures(self):
        compile_run(codec() + r'''
int main() {
    auto input=Input(); std::string encoded; assert(VpnNetworkStorage::Encode(input,encoded));
    std::vector<std::string> bad={"vpn-network:2:"+encoded,"invalid",std::string(VpnNetworkStorage::PREFIX),
        encoded+"00",encoded.substr(0,encoded.size()-1),encoded.substr(0,encoded.size()-8),
        std::string(VpnNetworkStorage::PREFIX)+std::string(VpnNetworkStorage::MAX_BYTES*2+2,'0')};
    auto invalidHex=encoded; invalidHex.back()='g'; bad.push_back(invalidHex);
    auto count=encoded; count.replace(count.size()-8,8,"ffffffff"); bad.push_back(count);
    for(const auto& value:bad) { auto destination=Input(); destination.mtu_=999;
        assert(!VpnNetworkStorage::Restore(value,destination)); assert(destination.mtu_==999);
        destination.mtu_=input.mtu_; EqualNetwork(input,destination); }
    auto destination=Input(); destination.vpnId_="another-uuid"; destination.mtu_=999;
    assert(!VpnNetworkStorage::Restore(encoded,destination)); assert(destination.mtu_==999);
    assert(VpnNetworkStorage::Restore("",destination)); assert(destination.mtu_==999);
}
''', language='c++')

    def test_encode_caps_and_write_failures_never_produce_an_accepted_snapshot(self):
        compile_run(codec() + r'''
int main() {
    for(unsigned round=0;round<7;++round) {
        auto input=Input(); std::string encoded="old";
        if(round==0) input.addresses_.resize(2001);
        if(round==1) input.localAddresses_.resize(2001);
        if(round==2) input.routes_.resize(10001);
        if(round==3) input.remoteAddresses_.resize(3);
        if(round==4) input.dnsAddresses_.resize(65);
        if(round==5) input.searchDomains_.resize(65);
        if(round==6) input.vpnId_=std::string(VpnNetworkStorage::MAX_BYTES,'a');
        assert(!VpnNetworkStorage::Encode(input,encoded)); assert(encoded.empty());
    }
    auto input=Input(); std::string encoded="old"; Parcel::capacityWorks=false;
    assert(!VpnNetworkStorage::Encode(input,encoded)); assert(encoded.empty());
}
''', language='c++')

    def test_all_three_variant_paths_and_database_binding_are_in_the_exact_recipe(self):
        sections = patch_sections(PATCH)
        bean = '\n'.join('\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/netmanager_ext/frameworks/native/netvpnclient/src/vpn_data_bean.cpp'])
        self.assertEqual(bean.count('VpnNetworkStorage::Restore('), 3)
        self.assertIn('VpnNetworkStorage::Encode(*sysVpnConfig, vpnBean->networkConfig_)', bean)
        database = '\n'.join('\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/netmanager_ext/services/vpnmanager/src/vpn_database_helper.cpp'])
        self.assertIn('values.PutString(VPN_NETWORK_CONFIG, info->networkConfig_)', database)
        self.assertIn('GetString(INDEX_VPN_NETWORK_CONFIG, vpnBean->networkConfig_)', database)
        self.assertIn('unreadable-network-snapshot', database)


if __name__ == '__main__':
    unittest.main()
