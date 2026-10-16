"""Run actual service/GAP bodies and one-use storage with named platform doubles."""
from pathlib import Path
import base64
import json
import os
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT, body, compile_run

PROJECT='foundation/communication/bluetooth_service'
COMPONENT=ROOT/'patches/common'/PROJECT/'oob_pairing_backend'
FIXTURE=Path(__file__).with_name('fixtures')/'batch_network/bluetooth-service-prepared.json'


def prepared(root):
    for name,encoded in json.loads(FIXTURE.read_text()).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
    return root/PROJECT/'services/bluetooth'


def store(source):
    text=(source/'service/include/interface_adapter.h').read_text()
    return text[text.index('struct PairingOobData {'):text.index('class IAdapter {')]


PREAMBLE=r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
std::chrono::steady_clock::time_point testNow {};
'''


class BluetoothServiceTests(unittest.TestCase):
    def test_exact_service_gap_stack_and_unknown_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root)
            subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            target=source/'stack/src/gap/gap_br_sec.c';target.write_bytes(target.read_bytes()+b'// unknown edit\n')
            unchanged=target.read_bytes();denied=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0);self.assertEqual(target.read_bytes(),unchanged)

    def test_actual_peer_type_single_use_expiry_cancel_and_off(self):
        cases=r'''
int main(){
 PendingOobPair session;PairingOobData data,out;data.peer={1,2,3,4,5,6};data.addressType=1;data.curve=2;
 data.confirmation.fill(25);data.randomizer.fill(52);data.hasRandomizer=true;
 assert(!session.Arm(data));session.SetEnabled(true);assert(session.Arm(data));assert(!session.Arm(data));
 auto other=data.peer;other[0]=99;assert(!session.Take(other.data(),1,out));assert(!session.Take(data.peer.data(),0,out));
 assert(session.State(data.peer.data(),1)==1 && session.Curve(data.peer.data(),1)==2);
 assert(session.State(data.peer.data(),0)==2);
 std::atomic<int> taken{0};std::vector<std::thread> threads;
 for(int i=0;i<8;++i)threads.emplace_back([&]{PairingOobData copy;if(session.Take(data.peer.data(),1,copy)){assert(copy.confirmation[0]==25 && copy.randomizer[0]==52);++taken;}});
 for(auto &thread:threads){
  thread.join();
 }
 assert(taken==1 && session.State(data.peer.data(),1)==2);
 assert(!session.Take(data.peer.data(),1,out));session.Complete(other.data());assert(!session.Arm(data));
 session.Complete(data.peer.data());assert(session.Arm(data));session.Invalidate(data.peer.data());
 assert(!session.Take(data.peer.data(),1,out) && !session.Arm(data));session.Complete(data.peer.data());
 assert(session.Arm(data));testNow+=std::chrono::milliseconds(PendingOobPair::TIMEOUT_MS-1);session.Expire();
 assert(session.State(data.peer.data(),1)==1);testNow+=std::chrono::milliseconds(1);session.Expire();
 assert(session.State(data.peer.data(),1)==2 && !session.Take(data.peer.data(),1,out));
 session.SetEnabled(false);session.SetEnabled(true);assert(session.Arm(data));session.SetEnabled(false);
 assert(!session.Take(data.peer.data(),1,out) && !session.Arm(data));out=data;out.Clear();
 assert(out.curve==0 && !out.hasRandomizer && std::all_of(out.confirmation.begin(),out.confirmation.end(),[](uint8_t v){return v==0;}) && std::all_of(out.randomizer.begin(),out.randomizer.end(),[](uint8_t v){return v==0;}));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root)
            actual=store(source).replace('std::chrono::steady_clock::now()','testNow')
            compile_run(PREAMBLE+actual+cases,root,extra=('-pthread',))

    def test_actual_extended_gap_task_and_hci_parameters_and_errors(self):
        declarations=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define BT_SUCCESS 0
