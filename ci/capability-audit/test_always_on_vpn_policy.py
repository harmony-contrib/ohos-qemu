"""Actual new service entrypoints with explicit caller/storage doubles."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/always_on_vpn'


class AlwaysOnVpnPolicyTests(unittest.TestCase):
    def test_permission_precedes_parameters_and_all_storage_access(self):
        sections = patch_sections(COMPONENT / '0001-connect-always-on-policy-through-permission-checked-ipc.patch')
        hunks = next(value for name, value in sections.items() if name.endswith('/src/networkvpn_service.cpp'))
        body = '\n'.join(hunks[0][2]).split('int32_t NetworkVpnService::SetAlwaysOnVpn(')[0]
        source = r'''
#include <cassert>
#include <cstdint>
#include <mutex>
#include <string>
constexpr int NETMANAGER_SUCCESS=0,NETMANAGER_EXT_SUCCESS=0,NETMANAGER_EXT_ERR_PARAMETER_ERROR=401;
namespace Permission {constexpr const char* MANAGE_VPN="ohos.permission.MANAGE_VPN";}
int permission=0,reads=0,writes=0,readError=0,writeError=0,permissionChecks=0;
std::string stored;
struct NetworkVpnService {
    std::mutex alwaysOnPolicyMutex_;
    int32_t CheckIpcPermission(const std::string& name){assert(name==Permission::MANAGE_VPN);++permissionChecks;return permission;}
    int32_t GetAlwaysOnVpn(std::string& package){++reads;package=stored;return readError;}
    int32_t SetAlwaysOnVpn(std::string& package,bool& enabled){
        ++writes;if(writeError)return writeError;stored=enabled?package:"";return 0;
    }
    int32_t SetAlwaysOnVpnEnabled(bool,const std::string&);
    int32_t IsAlwaysOnVpnEnabled(const std::string&,bool&);
};
'''
        main = r'''
int main(){
    NetworkVpnService service;
    for(int denial:{201,202}) for(const std::string &bundle:{std::string(),std::string("com.example.vpn")}) {
        permission=denial;reads=writes=0;bool enabled=true;
        assert(service.SetAlwaysOnVpnEnabled(true,bundle)==denial);
        assert(service.IsAlwaysOnVpnEnabled(bundle,enabled)==denial && !enabled);
        assert(reads==0 && writes==0);
    }
    permission=0;
    for(const std::string &bundle:{std::string(),std::string("com.example\0hidden",18)}){
        reads=writes=0;bool enabled=true;
        assert(service.SetAlwaysOnVpnEnabled(true,bundle)==401);
        assert(service.IsAlwaysOnVpnEnabled(bundle,enabled)==401 && !enabled);
        assert(reads==0 && writes==0);
    }
    bool enabled=true;stored.clear();
    assert(service.IsAlwaysOnVpnEnabled("com.example.vpn",enabled)==0 && !enabled);
    assert(service.SetAlwaysOnVpnEnabled(true,"com.example.vpn")==0);
    assert(service.IsAlwaysOnVpnEnabled("com.example.vpn",enabled)==0 && enabled);
    assert(service.IsAlwaysOnVpnEnabled("com.other.vpn",enabled)==0 && !enabled);
    readError=-1;enabled=true;
    assert(service.IsAlwaysOnVpnEnabled("com.example.vpn",enabled)==-1 && !enabled);
    readError=0;writeError=-1;
    assert(service.SetAlwaysOnVpnEnabled(false,"com.example.vpn")==-1 && stored=="com.example.vpn");
    writeError=0;
    assert(service.SetAlwaysOnVpnEnabled(false,"com.example.vpn")==0 && stored.empty());
    assert(permissionChecks==19);
}
'''
        compile_run(source + body + main, language='c++')

    def test_ipc_numbers_append_and_activation_runs_after_policy_unlock(self):
        text = (COMPONENT / '0001-connect-always-on-policy-through-permission-checked-ipc.patch').read_text()
        sections = patch_sections(COMPONENT / '0001-connect-always-on-policy-through-permission-checked-ipc.patch')
        idl = next(value for name, value in sections.items() if name.endswith('.idl'))[0][2]
        self.assertIn('GetVpnConfigToAnco', idl[0])
        self.assertIn('SetAlwaysOnVpnEnabled', idl[1])
        self.assertIn('IsAlwaysOnVpnEnabled', idl[2])
        self.assertIn('+    lock.unlock();', text)
        self.assertIn('persisted != (enable ? pkg : "")', text)
        self.assertIn('QueryOptional', text)

    def test_shared_recipe_applies_dependencies_before_exact_vpn_baseline(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        positions = []
        for variable in ('NETMANAGER_API26_FEATURES_SCRIPT', 'VPN_DIALOG_BUNDLE_COMPONENT_SCRIPT',
                         'OPTIONAL_SETTINGS_READ_COMPONENT_SCRIPT', 'ALWAYS_ON_VPN_COMPONENT_SCRIPT'):
            invocation = 'bash "${' + variable + '}" --source-root "${OHOS_ROOT}"'
            self.assertEqual(recipe.count(invocation), 1)
            positions.append(recipe.index(invocation))
        self.assertEqual(positions, sorted(positions))


if __name__ == '__main__':
    unittest.main()
