"""Run real patched control bodies; Linux additionally checks exec parent death."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = 'foundation/communication/netmanager_base'
EXT = 'foundation/communication/netmanager_ext'
HEADERS = ROOT / 'patches/common' / EXT / 'openvpn_backend/files'
COMPONENTS = (ROOT / 'patches/common' / BASE / 'qemu_openvpn_control',
              ROOT / 'patches/common' / EXT / 'openvpn_lifecycle')
FIXTURE = Path(__file__).with_name('fixtures') / 'batch_network/fixed-source.json'


def staged(root):
    for name, encoded in json.loads(FIXTURE.read_text()).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(encoded))


def apply(root):
    for component in COMPONENTS:
        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                       check=True, capture_output=True)


def body(text, signature):
    start = text.index(signature)
    # These pinned definitions use column-zero closing braces; avoid counting
    # braces inside the real logging strings and comments as C++ syntax.
    end = text.index('\n}', text.index('{', start)) + 2
    return text[start:end]


def compile_run(source, directory, arguments=(), extra=()):
    cpp, binary = directory / 'probe.cpp', directory / 'probe'
    cpp.write_text(source)
    compiled = subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra',
                               '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                               '-I', str(HEADERS), *extra, str(cpp), '-o', str(binary)],
                              capture_output=True, text=True)
    if compiled.returncode:
        raise AssertionError(compiled.stderr)
    ran = subprocess.run([str(binary), *arguments], capture_output=True, text=True, timeout=20)
    if ran.returncode:
        raise AssertionError(ran.stderr)


class OpenvpnLifecycleTests(unittest.TestCase):
    def test_checked_stack_idempotence_and_unknown_edit_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged(root)
            apply(root)
            before = {name: (root / name).read_bytes() for name in json.loads(FIXTURE.read_text())}
            apply(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
            for component in COMPONENTS:
                target = next(name for name in before if component.parent.name in name)
                path = root / target
                path.write_bytes(path.read_bytes() + b'// unknown edit\n')
                snapshot = {name: (root / name).read_bytes() for name in before}
                result = subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                                        capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(snapshot, {name: (root / name).read_bytes() for name in before})

    def test_actual_controller_rejects_start_stop_failure_and_clears_stale_config(self):
        declarations = r'''
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
#define NETMGR_EXT_LOG_I(...) ((void)0)
#define VPN_PIDDIR testDirectory
constexpr int NETMANAGER_EXT_SUCCESS=0,NETMANAGER_EXT_ERR_INTERNAL=2200003;
constexpr int OPENVPN_STATE_UNKNOWN=1,OPENVPN_STATE_STARTED=3,OPENVPN_STATE_CONNECTED=4,OPENVPN_STATE_DISCONNECTED=5;
std::string testDirectory;
struct SysVpnConfig {};
struct OpenvpnConfig : SysVpnConfig {};
template<class T> using sptr=std::shared_ptr<T>;
enum class SysVpnStageCode {VPN_STAGE_OPENVPN_RESTART,VPN_STAGE_OPENVPN_STOP,VPN_STAGE_SET_VPN_CALL_MODE};
struct NetsysController {
 int nextResult=0,calls=0; SysVpnStageCode last=SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART;
 static NetsysController& GetInstance(){static NetsysController value;return value;}
 int ProcessVpnStage(SysVpnStageCode stage,const std::string& = ""){++calls;last=stage;return nextResult;}
};
struct NetVpnImpl {int destroyResult=0,destroyCalls=0;int Destroy(){++destroyCalls;return destroyResult;}};
struct MultiInfo {bool isVpnExtCall=false;};
struct OpenvpnCtl : NetVpnImpl {
 sptr<OpenvpnConfig> openvpnConfig_;
 std::shared_ptr<MultiInfo> multiVpnInfo_;
 int openvpnState_=OPENVPN_STATE_UNKNOWN;
 std::vector<int> states;
 void UpdateOpenvpnState(int value){openvpnState_=value;states.push_back(value);}
 int32_t StartOpenvpn(); int32_t StopOpenvpn();int32_t Destroy();
 int32_t GetConnectedSysVpnConfig(sptr<SysVpnConfig>&);
};
'''
        cases = r'''
int main(int argc,char** argv){
 assert(argc==2);testDirectory=argv[1];
 auto &backend=NetsysController::GetInstance();OpenvpnCtl ctl;
 assert(ctl.StartOpenvpn()==NETMANAGER_EXT_ERR_INTERNAL && backend.calls==0 && ctl.openvpnState_==5);
 ctl.openvpnConfig_=std::make_shared<OpenvpnConfig>();
 assert(ctl.StartOpenvpn()==NETMANAGER_EXT_ERR_INTERNAL && backend.calls==0 && ctl.openvpnState_==5);
 std::filesystem::create_directory(testDirectory);
 for (int error : {-1,5,2200003}){
  backend.nextResult=error;
  assert(ctl.StartOpenvpn()==NETMANAGER_EXT_ERR_INTERNAL && ctl.openvpnState_==5);
  assert(backend.last==SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART);
 }
 backend.nextResult=0;
 assert(ctl.StartOpenvpn()==0 && ctl.openvpnState_==3);
 sptr<SysVpnConfig> output=ctl.openvpnConfig_;
 assert(ctl.GetConnectedSysVpnConfig(output)==0 && !output);
 ctl.openvpnState_=OPENVPN_STATE_CONNECTED;
 assert(ctl.GetConnectedSysVpnConfig(output)==0 && output==ctl.openvpnConfig_);
 backend.nextResult=-1;ctl.states.clear();
 assert(ctl.StopOpenvpn()==NETMANAGER_EXT_ERR_INTERNAL && ctl.openvpnState_==4 && ctl.states.empty());
 assert(backend.last==SysVpnStageCode::VPN_STAGE_OPENVPN_STOP);
 assert(ctl.Destroy()==NETMANAGER_EXT_ERR_INTERNAL && ctl.destroyCalls==1);
 ctl.destroyResult=2209001;
 assert(ctl.Destroy()==2209001 && ctl.destroyCalls==2);
 ctl.destroyResult=0;backend.nextResult=0;
 assert(ctl.Destroy()==0 && ctl.destroyCalls==3 && ctl.openvpnState_==5);
 output=ctl.openvpnConfig_;assert(ctl.GetConnectedSysVpnConfig(output)==0 && !output);
 assert(std::filesystem::remove(testDirectory));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged(root)
            apply(root)
            text = (root / EXT / 'services/vpnmanager/src/open_vpn_ctl.cpp').read_text()
            actual = '\n'.join(body(text, signature) for signature in (
                'int32_t OpenvpnCtl::StartOpenvpn(', 'int32_t OpenvpnCtl::StopOpenvpn(',
                'int32_t OpenvpnCtl::Destroy(', 'int32_t OpenvpnCtl::GetConnectedSysVpnConfig('))
            compile_run(declarations + actual + cases, root, [str(root / 'vpn')])

    def test_actual_netsys_qemu_and_other_product_routing(self):
        declarations = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <unistd.h>
#define NETNATIVE_LOGE(...) ((void)0)
#define UNITTEST_FORBID_FFRT 1
namespace NetsysNative {enum class SysVpnStageCode {VPN_STAGE_OPENVPN_RESTART,VPN_STAGE_OPENVPN_STOP,OTHER};}
using NetsysNative::SysVpnStageCode;
namespace NetManagerStandard {constexpr int NETMANAGER_SUCCESS=0;}
constexpr int NETMANAGER_ERROR=-1;enum {RESTART=2,STOP=1};
int accessResult=0,serviceResult=0,serviceCalls=0,lastAction=-1;
int HostAccess(const char* path,int mode){assert(std::string(path)=="/system/bin/qemu_openvpn_service" && mode==X_OK);return accessResult;}
int ServiceControl(const char* service,int action){assert(std::string(service)=="qemu_openvpn");++serviceCalls;lastAction=action;return serviceResult;}
#define access HostAccess
struct SystemVpnWrapper {
 bool prepared=false,vpnFfrtQueue_=true,isIpSecAccess_=false;int executed=0;
 bool PrepareUpdate(SysVpnStageCode,const std::string&){return prepared;}
 void ExecuteUpdate(SysVpnStageCode,const std::string&){++executed;}
 int32_t Update(SysVpnStageCode,const std::string& = "");
};
'''
        cases = r'''
int main(){
 SystemVpnWrapper wrapper;
#ifdef OHOS_QEMU_OPENVPN
 wrapper.vpnFfrtQueue_=false;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)==0 && serviceCalls==1 && lastAction==RESTART);
 assert(wrapper.executed==0);
 accessResult=-1;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)==-1 && serviceCalls==1);
 serviceResult=-1;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP)==-1 && serviceCalls==2 && lastAction==STOP);
 accessResult=0;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)==-1 && serviceCalls==3);
 serviceResult=0;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP)==0 && serviceCalls==4);
 assert(wrapper.Update(SysVpnStageCode::OTHER)==-1 && serviceCalls==4);
#else
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)==-1 && serviceCalls==0);
 wrapper.isIpSecAccess_=true;
 assert(wrapper.Update(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)==0 && serviceCalls==0 && wrapper.executed==1);
#endif
 wrapper.prepared=true;
 assert(wrapper.Update(SysVpnStageCode::OTHER)==0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged(root)
            apply(root)
            text = (root / BASE / 'services/netmanagernative/src/netsys/system_vpn_wrapper.cpp').read_text()
            actual = body(text, 'int32_t SystemVpnWrapper::Update(')
            for define in ([], ['-DOHOS_QEMU_OPENVPN']):
                compile_run(declarations + actual + cases, root, extra=define)

    def test_parent_death_guard_failure_and_reparent_race(self):
        # Real guard body; explicit syscall doubles make error and race paths
        # executable on macOS, without claiming Linux process semantics here.
        declarations = r'''
#include <cassert>
#include <signal.h>
#include <sys/types.h>
constexpr int PR_SET_PDEATHSIG=1;
int calls=0,syscallResult=0;pid_t parent=22;
int prctl(int operation,int deathSignal,int a,int b,int c){
 ++calls;assert(operation==PR_SET_PDEATHSIG && deathSignal==SIGKILL && !a && !b && !c);return syscallResult;
}
pid_t getppid(){return parent;}
'''
        text = (HEADERS / 'process_lifecycle.h').read_text()
        actual = body(text, 'inline bool BindToParent(')
        cases = r'''
int main(){
 assert(!BindToParent(0) && !BindToParent(1) && calls==0);
 syscallResult=-1;assert(!BindToParent(22) && calls==1);
 syscallResult=0;parent=1;assert(!BindToParent(22) && calls==2);
 parent=22;assert(BindToParent(22) && calls==3);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            compile_run(declarations + actual + cases, Path(temporary))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux parent-death/exec semantics')
    def test_linux_parent_death_kills_real_exec_child(self):
        # The orchestrator has a pipe from the exec child. Killing its parent
        # must produce EOF, even though that child has already exec'd /bin/cat.
        source = r'''
#include "process_lifecycle.h"
#include <cassert>
#include <fcntl.h>
#include <poll.h>
#include <sys/wait.h>
int main(){
 int report[2], hold[2];assert(pipe(report)==0 && pipe(hold)==0);
 pid_t owner=fork();assert(owner>=0);
 if(owner==0){
  close(report[0]);close(hold[1]);pid_t expected=getpid();
  pid_t worker=fork();assert(worker>=0);
  if(worker==0){
   if(!OhosOpenvpn::BindToParent(expected)) _exit(2);
   assert(dup2(hold[0],STDIN_FILENO)==STDIN_FILENO);
   assert(dup2(report[1],STDOUT_FILENO)==STDOUT_FILENO);
   close(hold[0]);close(report[1]);
   execl("/bin/cat","cat",static_cast<char*>(nullptr));_exit(3);
  }
  close(report[1]);close(hold[0]);for(;;) pause();
 }
 close(report[1]);close(hold[0]);
 assert(write(hold[1],"ready",5)==5);
 char buffer[8]{};pollfd ready{report[0],POLLIN,0};
 assert(poll(&ready,1,3000)==1 && read(report[0],buffer,8)==5);
 assert(kill(owner,SIGKILL)==0);assert(waitpid(owner,nullptr,0)==owner);
 ready.revents=0;assert(poll(&ready,1,3000)==1);
 assert(read(report[0],buffer,8)==0);
 close(report[0]);close(hold[1]);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            compile_run(source, Path(temporary))


if __name__ == '__main__':
    unittest.main()
