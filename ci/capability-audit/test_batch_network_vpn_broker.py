"""Exercise the real private broker parser, ownership registry and OS workers.

macOS supplies only prctl's unsupported kernel API as an explicit double; fork,
process groups, socketpair, deadlines, signals and filesystem cleanup stay real.
Linux runs the actual prctl/subreaper and additionally kills a blocked descendant.
No test can publish CONNECTED; TLS/TUN still belong to the real backend.
"""
from pathlib import Path
import os
import ast
import base64
import json
import subprocess
import sys
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT, EXT, BASE, body, compile_run

FIXTURE=Path(__file__).with_name("fixtures")/"batch_network/vpn-broker-prepared.json"

# Execute the emitted native main on the host too. This explicit FFRT double
# supplies an asynchronous serial worker; it does not replace target FFRT proof.
ASYNC_FFRT=r'''
namespace ffrt {
using shared_mutex=std::shared_mutex;
struct task_attr {task_attr&delay(uint64_t){return *this;}};
class queue {
 std::mutex mutex_;std::condition_variable changed_;std::deque<std::function<void()>> tasks_;
 bool stopped_=false;std::thread worker_;
 void Run(){
  for(;;){
   std::function<void()> task;
   {
    std::unique_lock<std::mutex> lock(mutex_);
    changed_.wait(lock,[this]{return stopped_ || !tasks_.empty();});
    if(tasks_.empty()){
     if(stopped_){return;}
     continue;
    }
    task=std::move(tasks_.front());tasks_.pop_front();
   }
   task();
  }
 }
public:
 explicit queue(const char*):worker_([this]{Run();}){}
 ~queue(){
  {std::lock_guard<std::mutex> lock(mutex_);stopped_=true;}
  changed_.notify_all();worker_.join();
 }
 void*submit_h(std::function<void()> task,const task_attr& = {}){
  {std::lock_guard<std::mutex> lock(mutex_);if(stopped_){return nullptr;}tasks_.push_back(std::move(task));}
  changed_.notify_one();return this;
 }
};
}
'''

def prepared(root):
    for name,encoded in json.loads(FIXTURE.read_text()).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
    for project,component in [(BASE,"qemu_openvpn_broker"),(EXT,"openvpn_broker")]:
        subprocess.run(["bash",str(ROOT/"patches/common"/project/component/"apply.sh"),"--source-root",str(root)],check=True,capture_output=True)