#define BT_NO_MEMORY (-1)
#define GAP_ERR_NOT_ENABLE (-2)
#define GAP_ERR_INVAL_PARAM (-3)
#define BT_PUBLIC_DEVICE_ADDRESS 0
#define GAP_ACCEPT 1
#define GAP_NOT_ACCEPT 0
#define BT_ADDRESS_SIZE 6
#define GAP_OOB_DATA_CONFIRM_SIZE 16
#define GAP_OOB_DATA_RANDOM_SIZE 16
typedef struct {uint8_t addr[6];uint8_t type;} BtAddr;
typedef struct {uint8_t C[16];uint8_t R[16];} GapOOBData;
typedef struct {struct {uint8_t raw[6];} bdAddr;uint8_t c192[16],r192[16],c256[16],r256[16];} HciRemoteOobExtendedDataRequestReplyParam;
static bool enabled=true,failAlloc=false;static int blockError=0,hciError=0,negativeError=0,calls=0,negatives=0;
static HciRemoteOobExtendedDataRequestReplyParam received;
static int memset_s(void *p,size_t max,int value,size_t n){assert(n<=max);memset(p,value,n);return 0;}
static int memcpy_s(void *p,size_t max,const void *from,size_t n){assert(n<=max);memcpy(p,from,n);return 0;}
static bool GapIsBredrEnable(void){return enabled;}
static int HCI_RemoteOOBExtendedDataRequestReply(const HciRemoteOobExtendedDataRequestReplyParam *command){++calls;received=*command;return hciError;}
static int GapRemoteOOBDataRequestNegativeReply(const BtAddr *addr){assert(addr);++negatives;return negativeError;}
static void *allocate(size_t size){return failAlloc?NULL:malloc(size);}
static const struct {void *(*alloc)(size_t);void (*free)(void*);} MEM_MALLOC={allocate,free};
static int GapRunTaskBlockProcess(void (*task)(void*),void *ctx){if(blockError)return blockError;task(ctx);return 0;}
'''
        cases=r'''
