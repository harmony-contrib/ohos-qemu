"""Compile the actual no-op callback class under the native backend's warnings."""
from pathlib import Path
import base64
import json
import subprocess
import tempfile
import unittest
from test_batch_network_openvpn_lifecycle import ROOT,compile_run
from test_batch_network_vpn_callbacks import prepared as callbacks_prepared

PROJECT='foundation/communication/netmanager_ext'
COMPONENT=ROOT/'patches/common'/PROJECT/'netvpn_callback_unused'
ANCESTORS=Path(__file__).with_name('fixtures')/'batch_network/vpn-callback-ancestor-files.json'
RELATIVE='interfaces/innerkits/netvpnclient/include/networkvpn_client.h'


def prepared(root):
    for name,encoded in json.loads(ANCESTORS.read_text()).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)


class NativeCallbackWarningTests(unittest.TestCase):
    def test_actual_class_preserves_callback_signature_under_werror(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);prepared(root);source=(root/PROJECT/RELATIVE).read_text()
            start=source.index('class VpnSetUpEventCallback :');end=source.index('\n};',start)+3
            declaration=r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <type_traits>
template<class T>using sptr=std::shared_ptr<T>;
constexpr int ERR_OK=0;
struct VpnState {};
struct VpnEventCallbackStub {virtual~VpnEventCallbackStub()=default;virtual int32_t OnVpnStateChanged(bool,const sptr<VpnState>&)=0;virtual int32_t OnMultiVpnStateChanged(bool,const std::string&,const std::string&)=0;virtual int32_t OnVpnMultiUserSetUp()=0;};
'''
            cases=r'''
int32_t VpnSetUpEventCallback::OnVpnMultiUserSetUp(){return ERR_OK;}
static_assert(std::is_same_v<decltype(&VpnSetUpEventCallback::OnVpnStateChanged),int32_t(VpnSetUpEventCallback::*)(bool,const sptr<VpnState>&)>);
static_assert(std::is_same_v<decltype(&VpnSetUpEventCallback::OnMultiVpnStateChanged),int32_t(VpnSetUpEventCallback::*)(bool,const std::string&,const std::string&)>);
int main(){VpnSetUpEventCallback callback;assert(callback.OnVpnStateChanged(true,nullptr)==ERR_OK && callback.OnMultiVpnStateChanged(false,"owner","id")==ERR_OK);}
'''
            original=base64.b64decode(json.loads(ANCESTORS.read_text())[PROJECT+'/'+RELATIVE]).decode()
            old_start=original.index('class VpnSetUpEventCallback :');old_end=original.index('\n};',old_start)+3
            with self.assertRaisesRegex(AssertionError, 'unused parameter'):
                compile_run(declaration+original[old_start:old_end]+cases,root)
            compile_run(declaration+source[start:end]+cases,root)
            subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            p=root/PROJECT/RELATIVE;p.write_bytes(p.read_bytes()+b'// unknown\n')
            self.assertNotEqual(subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],capture_output=True).returncode,0)

    def test_complete_ancestor_callback_stack_and_warnings_are_idempotent(self):
        from test_connected_vpn_nullable import staged
        from test_batch_network_openvpn_session import prepared as session_prepared
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);staged(root);base=ROOT/'patches/common'/PROJECT
            subprocess.run(['bash',str(base/'connected_vpn_nullable/apply.sh'),'--source-root',str(root)],check=True,capture_output=True)
            session_prepared(root);callbacks_prepared(root);prepared(root)
            for name in ['always_on_vpn','connected_vpn_nullable','openvpn_lifecycle','openvpn_session','vpn_callback_dispatch','netvpn_callback_unused']:
                subprocess.run(['bash',str(base/name/'apply.sh'),'--source-root',str(root)],check=True,capture_output=True)


if __name__=='__main__':unittest.main()
