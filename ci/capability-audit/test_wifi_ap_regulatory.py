"""Candidate guard/callback tests; not Wi-Fi identity, AP or regulatory acceptance."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/software_ap_regulatory'
PATCH = COMPONENT / '0001-apply-and-read-back-kernel-regulatory-domain.patch'


def added_header():
    section = PATCH.read_text().split('new file mode 100644\n', 1)[1]
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line.startswith('+') and not line.startswith('+++')) + '\n'


class WifiApRegulatoryTests(unittest.TestCase):
    def test_libnl_external_dependency_is_a_component_not_third_party_metadata(self):
        # The real OHOS external-deps checker consults deps.components only.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'foundation/communication/wifi/wifi/bundle.json'
            target.parent.mkdir(parents=True)
            value = {'component': {'deps': {'components': [
                'image_framework', 'init', 'ipc', 'napi', 'netmanager_base', 'netmanager_ext', 'netstack'],
                'third_party': ['googletest', 'wpa_supplicant']}}}
            target.write_text(json.dumps(value, indent=4))
            subprocess.run(['git', '-C', directory, 'apply',
                '--include=foundation/communication/wifi/wifi/bundle.json', str(PATCH)],
                capture_output=True, text=True, check=True)
            deps = json.loads(target.read_text())['component']['deps']
            self.assertEqual(deps['components'].count('libnl'), 1)
            self.assertNotIn('libnl', deps['third_party'])

    def test_only_software_wpa_branch_gains_backend_and_dependency(self):
        patch = PATCH.read_text()
        self.assertIn('+    } else if (wifi_feature_with_hdi_wpa_supported) {', patch)
        self.assertIn('+      external_deps += [ "libnl:libnl_share" ]', patch)
        self.assertIn('+#elif defined(WIFI_SOFTWARE_AP_REGULATORY_BACKEND)', patch)
        self.assertIn('SetAndReadBack(ifaceName, code) ? WIFI_HAL_OPT_OK : WIFI_HAL_OPT_FAILED', patch)
        self.assertNotIn('wifi_standard.cfg', patch)
        self.assertNotIn('CAP_NET_ADMIN', patch)

    def test_real_request_ack_readback_and_bounded_fail_closed_paths(self):
        header = added_header()
        for required in ('NL80211_CMD_REQ_SET_REG', 'NL80211_CMD_GET_REG',
                         'nl_send_auto_complete', 'nl_recvmsgs_default',
                         'SO_RCVTIMEO', 'SO_SNDTIMEO', 'std::chrono::steady_clock',
                         'if_nametoindex(interface.c_str()) == 0',
                         'return reply.ack && !reply.failed && (!query || reply.valid)',
                         'if (reply.alpha2 == country)', 'nl_socket_free(socket)'):
            self.assertIn(required, header)
        for forbidden in ('system(', 'popen(', 'nl_socket_disable_seq_check', 'NLM_F_DUMP'):
            self.assertNotIn(forbidden, header)

    def test_compiled_actual_guards_and_callbacks_reject_malformed_or_foreign_replies(self):
        # Libnl structures/accessors below are test doubles. Compile the actual
        # added callback bodies, not a reimplemented parser or acceptance result.
        header = added_header()
        callbacks = header[header.index('struct Reply {'):header.index('inline bool Exchange(')]
        harness = r'''#include <cassert>
#include <string>
constexpr int NL_STOP=2, NL_OK=0, AF_NETLINK=16;
constexpr int NL80211_ATTR_MAX=4, NL80211_ATTR_REG_ALPHA2=2, NL80211_CMD_GET_REG=34;
struct sockaddr_nl { int nl_family=AF_NETLINK; int nl_pid=0; };
struct nlmsgerr {};
struct genlmsghdr { int cmd=NL80211_CMD_GET_REG; };
struct nlattr { int size=3; char value[4]={'H','K',0,0}; };
struct nlmsghdr { bool valid=true, parsed=true, hasAlpha=true; genlmsghdr generic; nlattr alpha; };
struct nl_msg { sockaddr_nl source; bool hasSource=true; nlmsghdr header; };
sockaddr_nl *nlmsg_get_src(nl_msg *m) { return m->hasSource ? &m->source : nullptr; }
nlmsghdr *nlmsg_hdr(nl_msg *m) { return &m->header; }
bool genlmsg_valid_hdr(nlmsghdr *h, int) { return h->valid; }
int genlmsg_parse(nlmsghdr *h, int, nlattr **a, int, void *) {
    if (!h->parsed) return -1;
    a[NL80211_ATTR_REG_ALPHA2] = h->hasAlpha ? &h->alpha : nullptr;
    return 0;
}
void *nlmsg_data(nlmsghdr *h) { return &h->generic; }
int nla_len(const nlattr *a) { return a->size; }
const void *nla_data(const nlattr *a) { return a->value; }
''' + callbacks + r'''
int main() {
    assert(ValidCountry("HK") && ValidCountry("US"));
    for (const std::string value : {"", "H", "HKK", "hk", "0H", "H0", "00", "HK\n"})
        assert(!ValidCountry(value));
    assert(!ValidCountry(std::string("H\0", 2)));
    nl_msg good;
    Reply reply;
    assert(KernelOnly(&good, &reply) == NL_OK && !reply.failed);
    assert(RegulatoryReply(&good, &reply) == NL_OK && reply.valid && reply.alpha2 == "HK");
    assert(!reply.ack);
    assert(Ack(&good, &reply) == NL_STOP && reply.ack);
    for (int mutation=0; mutation<6; ++mutation) {
        nl_msg bad;
        Reply invalid;
        if (mutation==0) bad.header.valid=false;
        if (mutation==1) bad.header.parsed=false;
        if (mutation==2) bad.header.hasAlpha=false;
        if (mutation==3) bad.header.generic.cmd=99;
        if (mutation==4) bad.header.alpha.size=2;
        if (mutation==5) bad.header.alpha.value[2]='X';
        assert(RegulatoryReply(&bad, &invalid) == NL_STOP && invalid.failed && !invalid.valid);
    }
    for (int mutation=0; mutation<3; ++mutation) {
        nl_msg bad;
        Reply invalid;
        if (mutation==0) bad.hasSource=false;
        if (mutation==1) bad.source.nl_pid=123;
        if (mutation==2) bad.source.nl_family=2;
        assert(KernelOnly(&bad, &invalid) == NL_STOP && invalid.failed);
    }
    Reply failure;
    assert(Error(nullptr, nullptr, &failure) == NL_STOP && failure.failed && !failure.ack);
}
'''
        with tempfile.TemporaryDirectory(prefix='wifi-ap-regulatory-callbacks-') as directory:
            source = Path(directory) / 'callbacks.cpp'
            binary = Path(directory) / 'callbacks'
            source.write_text(harness)
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_shared_local_recipe_and_exact_source_state_guard(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${QEMU_SOFTWARE_AP_REGULATORY_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertIn('software_ap_regulatory/apply.sh', recipe)
        self.assertIn('apply_exact_component.py', (COMPONENT / 'apply.sh').read_text())
        baseline = (COMPONENT / 'verify_source.py').read_text()
        self.assertIn('367605c52dfaf5f09bd690f16d9ee9a301cfc98a', baseline)
        self.assertIn('validate_component(root, PROJECT, REVISION, FILES, require_patched)', baseline)


if __name__ == '__main__':
    unittest.main()
