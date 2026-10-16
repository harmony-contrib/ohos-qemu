"""Execute the API26 entry/parser with explicit NAPI/native async doubles."""
from pathlib import Path
import base64
import json
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT,body,compile_run

PROJECT='foundation/communication/bluetooth'
COMPONENT=ROOT/'patches/common'/PROJECT/'api26_oob_pairing'
FIXTURE=Path(__file__).with_name('fixtures')/'batch_network/bluetooth-oob-prepared.json'


def patched(root):
    for name,encoded in json.loads(FIXTURE.read_text()).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)


class BluetoothOobTests(unittest.TestCase):
    def test_exact_stack_export_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);patched(root)
            source=root/PROJECT/'frameworks/js/napi/src/connection/napi_bluetooth_connection.cpp'
            text=source.read_text()
            self.assertEqual(text.count('DECLARE_NAPI_FUNCTION("startPairOutOfBand", StartPairOutOfBand)'),1)
            self.assertEqual(text.count('DECLARE_NAPI_FUNCTION("pairDeviceOutOfBand", PairDeviceOutOfBand)'),1)
            subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            source.write_text(text+'// unknown source\n')
            denied=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(denied.returncode,0);self.assertEqual(source.read_text(),text+'// unknown source\n')

    def test_actual_parser_target_optional_selection_async_capture_and_errors(self):
        declarations=r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>
enum napi_status {napi_ok,napi_invalid_arg};
enum napi_valuetype {napi_undefined,napi_null,napi_number,napi_string,napi_object};
enum class OobDataType {P192,P256};
struct OobData {OobDataType type=OobDataType::P192;std::vector<uint8_t> hash,random;std::string rawPeer;void SetOobDataType(OobDataType value){type=value;}};
struct AddressInfo {};
struct Value {napi_valuetype type=napi_undefined;double number=0;std::string text;OobData oob;bool settled=false;int code=0;};
using napi_env=void*;using napi_callback_info=void*;using napi_value=Value*;
constexpr size_t ARGS_SIZE_THREE=3,ARGS_SIZE_FOUR=4,PARAM0=0,PARAM1=1,PARAM2=2,PARAM3=3;
constexpr int BT_TRANSPORT_NONE=-1,BT_ERR_INVALID_PARAM=401,BT_ERR_INTERNAL_ERROR=2900099,ASYNC_WORK_NO_NEED_CALLBACK=0;
std::vector<napi_value> arguments;Value undefinedValue;int thrown=0,parseCalls=0,nativeCalls=0,nativeResult=0;bool enabled=true,failFactory=false;
std::string nativeTarget;int nativeTransport=-1;OobData nativeData;
#define NAPI_BT_CALL_RETURN(call) do {auto status=(call);if(status!=napi_ok)return status;}while(0)
#define NAPI_BT_RETURN_IF(test,message,error) do {if(test)return error;}while(0)
#define NAPI_BT_ASSERT_RETURN_UNDEF(env,test,error) do {if(!(test)){thrown=error;return &undefinedValue;}}while(0)
napi_status napi_get_cb_info(napi_env,napi_callback_info,size_t *count,napi_value *values,napi_value*,void**){
 auto size=std::min(*count,arguments.size());std::copy_n(arguments.begin(),size,values);*count=size;return napi_ok;
}
napi_status NapiParseBdAddr(napi_env,napi_value value,std::string& address){
 if(!value || value->type!=napi_string || value->text.size()!=17 || value->text[2]!=':' || value->text.find('\0')!=std::string::npos)return napi_invalid_arg;
 address=value->text;return napi_ok;
}
bool ParseInt32(napi_env,int32_t& number,napi_value value){if(!value || value->type!=napi_number || !std::isfinite(value->number) || value->number<-2147483648.0 || value->number>2147483647.0)return false;number=static_cast<int32_t>(value->number);return true;}
napi_status napi_get_value_double(napi_env,napi_value value,double* number){if(value->type!=napi_number)return napi_invalid_arg;*number=value->number;return napi_ok;}
napi_status napi_typeof(napi_env,napi_value value,napi_valuetype *type){if(!value)return napi_invalid_arg;*type=value->type;return napi_ok;}
bool IsValidTransport(int value){return value==0 || value==1;}
napi_status ParseOobDataParam(napi_env,napi_value value,int,AddressInfo&,OobData& output){
 ++parseCalls;if(value->type!=napi_object || value->oob.hash.size()!=16 || (!value->oob.random.empty() && value->oob.random.size()!=16))return napi_invalid_arg;
 output=value->oob;return napi_ok;
}
struct NapiHaEventUtils {NapiHaEventUtils(napi_env,const char*){}};
struct NapiAsyncWorkRet {int code;explicit NapiAsyncWorkRet(int value):code(value){}};
struct BluetoothRemoteDevice {
 std::string target;int transport;BluetoothRemoteDevice(const std::string& value,int mode):target(value),transport(mode){}
 int StartPairOutOfBand(const OobData& data){++nativeCalls;nativeTarget=target;nativeTransport=transport;nativeData=data;return enabled?nativeResult:2900003;}
};
struct Work {std::function<NapiAsyncWorkRet()> execute;Value promise;bool queued=false;void Run(){assert(!queued);queued=true;}napi_value GetRet(){return &promise;}void Complete(){assert(queued && !promise.settled);promise.code=execute().code;promise.settled=true;}};
std::vector<std::shared_ptr<Work>> works;
struct NapiAsyncWorkFactory {
 template<class F>static std::shared_ptr<Work> CreateAsyncWork(napi_env,napi_callback_info,F run,int,std::shared_ptr<NapiHaEventUtils>){
  if(failFactory)return nullptr;auto work=std::make_shared<Work>();work->execute=run;works.push_back(work);return work;
 }
};
'''
        cases=r'''
