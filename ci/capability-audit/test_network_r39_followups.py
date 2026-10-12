"""Exact prepared-source and actual OpenVPN copy branch tests, not guest proof."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'patches/common/foundation/communication/netmanager_ext'
FIXTURES = Path(__file__).parent / 'fixtures'


def baseline(name):
    spec = importlib.util.spec_from_file_location('network_followup_' + name, BASE / name / 'verify_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def staged(root, name):
    module = baseline(name)
    path = root / module.PROJECT / module.FILES[0][0]
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / (name + '_prepared.cpp'), path)
    return module, path


class NetworkFollowupTests(unittest.TestCase):
    def test_real_prepared_sources_apply_twice_and_preserve_other_content(self):
        for name in ('ethernet_business_error', 'vpn_openvpn_fields'):
            with self.subTest(component=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                module, path = staged(root, name)
                self.assertFalse(module.validate(root))
                for _ in range(2):
                    subprocess.run(['bash', str(BASE / name / 'apply.sh'), '--source-root', str(root)],
                                   check=True, capture_output=True)
                    self.assertTrue(module.validate(root, True))
                content = path.read_text()
                if name == 'ethernet_business_error':
                    self.assertIn('napi_throw_business_error(env, napiCode, errMsg.c_str());', content)
                    self.assertNotIn('napiCodeStr', content)
                    self.assertIn('EthernetExec::MapToNapiErrorCode(result)', content)
                else:
                    self.assertEqual(content.count('openvpnConfig->forwardingRoutes_ = vpnBean->forwardingRoutes_;'), 1)
                    self.assertIn('VpnNetworkStorage::Restore(vpnBean->networkConfig_', content)

    def test_unknown_and_linked_input_refuse_before_modifying_source(self):
        for name in ('ethernet_business_error', 'vpn_openvpn_fields'):
            with self.subTest(component=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, path = staged(root, name)
                unknown = path.read_bytes() + b'// unknown caller edit\n'
                path.write_bytes(unknown)
                child = subprocess.run(['bash', str(BASE / name / 'apply.sh'), '--source-root', str(root)],
                                       capture_output=True)
                self.assertNotEqual(child.returncode, 0)
                self.assertEqual(path.read_bytes(), unknown)
                saved = root / 'linked.cpp'
                saved.write_bytes(unknown)
                path.unlink()
                path.symlink_to(saved)
                child = subprocess.run(['bash', str(BASE / name / 'apply.sh'), '--source-root', str(root)],
                                       capture_output=True)
                self.assertNotEqual(child.returncode, 0)
                self.assertTrue(path.is_symlink())
                self.assertEqual(saved.read_bytes(), unknown)

    def test_parent_accepts_only_exact_complete_followup_not_unknown_or_partial(self):
        parent = baseline('vpn_config_store')
        with patch.object(parent, 'validate_component', side_effect=[ValueError('old state differs'), True]) as check:
            self.assertTrue(parent.validate(Path('/explicit-fixture'), True))
            args = check.call_args_list[1].args
            self.assertTrue(args[-1])
            updated = args[3]
            self.assertEqual(len(updated), len(parent.FILES))
            changed = [row for row, old in zip(updated, parent.FILES) if row != old]
            self.assertEqual(changed, [('frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
                'cd88f49e024b904fefd934af5f86dced4f4e28060bf67d82afd5f62b44107f16',
                '11a8895cfc7d8c4ea546e8044c1ba2dd2763dce04abbff524736c02c4ea7ef67')])
        with patch.object(parent, 'validate_component', side_effect=[ValueError('preserve unknown'), ValueError('partial')]):
            with self.assertRaisesRegex(ValueError, 'preserve unknown'):
                parent.validate(Path('/explicit-fixture'))

    def test_original_OpenVPN_omission_and_exact_fixed_branch_with_sanitizers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, path = staged(root, 'vpn_openvpn_fields')
            before = path.read_text()
            subprocess.run(['bash', str(BASE / 'vpn_openvpn_fields/apply.sh'), '--source-root', str(root)],
                           check=True, capture_output=True)
            after = path.read_text()
        start = 'sptr<OpenvpnConfig> VpnDataBean::ConvertVpnBeanToOpenvpnConfig'
        end = '\nsptr<IpsecVpnConfig>'
        bodies = [text[text.index(start):text.index(end, text.index(start))] for text in (before, after)]
        names = sorted(set(re.findall(r'vpnBean->(\w+)', bodies[1])))
        integers = {'vpnType_', 'isLegacy_', 'saveLogin_', 'ovpnProtocol_', 'ovpnAuthType_', 'userId_'}
        strings = [name for name in names if name not in integers]
        # Smart pointer and network restoration are explicit host doubles;
        # execute the complete actual old/new copy body, not IPC/DB/storage.
        code = '''#include <cassert>
#include <memory>
#include <new>
#include <string>
#include <vector>
#define NETMGR_EXT_LOG_E(...) ((void)0)
template<class T> struct sptr {
 std::shared_ptr<T> value;
 sptr(std::nullptr_t=nullptr) {}
 sptr(T *p):value(p) {}
 T *operator->() const {return value.get();}
 T &operator*() const {return *value;}
 bool operator==(std::nullptr_t) const {return !value;}
};
struct Fields {
''' + ''.join(' std::string ' + name + ';\n' for name in strings) + ''.join(
            ' int ' + name + ' = 0;\n' for name in sorted(integers)) + '''};
struct VpnDataBean: Fields {};
struct OpenvpnConfig: Fields {std::vector<std::string> remoteAddresses_;};
struct VpnNetworkStorage {
 static bool Restore(const std::string &s, OpenvpnConfig &) {return s=="actual-host-double";}
};
''' + bodies[0].replace('VpnDataBean::ConvertVpnBeanToOpenvpnConfig', 'Legacy') + bodies[1].replace(
            'VpnDataBean::ConvertVpnBeanToOpenvpnConfig', 'Fixed') + '''int main() {
 sptr<VpnDataBean> bean = new VpnDataBean();
 bean->networkConfig_="actual-host-double";
 bean->forwardingRoutes_="198.18.0.0/24";
 bean->remoteAddr_="203.0.113.1";
 bean->saveLogin_=1; bean->isLegacy_=1;
 auto old=Legacy(bean); auto next=Fixed(bean);
 assert(!(old==nullptr) && !(next==nullptr));
 assert(old->forwardingRoutes_.empty());
 assert(next->forwardingRoutes_==bean->forwardingRoutes_);
 assert(next->remoteAddresses_==old->remoteAddresses_ && next->remoteAddresses_.size()==1);
 assert(next->saveLogin_==1 && next->isLegacy_==1);
''' + ''.join(' assert(next->' + name + '==old->' + name + ');\n' for name in names
              if name not in ('forwardingRoutes_', 'remoteAddr_', 'networkConfig_')) + '''
 bean->forwardingRoutes_="2001:db8::/64";
 assert(next->forwardingRoutes_=="198.18.0.0/24");
 assert(Fixed(bean)->forwardingRoutes_=="2001:db8::/64");
 assert(Fixed(nullptr)==nullptr);
 bean->networkConfig_="invalid-host-double";
 assert(Fixed(bean)==nullptr);
}
'''
        compiler = shutil.which('clang++')
        if compiler is None: self.skipTest('clang++ required for actual conversion branch sanitizers')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate, binary = root / 'openvpn-copy.cpp', root / 'openvpn-copy'
            candidate.write_text(code)
            compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(candidate), '-o', str(binary)], capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode(errors='replace'))
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_both_followups_run_after_prerequisites_before_traversal(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = builder.index('  write_source_preparation_metadata')
        for prior, name in (('ETHERNET_API26_COMPONENT_SCRIPT', 'ETHERNET_BUSINESS_ERROR_COMPONENT_SCRIPT'),
                            ('VPN_CONFIG_STORE_COMPONENT_SCRIPT', 'VPN_OPENVPN_FIELDS_COMPONENT_SCRIPT')):
            self.assertLess(builder.index('bash "${' + prior + '}"'), builder.index('bash "${' + name + '}"'))
            self.assertLess(builder.index('bash "${' + name + '}"'), marker)

    def test_TU_checker_preserves_quoted_headers_and_requires_actual_feature(self):
        checker = (ROOT / 'ci/capability-audit/compile_network_r39_followups.py').read_text()
        self.assertIn('overlay_component_headers=True', checker)
        self.assertIn("else 'SUPPORT_SYSVPN'", checker)
        self.assertNotIn('candidate_defines=', checker)
        self.assertIn("result.update(status='fail', error=", checker)
        self.assertIn("finally:\n        args.output.write_text", checker)


if __name__ == '__main__':
    unittest.main()