int main(void){
 BtAddr addr={{1,2,3,4,5,6},0};GapOOBData a,b;memset(&a,0x19,sizeof(a));memset(&b,0x25,sizeof(b));
 assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==0 && calls==1 && memcmp(received.bdAddr.raw,addr.addr,6)==0);
 for(int i=0;i<16;++i)assert(received.c192[i]==0 && received.r192[i]==0 && received.c256[i]==0x25 && received.r256[i]==0x25);
 assert(GAPIF_RemoteOobExtendedRsp(&addr,1,&a,&b)==0 && calls==2 && received.c192[0]==0x19 && received.c256[0]==0x25);
 hciError=13;assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==13 && calls==3);hciError=0;
 negativeError=19;assert(GAPIF_RemoteOobExtendedRsp(&addr,0,NULL,NULL)==19 && negatives==1);
 assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,NULL)==GAP_ERR_INVAL_PARAM);
 assert(GAPIF_RemoteOobExtendedRsp(NULL,1,NULL,&b)==GAP_ERR_INVAL_PARAM);
 assert(GAPIF_RemoteOobExtendedRsp(&addr,9,NULL,&b)==GAP_ERR_INVAL_PARAM && calls==3);
 enabled=false;assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==GAP_ERR_NOT_ENABLE);enabled=true;
 addr.type=1;assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==GAP_ERR_INVAL_PARAM);addr.type=0;
 blockError=37;assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==37 && calls==3);blockError=0;
 failAlloc=true;assert(GAPIF_RemoteOobExtendedRsp(&addr,1,NULL,&b)==BT_NO_MEMORY && calls==3);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root)
            wrapper=(source/'stack/src/gap/gap_if.c').read_text();gap=(source/'stack/src/gap/gap_br_sec.c').read_text()
            end=wrapper.index('} GapRemoteExtandedOobRspInfo;')+len('} GapRemoteExtandedOobRspInfo;')
            start=wrapper.rfind('typedef struct {',0,end)
            actual=body(gap,'int GAP_RemoteOobExtendedRsp(')+'\n'+wrapper[start:end]+'\n'+body(wrapper,'static void GapRemoteOobExtendedRspTask(')+'\n'+body(wrapper,'int GAPIF_RemoteOobExtendedRsp(')
            c=root/'probe.c';binary=root/'probe';c.write_text(declarations+actual+cases)
            built=subprocess.run([os.environ.get('CC','clang'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20);self.assertEqual(ran.returncode,0,ran.stderr)

    def test_actual_service_permissions_target_shape_off_and_failure_propagation(self):
        declarations=r'''
#include <cctype>
#include <cstdio>
constexpr int NO_ERROR=0,BT_ERR_INVALID_PARAM=401,BT_ERR_INVALID_STATE=2900003,BT_ERR_API_NOT_SUPPORT=801,BT_ERR_INTERNAL_ERROR=2900099;
constexpr int BT_TRANSPORT_BREDR=0,BT_TRANSPORT_BLE=1;
namespace OHOS { namespace bluetooth {enum {P192=1,P256=2,DEVICE_ROLE_BOTH_PREFER_CENTRAL=3};}}
#define HILOGI(...) do {}while(0)
#define HILOGE(...) do {}while(0)
#define CHECK_PERM(isSystemApi,api9Perm,api10Perm) PermissionItem{isSystemApi}
struct RawAddress {std::string value;explicit RawAddress(std::string v):value(v){}const std::string& GetAddress()const{return value;}static RawAddress ConvertToString(const uint8_t *a){char b[18];snprintf(b,sizeof(b),"%02X:%02X:%02X:%02X:%02X:%02X",a[5],a[4],a[3],a[2],a[1],a[0]);return RawAddress(b);}};
struct BluetoothRawAddress {std::string value;std::string GetAddress()const{return value;}};
struct BluetoothOobData {
 bool addressPresent=true,confirmationPresent=true,randomPresent=true,namePresent=false;uint8_t curve=2,role=0;
 std::vector<uint8_t> raw{0x11,0x22,0x33,0x44,0x55,0x66,0},confirmation=std::vector<uint8_t>(16,25),random=std::vector<uint8_t>(16,52);std::string name;
 bool HasOobData()const{return addressPresent && confirmationPresent;}bool HasAddressWithType()const{return addressPresent;}bool HasConfirmHash()const{return confirmationPresent;}bool HasRandomHash()const{return randomPresent;}bool HasDeviceName()const{return namePresent;}
 auto GetAddressWithType()const{return raw;}auto GetConfirmationHash()const{return confirmation;}auto GetRandomizerHash()const{return random;}auto GetDeviceName()const{return name;}auto GetDeviceRole()const{return role;}auto GetOobDataType()const{return curve;}
};
int permission=0,permissionCalls=0,backendCalls=0,ordinaryCalls=0;bool btOn=true,bleOn=true,backend=true,systemCaller=true,accessPermission=true;PairingOobData received;std::string target;
struct PermissionItem {bool systemRequired;};
struct PermissionManager {static int VerifyMultiPermissions(PermissionItem item){++permissionCalls;if(item.systemRequired && !systemCaller)return 202;if(!accessPermission)return 201;return permission;}};
struct Adapter {bool StartPair(const RawAddress&){++ordinaryCalls;return backend;}bool StartPairOutOfBand(const RawAddress& peer,const PairingOobData& data){++backendCalls;target=peer.GetAddress();received=data;return backend;}};
struct IAdapterManager {static IAdapterManager* GetInstance(){static IAdapterManager m;return &m;}Adapter* GetClassicAdapterInterface(){return &a;}Adapter* GetBleAdapterInterface(){return &a;}Adapter a;};
struct IBluetoothOobObserver{};template<class T>using sptr=std::shared_ptr<T>;
struct BluetoothHostServer {static bool IsBtEnabled(){return btOn;}static bool IsBleEnabled(){return bleOn;}int GetTransportByDeviceType(int value,const std::string&){return value;}int StartPair(int,const BluetoothRawAddress&,const BluetoothOobData&);int GenerateLocalOobData(int,const sptr<IBluetoothOobObserver>&);};
'''
        cases=r'''
int main(){
 BluetoothHostServer service;BluetoothRawAddress peer{"11:22:33:44:55:66"};BluetoothOobData data;
 assert(service.StartPair(0,peer,data)==0 && backendCalls==1 && target==peer.value && received.curve==2 && received.peer[0]==0x66 && received.confirmation[0]==25 && received.randomizer[0]==52);
 data.curve=1;assert(service.StartPair(0,peer,data)==0 && received.curve==1);
 assert(service.StartPair(1,peer,data)==801);data.curve=2;assert(service.StartPair(1,peer,data)==0);
 const int accepted=backendCalls;
 systemCaller=false;assert(service.StartPair(0,peer,data)==202 && backendCalls==accepted);systemCaller=true;
 accessPermission=false;assert(service.StartPair(0,peer,data)==201 && backendCalls==accepted);accessPermission=true;
 for(int error:{201,202}){permission=error;assert(service.StartPair(0,peer,data)==error && backendCalls==accepted);}permission=0;
 auto mismatch=peer;mismatch.value="11:22:33:44:55:67";assert(service.StartPair(0,mismatch,data)==401);
 data.raw.pop_back();assert(service.StartPair(0,peer,data)==401);data.raw.push_back(0);
 data.confirmation.resize(15);assert(service.StartPair(0,peer,data)==401);data.confirmation.resize(16);
 data.random.resize(17);assert(service.StartPair(0,peer,data)==401);data.random.resize(16);
 data.raw[6]=1;assert(service.StartPair(0,peer,data)==401);data.raw[6]=0;
 data.curve=3;assert(service.StartPair(0,peer,data)==401);data.curve=2;
 data.role=4;assert(service.StartPair(0,peer,data)==401);data.role=0;
 data.addressPresent=false;assert(service.StartPair(0,peer,data)==401);data.addressPresent=true;
 assert(service.StartPair(2,peer,data)==401);btOn=false;assert(service.StartPair(0,peer,data)==2900003);btOn=true;
 bleOn=false;assert(service.StartPair(1,peer,data)==2900003);bleOn=true;
 data.randomPresent=false;assert(service.StartPair(0,peer,data)==801);data.randomPresent=true;
 backend=false;assert(service.StartPair(0,peer,data)==2900099);backend=true;
 auto observer=std::make_shared<IBluetoothOobObserver>();assert(service.GenerateLocalOobData(0,observer)==801);
 assert(service.GenerateLocalOobData(2,observer)==401 && service.GenerateLocalOobData(0,nullptr)==401);
 btOn=false;assert(service.GenerateLocalOobData(0,observer)==2900003);btOn=true;
 data.addressPresent=data.confirmationPresent=data.randomPresent=false;assert(service.StartPair(0,peer,data)==0 && ordinaryCalls==1);
 assert(permissionCalls>0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root);server=(source/'server/src/bluetooth_host_server.cpp').read_text()
            actual=body(server,'int32_t BluetoothHostServer::StartPair(')+'\n'+body(server,'int32_t BluetoothHostServer::GenerateLocalOobData(')
            compile_run(PREAMBLE+store(source)+declarations+actual+cases,root)


    def test_actual_classic_and_le_handlers_consume_match_and_reject_late_requests(self):
        declarations=r'''
#define HILOGI(...) do {}while(0)
#define HILOGE(...) do {}while(0)
#define LOG_DEBUG(...) do {}while(0)
#define LOG_ERROR(...) do {}while(0)
constexpr int BT_SUCCESS=0,BT_BAD_PARAM=7,BT_PUBLIC_DEVICE_ADDRESS=0,BT_RANDOM_DEVICE_ADDRESS=1;
constexpr int GAP_ACCEPT=1,GAP_NOT_ACCEPT=0,GAP_OOB_DATA_NOT_PRESENT=0,GAP_OOB_DATA_PRESENT_P192=1,GAP_OOB_DATA_PRESENT_P256=2,GAP_MITM_REQUIRED=1,GAP_OOB_DATA_SIZE=16;
constexpr int PAIR_NONE=0,PAIR_PAIRING=1,PAIR_CANCELING=2,PAIR_CONFIRM_STATE_USER_CONFIRM_REPLY=3,PAIR_CONFIRM_STATE_USER_CONFIRM=4,ADAPTER_BREDR=0;
struct BtAddr {uint8_t addr[6]{};uint8_t type=0;};
struct GapOOBData {uint8_t C[16]{},R[16]{};};
struct RawAddress {
 std::array<uint8_t,6> peer;explicit RawAddress(std::array<uint8_t,6> v):peer(v){}explicit RawAddress(std::string):peer{1,2,3,4,5,6}{}
 void ConvertToUint8(uint8_t* a)const{std::copy(peer.begin(),peer.end(),a);}std::string GetAddress()const{return "peer";}
 static RawAddress ConvertToString(const uint8_t *a){std::array<uint8_t,6> p;std::copy_n(a,6,p.begin());return RawAddress(p);}
};
int gapError=0,cancelError=0,classicCalls=0,extendedCalls=0,negativeCalls=0,cancelCalls=0,ioCurve=-1,ioAccept=-1,failedEvents=0;
GapOOBData received;bool timerOk=true,startOk=true;int starts=0;std::vector<std::function<void()>> expired;
int memcpy_s(void* to,size_t max,const void* from,size_t n){assert(n<=max);memcpy(to,from,n);return 0;}
int memset_s(void* to,size_t max,int value,size_t n){assert(n<=max);memset(to,value,n);return 0;}
int GAPIF_RemoteOobRsp(const BtAddr*,int accept,const GapOOBData *data){if(accept){++classicCalls;received=*data;}else ++negativeCalls;return gapError;}
int GAPIF_RemoteOobExtendedRsp(const BtAddr*,int accept,const GapOOBData *a,const GapOOBData *b){assert(accept && a==nullptr && b);++extendedCalls;received=*b;return gapError;}
int GAPIF_CancelAuthenticationReq(const BtAddr*){++cancelCalls;return cancelError;}
int GAPIF_IOCapabilityRsp(const BtAddr*,int accept,int,int curve,int){ioAccept=accept;ioCurve=curve;return gapError;}
int GAPIF_PairIsFromLocal(const BtAddr*,bool* local){*local=true;return 0;}
struct ClassicUtils {static void CheckReturnValue(const char*,const char*,bool){}};
namespace utility {struct Timer {std::function<void()> callback;explicit Timer(std::function<void()> cb):callback(cb){expired.push_back(cb);}bool Start(int){return timerOk;}};}
struct Remote {int state=PAIR_PAIRING;bool local=true;int GetPairedStatus()const{return state;}void SetPairedStatus(int s){state=s;}int GetPairConfirmState()const{return 0;}int GetPairConfirmType()const{return 0;}std::string GetAddress()const{return "peer";}std::string GetRemoteName()const{return "known";}void SetBondedFromLocal(bool b){local=b;}};
using ClassicRemoteDevice=Remote;
struct Properties {int GetIoCapability()const{return 1;}};
struct ClassicAdapter {
 struct Impl {std::recursive_mutex syncMutex_;std::shared_ptr<PendingOobPair> oobPair_=std::make_shared<PendingOobPair>();std::unique_ptr<utility::Timer> oobTimer_;};
 std::unique_ptr<Impl> pimpl=std::make_unique<Impl>();bool isDisable_=false,btmEnableSuccess_=true;Properties adapterProperties_;
 std::shared_ptr<Remote> remote=std::make_shared<Remote>();std::map<std::string,std::shared_ptr<Remote>> devices_{{"peer",remote}};
 BtAddr ConvertToBtAddr(const RawAddress &d)const{BtAddr a;d.ConvertToUint8(a.addr);return a;}
 bool StartPair(const RawAddress&){++starts;return startOk;}
 std::shared_ptr<Remote> FindRemoteDevice(const RawAddress&){return remote;}
 void SendPairStatusChanged(int,const RawAddress&,int){++failedEvents;}void SendPairRequested(int,const RawAddress&){}void GetRemoteName(const BtAddr&){}
 void UserConfirmAutoReply(const RawAddress&,int,bool){}
 bool StartPairOutOfBand(const RawAddress&,const PairingOobData&);void ReplyRemoteOob(const BtAddr&);void SetIoCapability(const BtAddr&);bool CancelPairing(const RawAddress&);
};
constexpr int GAP_LE_AUTH_REQ_BONDING=1,GAP_LE_AUTH_REQ_BIT_MITM=4,GAP_LE_AUTH_REQ_BIT_SC=8,GAP_LE_KEY_DIST_ENC_KEY=1,GAP_LE_KEY_DIST_ID_KEY=2,GAP_LE_KEY_DIST_SIGN_KEY=4,GAP_LE_OOB_DATA_PRESENT=1,GAP_LINKKEY_SIZE=16,BLUETOOTH_CORE_SPECIFICATION_4_2=8;
enum GAP_LeSecMode1Level {LE_MODE_1_LEVEL_3=3,LE_MODE_1_LEVEL_4=4};
struct GapLePairFeature {uint8_t ioCapability=0,oobDataFlag=0,authReq=0,maxEncKeySize=0,initKeyDis=0,respKeyDis=0;};
struct BtmLocalVersionInformation {int hciVersion=9;};int BTM_GetLocalVersionInformation(BtmLocalVersionInformation*){return 0;}
int leCalls=0,leNegative=0,leCancel=0,leCompleted=0,lastComplete=0,leError=0;GapLePairFeature advertised;
int GAPIF_LePairFeatureRsp(const BtAddr*,GapLePairFeature feature){advertised=feature;return leError;}
int GAPIF_LePairOobRsp(const BtAddr*,int accept,uint8_t*){assert(accept==0);++leNegative;return leError;}
int GAPIF_LePairScOobRsp(const BtAddr*,int accept,const uint8_t* c,const uint8_t* r){if(accept){++leCalls;memcpy(received.C,c,16);memcpy(received.R,r,16);}else ++leNegative;return leError;}
int GAPIF_LeCancelPair(const BtAddr*){++leCancel;return leError;}
struct IAdapterBle {};struct BleAdapter: IAdapterBle {void LePairComplete(const RawAddress&,int status){++leCompleted;lastComplete=status;}int GetPeerDeviceAddrType(const RawAddress&){return 0;}};
bool scEnabled=true;struct BleConfig {static BleConfig& GetInstance(){static BleConfig c;return c;}int GetIoCapability(){return 1;}bool GetBleSecurity(){return scEnabled;}int GetBleModel1Level(){return 3;}void SetPeerKeyType(const std::string&,const std::string&){}void Save(){}};
enum CompatType {COMPAT_DISABLE_BLE_SECURE_CONNECTIONS};struct Compat {static bool CompatCheck(CompatType,const std::string&){return false;}};
struct BleGapCallbackParam {struct {BtAddr addr;} lePairOobReq_,lePairScOob_req_;struct {BtAddr peerAddr;} lePairFeatureReq_;struct {BtAddr addr;int result=0,keyType=0;}lePairComplete_;};
struct BleSecurity {
 struct Impl {std::shared_ptr<PendingOobPair> oobPair_=std::make_shared<PendingOobPair>();std::unique_ptr<utility::Timer> oobTimer_;};std::unique_ptr<Impl> pimpl=std::make_unique<Impl>();IAdapterBle *bleAdapter_=nullptr;
 static bool StartPair(const RawAddress&,uint8_t){++starts;return startOk;}
 bool StartPairOutOfBand(const RawAddress&,const PairingOobData&);void SetOobEnabled(bool);
 bool GapLePairOobReq(const BleGapCallbackParam&)const;bool GapLePairScOobReq(const BleGapCallbackParam&)const;bool LePairFeatureReq(const BleGapCallbackParam&)const;bool GapLePairComplete(const BleGapCallbackParam&)const;
};
'''
        cases=r'''
int main(){
 RawAddress device(std::array<uint8_t,6>{1,2,3,4,5,6});BtAddr peer;device.ConvertToUint8(peer.addr);
 PairingOobData data;data.peer=device.peer;data.curve=1;data.confirmation.fill(19);data.randomizer.fill(91);data.hasRandomizer=true;
 ClassicAdapter classic;classic.pimpl->oobPair_->SetEnabled(true);assert(classic.StartPairOutOfBand(device,data));
 classic.SetIoCapability(peer);assert(ioAccept==1 && ioCurve==1);classic.ReplyRemoteOob(peer);
 assert(classicCalls==1 && received.C[0]==19 && received.R[0]==91);classic.ReplyRemoteOob(peer);assert(negativeCalls==1);
 assert(!classic.StartPairOutOfBand(device,data));classic.pimpl->oobPair_->Complete(peer.addr);data.curve=2;
 assert(classic.StartPairOutOfBand(device,data));classic.SetIoCapability(peer);assert(ioCurve==2);
 classic.ReplyRemoteOob(peer);assert(extendedCalls==1 && received.C[0]==19);
 classic.pimpl->oobPair_->Complete(peer.addr);classic.remote->state=PAIR_PAIRING;assert(classic.StartPairOutOfBand(device,data));
 cancelError=9;assert(!classic.CancelPairing(device));assert(classic.pimpl->oobPair_->State(peer.addr,0)==2);cancelError=0;
 classic.pimpl->oobPair_->Complete(peer.addr);classic.remote->state=PAIR_PAIRING;
 startOk=false;assert(!classic.StartPairOutOfBand(device,data));startOk=true;
 timerOk=false;assert(!classic.StartPairOutOfBand(device,data));timerOk=true;
 assert(classic.StartPairOutOfBand(device,data));testNow+=std::chrono::milliseconds(PendingOobPair::TIMEOUT_MS);expired.back()();
 classic.SetIoCapability(peer);assert(ioAccept==0);classic.ReplyRemoteOob(peer);assert(negativeCalls==2);
 classic.pimpl->oobPair_->Complete(peer.addr);classic.remote->state=PAIR_PAIRING;assert(classic.StartPairOutOfBand(device,data));
 gapError=31;classic.ReplyRemoteOob(peer);assert(classic.remote->state==PAIR_NONE && failedEvents>0);gapError=0;
 auto afterTeardown=expired.back();classic.pimpl.reset();afterTeardown();
 BleAdapter adapter;BleSecurity ble;ble.bleAdapter_=&adapter;ble.SetOobEnabled(true);
 assert(ble.StartPairOutOfBand(device,data));BleGapCallbackParam event;event.lePairFeatureReq_.peerAddr=peer;
 assert(ble.LePairFeatureReq(event) && advertised.oobDataFlag==1 && (advertised.authReq&GAP_LE_AUTH_REQ_BIT_SC));
 event.lePairScOob_req_.addr=peer;assert(ble.GapLePairScOobReq(event) && leCalls==1 && received.C[0]==19 && received.R[0]==91);
 assert(!ble.GapLePairScOobReq(event) && leNegative==1 && leCompleted==1 && lastComplete!=0);
 event.lePairComplete_.addr=peer;assert(ble.GapLePairComplete(event));assert(ble.StartPairOutOfBand(device,data));
 scEnabled=false;assert(!ble.LePairFeatureReq(event) && leCancel>0);scEnabled=true;ble.GapLePairComplete(event);
 assert(ble.StartPairOutOfBand(device,data));event.lePairScOob_req_.addr.addr[0]=99;
 assert(!ble.GapLePairScOobReq(event));assert(ble.pimpl->oobPair_->State(peer.addr,0)==1);
 event.lePairScOob_req_.addr=peer;leError=43;assert(!ble.GapLePairScOobReq(event) && lastComplete==43);leError=0;ble.GapLePairComplete(event);
 assert(ble.StartPairOutOfBand(device,data));event.lePairOobReq_.addr=peer;assert(ble.GapLePairOobReq(event));
 assert(ble.pimpl->oobPair_->State(peer.addr,0)==2);ble.GapLePairComplete(event);
 assert(ble.StartPairOutOfBand(device,data));ble.SetOobEnabled(false);assert(!ble.GapLePairScOobReq(event) && !ble.StartPairOutOfBand(device,data));
 auto delayed=expired.back();ble.pimpl.reset();delayed();
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=prepared(root)
            classic=(source/'service/src/classic/classic_adapter.cpp').read_text();ble=(source/'service/src/ble/ble_security.cpp').read_text()
            actual='\n'.join(body(classic,signature) for signature in (
                'bool ClassicAdapter::StartPairOutOfBand(', 'void ClassicAdapter::ReplyRemoteOob(',
                'void ClassicAdapter::SetIoCapability(', 'bool ClassicAdapter::CancelPairing('))
            actual+='\n'+'\n'.join(body(ble,signature) for signature in (
                'bool BleSecurity::StartPairOutOfBand(', 'void BleSecurity::SetOobEnabled(',
                'bool BleSecurity::GapLePairOobReq(', 'bool BleSecurity::GapLePairScOobReq(',
                'bool BleSecurity::LePairFeatureReq(', 'bool BleSecurity::GapLePairComplete('))
            compile_run(PREAMBLE+'#include <map>\n'+store(source).replace('std::chrono::steady_clock::now()','testNow')+declarations+actual+cases,root)


if __name__=='__main__':unittest.main()