int main(){
 Value id;id.type=napi_string;id.text="11:22:33:AA:BB:FF";Value transport;transport.type=napi_number;transport.number=1;
 Value p192,p256;p192.type=p256.type=napi_object;p192.oob.hash.assign(16,19);p256.oob.hash.assign(16,25);
 p192.oob.rawPeer=p256.oob.rawPeer="AA:BB:CC:DD:EE:FF";p256.oob.random.assign(16,7);
 Value absent,nullValue;nullValue.type=napi_null;
 arguments={&id,&transport,&p192};auto promise=StartPairOutOfBand(nullptr,nullptr);assert(!promise->settled && nativeCalls==0 && works.size()==1);
 id.text="99:88:77:66:55:44";p192.oob.hash[0]=99;works.back()->Complete();
 assert(promise->settled && promise->code==0 && nativeTarget=="11:22:33:AA:BB:FF" && nativeTransport==1 && nativeData.hash[0]==19 && nativeData.type==OobDataType::P192);
 assert(nativeData.rawPeer=="AA:BB:CC:DD:EE:FF");
 id.text="11:22:33:AA:BB:FF";
 for(int error:{201,202,801,2900099}){
  nativeResult=error;arguments={&id,&transport,&p192,&p256};promise=StartPairOutOfBand(nullptr,nullptr);works.back()->Complete();
  assert(promise->code==error && nativeData.type==OobDataType::P256 && nativeData.hash[0]==25);
 }
 enabled=false;arguments={&id,&transport,&absent,&p256};promise=StartPairOutOfBand(nullptr,nullptr);works.back()->Complete();assert(promise->code==2900003);enabled=true;
 const auto count=works.size();const int calls=nativeCalls;
 for(auto bad:std::vector<std::vector<napi_value>>{
  {},{&id,&transport},{&id,&transport,&absent},{&id,&transport,&absent,&absent},
  {&id,&transport,&nullValue},{&id,&transport,&p192,&p256,&absent},
  {&transport,&transport,&p192},{&id,&id,&p192}}){
  arguments=bad;thrown=0;assert(StartPairOutOfBand(nullptr,nullptr)==&undefinedValue && thrown==401 && works.size()==count && nativeCalls==calls);
 }
 arguments={&id,&transport,&p192};
 for(double invalid:{-1.0,2.0,3.0,1.5}){transport.number=invalid;thrown=0;StartPairOutOfBand(nullptr,nullptr);assert(thrown==401 && works.size()==count);}
 transport.number=0;p192.oob.hash.resize(15);thrown=0;StartPairOutOfBand(nullptr,nullptr);assert(thrown==401 && works.size()==count);
 p192.oob.hash.resize(16);p192.oob.random.resize(17);thrown=0;StartPairOutOfBand(nullptr,nullptr);assert(thrown==401 && works.size()==count);
 p192.oob.random.clear();failFactory=true;thrown=0;StartPairOutOfBand(nullptr,nullptr);assert(thrown==2900099 && works.size()==count && nativeCalls==calls);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);patched(root)
            source=(root/PROJECT/'frameworks/js/napi/src/connection/napi_bluetooth_connection.cpp').read_text()
            actual='\n'.join(body(source,sig) for sig in ('napi_status CheckStartPairOobParam(', 'napi_value StartPairOutOfBand('))
            compile_run(declarations+actual+cases,root)


if __name__=='__main__':unittest.main()