class VpnBrokerTests(unittest.TestCase):
    def test_complete_exact_broker_chain_and_unknown_edits(self):
        from test_connected_vpn_nullable import staged
        from test_batch_network_openvpn_session import prepared as session_prepared
        from test_batch_network_vpn_callbacks import prepared as callbacks_prepared
        from test_batch_network_vpn_client_warnings import prepared as warnings_prepared
        from test_batch_network_openvpn_lifecycle import staged as lifecycle_staged, apply as lifecycle_apply
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);lifecycle_staged(root);lifecycle_apply(root);staged(root)
            ext=ROOT/'patches/common'/EXT
            subprocess.run(['bash',str(ext/'connected_vpn_nullable/apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            session_prepared(root);callbacks_prepared(root);warnings_prepared(root);prepared(root)
            for project,names in [(BASE,['qemu_openvpn_control','qemu_openvpn_broker']),
                (EXT,['always_on_vpn','connected_vpn_nullable','openvpn_lifecycle','openvpn_session','vpn_callback_dispatch','netvpn_callback_unused','openvpn_broker'])]:
                for name in names:
                    result=subprocess.run(['bash',str(ROOT/'patches/common'/project/name/'apply.sh'),'--source-root',str(root)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,name+result.stderr)
            target=root/EXT/'services/vpnmanager/src/multi_vpn_helper.cpp'
            target.write_bytes(target.read_bytes()+b'// unreviewed change\n')
            result=subprocess.run(['bash',str(ext/'vpn_callback_dispatch/apply.sh'),'--source-root',str(root)],capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_actual_new_dispatch_cancels_connected_before_blocking_stop(self):
        import test_batch_network_vpn_callbacks as previous
        parsed=ast.parse(Path(previous.__file__).read_text())
        method=next(node for node in ast.walk(parsed) if isinstance(node,ast.FunctionDef) and node.name=='test_actual_functions_reentry_epoch_owner_order_teardown_and_delivery_failures')
        literals={node.targets[0].id:ast.literal_eval(node.value) for node in method.body
            if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant)}
        declarations=literals['declarations'].replace('int Destroy(){++destroys;return destroyError;}',
            'bool nativeSession=false;bool HasQemuSession(){return nativeSession;}int Destroy(){++destroys;return destroyError;}')
        declarations=declarations.replace(' NetworkVpnService();~NetworkVpnService();',' NetworkVpnService();~NetworkVpnService();\n int DestroyOwnedConnection(const std::shared_ptr<NetVpnImpl>&);bool ScheduleQemuHealthCheck();bool ReconcileQemuSessions(bool,uint64_t=0);')
        declarations=declarations.replace('bool nativeSession=false;bool HasQemuSession(){return nativeSession;}', 'bool nativeSession=false;bool HasQemuSession(){return nativeSession;}bool QemuNeedsRecovery(){return false;}')
        declarations=declarations.replace('std::shared_ptr<NetVpnImpl> vpnObj_;','std::shared_ptr<NetVpnImpl> vpnObj_,connectingObj_;')
        declarations=declarations.replace('namespace ffrt {using shared_mutex=', 'namespace ffrt {struct task_attr{task_attr&delay(uint64_t){return *this;}};using shared_mutex=')
        declarations=declarations.replace('void* submit_h(std::function<void()> task)', 'void* submit_h(std::function<void()> task,const task_attr & = {})')
        declarations+='\nstd::shared_ptr<NetVpnImpl> QemuOpenvpn(const std::shared_ptr<NetVpnImpl>& object){return object && object->nativeSession?object:nullptr;}\n'
        addition=r'''
 auto closingObject=std::make_shared<NetVpnImpl>();closingObject->nativeSession=true;
 auto closing=service->CreateConnectionCallback(closingObject,"closing.owner",100,"closing");closing->Commit();Drain();
 const int oldPublications=service->publishes;const auto oldStates=restarted->states.size();
 // The original host main already destroyed its single VPN on remote death;
 // the native main still owns nextObject. Exercise the same exclusion boundary
 // in both mains, then tear down the single VPN before the multi-owner case.
 {
  std::unique_lock<ffrt::shared_mutex> lock(service->netVpnMutex_);
  if(!service->vpnObj_){service->vpnObj_=std::make_shared<NetVpnImpl>();}
  assert(!service->vpnObj_->IsSystemVpn());
  assert(!service->IsNeedNotify(VpnConnectState::VPN_DISCONNECTED,"closing",100));
 }
 closing->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,State("closing"));Drain();
 assert(restarted->states.size()==oldStates && service->publishes==oldPublications);
 {
  std::unique_lock<ffrt::shared_mutex> lock(service->netVpnMutex_);
  auto single=service->vpnObj_;
  assert(service->DestroyOwnedConnection(single)==0 && single->destroys==1);
  service->vpnObj_.reset();
  assert(service->IsNeedNotify(VpnConnectState::VPN_DISCONNECTED,"closing",100));
 }
 std::future<bool> publisher;
 {
  std::unique_lock<ffrt::shared_mutex> lock(service->netVpnMutex_);
  closing->SendConnStateChanged(VpnConnectState::VPN_CONNECTED,2,"closing");
  publisher=std::async(std::launch::async,[]{return DrainOne();});
  assert(publisher.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout);
  assert(service->DestroyOwnedConnection(closingObject)==0 && closingObject->destroys==1);
 }
 assert(publisher.wait_for(std::chrono::seconds(1))==std::future_status::ready);publisher.get();Drain();
 assert(service->publishes==oldPublications);
 closing->OnVpnConnStateChanged(VpnConnectState::VPN_CONNECTED,State("closing"));Drain();assert(restarted->states.size()==oldStates);
 closing->OnVpnConnStateChanged(VpnConnectState::VPN_DISCONNECTED,State("closing"));Drain();
 assert(restarted->states.size()==oldStates+1 && !restarted->states.back() && restarted->owners.back()=="closing.owner");
'''
        cases=literals['cases'].replace(' auto pendingObject=std::make_shared<NetVpnImpl>();',addition+' auto pendingObject=std::make_shared<NetVpnImpl>();')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);source=root/EXT/'services/vpnmanager'
            text=(source/'src/networkvpn_service.cpp').read_text();header=(source/'include/networkvpn_service.h').read_text()
            a=header.index('    class VpnConnStateCb :');b=header.index('\n    class ReceiveMessage',a);declarations=declarations.replace(' CALLBACK_CLASS',header[a:b])
            a=text.index('namespace {\nffrt::queue &VpnExternalCallbackQueue()');b=text.index('NetworkVpnService::NetworkVpnService()',a);actual=text[a:b]
            signatures=['NetworkVpnService::~NetworkVpnService()', 'bool NetworkVpnService::IsNeedNotify(', 'void NetworkVpnService::VpnConnStateCb::OnVpnConnStateChanged(', 'void NetworkVpnService::VpnConnStateCb::SendConnStateChanged(', 'void NetworkVpnService::VpnConnStateCb::OnMultiVpnConnStateChanged(', 'void NetworkVpnService::OnVpnMultiUserSetUp()', 'int32_t NetworkVpnService::SyncRegisterVpnEvent(', 'int32_t NetworkVpnService::SyncUnregisterVpnEvent(', 'int32_t NetworkVpnService::SyncRegisterMultiVpnEvent(', 'int32_t NetworkVpnService::SyncUnregisterMultiVpnEvent(', 'void NetworkVpnService::OnRemoteDied(', 'void NetworkVpnService::RemoveALLClientDeathRecipient()', 'int32_t NetworkVpnService::GetConnectedSysVpnConfig(', 'int32_t NetworkVpnService::DestroyOwnedConnection(']
            for signature in signatures:actual+='\n'+body(text,signature)
            declarations+='#include <cstring>\nconstexpr const char *INNER_CHL_NAME="inner-chl";\n'
            compile_run(declarations+actual+cases,root,extra=('-pthread',))
            begin=declarations.index('namespace ffrt {');end=declarations.index('struct SysVpnConfig',begin)
            native_cases=literals['cases'][:literals['cases'].index('int main(){')]+previous.NATIVE_MAIN
            native_addition=addition.replace('Drain();','NativeFlush();').replace('std::future<bool> publisher;','std::future<void> publisher;').replace('return DrainOne();','NativeFlush();')
            native_cases=native_cases.replace('    auto pendingObject = std::make_shared<NetVpnImpl>();',native_addition+'    auto pendingObject = std::make_shared<NetVpnImpl>();')
            async_declarations=declarations[:begin]+ASYNC_FFRT+declarations[end:]
            compile_run(async_declarations+actual+native_cases,root,extra=('-pthread',))
            native_output=os.environ.get('BATCH_NETWORK_BROKER_CALLBACK_NATIVE_OUTPUT')
            if native_output:
                native=declarations[:begin]+'#include "ffrt.h"\n'+declarations[end:]
                Path(native_output).write_text('// Actual multi-owner stop epoch/functions; real FFRT. Account/IPC/backend remain explicit doubles.\n'+native+actual+native_cases)

    def test_actual_codec_roundtrip_owner_replay_and_socket_framing(self):
        source=r'''
#include "broker_protocol.h"
#include <cassert>
#include <thread>
#include <vector>
int main(){
 using namespace OhosOpenvpn;
 BrokerCommand command; command.start=true; command.owner={20000123,100,"com.owner.one","vpn-id\nwith-newline"};
 command.interfaceName="multitun-vpn1";command.session={std::string(32,'a'),"client\n<key>actual</key>\n","secret"};
 auto wire=EncodeBroker(command);assert(!wire.empty());BrokerCommand copy;assert(DecodeBroker(wire,copy));
 assert(copy.owner==command.owner && copy.session.token==command.session.token && copy.session.profile==command.session.profile);
 assert(copy.session.password=="secret" && copy.interfaceName=="multitun-vpn1");
 pid_t worker=-1;std::string start;assert(DecodeStartReply(StartReply(23,"12345"),worker,start) && worker==23 && start=="12345");
 for(auto invalid:{"0","0\n0\n123","0\n23\n0","0\n23\n12x","0\n23\n123\n","0\n2147483648\n123"})assert(!DecodeStartReply(invalid,worker,start));
 for(auto suffix:{std::string("x"),std::string("\0",1)})assert(!DecodeBroker(wire+suffix,copy));
 for(size_t cut=0;cut<wire.size();++cut)assert(!DecodeBroker(wire.substr(0,cut),copy));
 for(auto name:{"multitun-vpn0","multitun-vpn01","multitun-vpn21","multitun-vpn-1","tun-vpn","../../tun","multitun-vpn1x"}){
  command.interfaceName=name;assert(EncodeBroker(command).empty());
 }
 for(auto name:{"multitun-vpn1","multitun-vpn9","multitun-vpn20"})assert(BrokerInterface(name));
 command.interfaceName="multitun-vpn2";command.owner.uid=-1;assert(EncodeBroker(command).empty());command.owner.uid=23;
 command.owner.bundle=std::string("bad\0bundle",10);assert(EncodeBroker(command).empty());command.owner.bundle="actual.owner";
 command.start=false;assert(EncodeBroker(command).empty());command.session.profile.clear();command.session.password.clear();
 assert(DecodeBroker(EncodeBroker(command),copy) && !copy.start && copy.owner==command.owner);
 int sockets[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)==0);
 std::thread sender([&]{assert(SendFrame(sockets[0],wire));});std::string frame;
 assert(ReadFrame(sockets[1],frame) && frame==wire);sender.join();
 assert(!ReadFrame(sockets[1],frame,10));
 uint32_t size=htonl(MAX_BROKER_FRAME+1);assert(write(sockets[0],&size,4)==4);assert(!ReadFrame(sockets[1],frame));
 close(sockets[0]);close(sockets[1]);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            compile_run(source,Path(temporary))

    def test_actual_broker_two_owners_stop_isolation_replay_and_cleanup(self):
        source=r'''
#include "broker_runtime.h"
#include <cassert>
#include <filesystem>
#include <fstream>
int main(int argc,char **argv){
 assert(argc==2);using namespace OhosOpenvpn;const std::string root=argv[1];assert(mkdir(root.c_str(),0700)==0);
 BrokerRuntime broker(root,getuid(),[](const BrokerCommand&,const std::string &directory){
  alarm(10);std::ofstream(directory+"/client.ovpn")<<"private credentials";
  for(;;){
   pause();
  }
  return 0;
 });assert(broker.Open());
 BrokerCommand one;one.start=true;one.owner={1000023,100,"first.owner","one"};one.interfaceName="multitun-vpn1";
 one.session={std::string(32,'a'),"client\nactual-profile\n","one-password"};
 auto two=one;two.owner={1000045,100,"second.owner","two"};two.interfaceName="multitun-vpn2";two.session.token=std::string(32,'b');
 assert(broker.Apply(one)==0);assert(broker.Apply(two)==0 && broker.Count()==2);
 assert(broker.Apply(one)==EALREADY && broker.Count()==2);
 auto duplicate=one;duplicate.session.token=std::string(32,'c');assert(broker.Apply(duplicate)==EEXIST);
 duplicate.owner.bundle="third.owner";duplicate.owner.vpnId="third";assert(broker.Apply(duplicate)==EEXIST);
 auto stop=BrokerMetadata(one);stop.owner=two.owner;assert(broker.Apply(stop)==EPERM && broker.Count()==2);
 stop=BrokerMetadata(one);stop.interfaceName=two.interfaceName;assert(broker.Apply(stop)==EPERM && broker.Count()==2);
 stop=BrokerMetadata(one);assert(broker.Apply(stop)==0 && broker.Count()==1);
 assert(broker.Apply(stop)==0 && broker.Count()==1);assert(broker.Apply(one)==EALREADY);
 auto fresh=one;fresh.session.token=std::string(32,'c');assert(broker.Apply(fresh)==0 && broker.Count()==2);
 broker.Shutdown();assert(broker.Count()==0);
 for(const auto &entry:std::filesystem::directory_iterator(root))assert(entry.path().filename()=="backend.lock");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);extra=[]
            if not sys.platform.startswith('linux'):
                stub=root/'sys';stub.mkdir();(stub/'prctl.h').write_text('#pragma once\n#define PR_SET_PDEATHSIG 1\ninline int prctl(int,int,int,int,int){return 0;}\n')
                extra=['-I',str(root)]
            compile_run(source,root,arguments=[str(root/'sessions')],extra=extra)

    @unittest.skipUnless(sys.platform.startswith('linux'),'requires real Linux broker/worker/client/bridge parent death')
    def test_linux_sigkill_broker_kills_all_descendants_and_reclaims_credentials(self):
        source=r'''
#include "broker_runtime.h"
#include <cassert>
#include <filesystem>
struct Trace{char role;pid_t pid;};
void Record(int fd,char role){Trace trace{role,getpid()};assert(write(fd,&trace,sizeof(trace))==sizeof(trace));}
int main(int argc,char **argv){assert(argc==2);using namespace OhosOpenvpn;assert(prctl(PR_SET_CHILD_SUBREAPER,1)==0);
 const std::string root=argv[1];assert(mkdir(root.c_str(),0700)==0);int pipeFd[2];assert(pipe(pipeFd)==0);const pid_t owner=getpid();const pid_t controller=fork();assert(controller>=0);
 if(controller==0){assert(BindToParent(owner));close(pipeFd[0]);BrokerRuntime broker(root,getuid(),[&](const BrokerCommand&,const std::string&directory){
  int secret=open((directory+"/askpass").c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);assert(secret>=0 && write(secret,"secret",6)==6);close(secret);Record(pipeFd[1],'w');
  const pid_t worker=getpid();const pid_t client=fork();assert(client>=0);if(client==0){assert(BindToParent(worker));Record(pipeFd[1],'c');const pid_t clientPid=getpid();const pid_t bridge=fork();assert(bridge>=0);if(bridge==0){assert(BindToParent(clientPid));Record(pipeFd[1],'t');}for(;;)pause();}for(;;)pause();return 0;
 });assert(broker.Open());BrokerCommand command;command.start=true;command.owner={23,100,"actual.owner","one"};command.interfaceName="multitun-vpn1";command.session={std::string(32,'a'),"client\nactual-profile\n","secret"};assert(broker.Apply(command)==0);for(;;)pause();}
 close(pipeFd[1]);std::vector<pid_t>pids;for(int i=0;i<3;++i){pollfd ready{pipeFd[0],POLLIN,0};assert(poll(&ready,1,3000)>0);Trace trace{};assert(read(pipeFd[0],&trace,sizeof(trace))==sizeof(trace));assert(!ProcessStart(trace.pid).empty());pids.push_back(trace.pid);}close(pipeFd[0]);
 assert(kill(controller,SIGKILL)==0);int status=0;while(waitpid(controller,&status,0)<0)assert(errno==EINTR);
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);for(;;){const pid_t child=waitpid(-1,&status,WNOHANG);if(child>0)continue;if(child<0 && errno==EINTR)continue;if(child<0 && errno==ECHILD)break;assert(std::chrono::steady_clock::now()<deadline);poll(nullptr,0,10);}
 for(pid_t pid:pids){
  assert(ProcessStart(pid).empty());
 }
 bool secretLeft=false;for(const auto &entry:std::filesystem::directory_iterator(root))if(entry.is_directory())secretLeft=std::filesystem::exists(entry.path()/"askpass");assert(secretLeft);
 SessionStore restarted;assert(restarted.Open(root.c_str(),getuid()));for(const auto &entry:std::filesystem::directory_iterator(root))assert(entry.path().filename()=="backend.lock");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);compile_run(source,root,arguments=[str(root/'sessions')])

    @unittest.skipUnless(sys.platform.startswith('linux'),'requires real Linux subreaper/PDEATHSIG')
    def test_linux_stop_reaps_worker_and_descendant_blocked_on_callback(self):
        source=r'''
#include "broker_runtime.h"
#include <cassert>
#include <fstream>
int main(int argc,char **argv){
 assert(argc==2);using namespace OhosOpenvpn;std::string root=argv[1];assert(mkdir(root.c_str(),0700)==0);
 BrokerRuntime broker(root,getuid(),[](const BrokerCommand&,const std::string &directory){
  const pid_t worker=getpid();const pid_t child=fork();assert(child>=0);
  if(child==0){assert(BindToParent(worker));signal(SIGTERM,SIG_IGN);for(;;)pause();}
  std::ofstream(directory+"/client.ovpn")<<child;signal(SIGTERM,SIG_IGN);for(;;)pause();return 0;
 });assert(broker.Open());BrokerCommand command;command.start=true;command.owner={123,100,"actual.owner","blocked"};
 command.interfaceName="multitun-vpn1";command.session={std::string(32,'a'),"client\nactual\n","password"};assert(broker.Apply(command)==0);
 poll(nullptr,0,100);const auto began=std::chrono::steady_clock::now();auto stop=BrokerMetadata(command);
 assert(broker.Apply(stop)==0 && broker.Count()==0);assert(std::chrono::steady_clock::now()-began<std::chrono::seconds(6));
 int status=0;assert(waitpid(-1,&status,WNOHANG)==-1 && errno==ECHILD);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);compile_run(source,root,arguments=[str(root/'sessions')])

if __name__=='__main__':unittest.main()
