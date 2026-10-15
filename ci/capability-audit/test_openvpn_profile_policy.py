"""Compile the actual supervisor policy and reject execution/ownership escapes."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADERS = ROOT / 'patches/common/foundation/communication/netmanager_ext/openvpn_backend/files'


class OpenvpnProfilePolicyTests(unittest.TestCase):
    def test_actual_policy_with_sanitizers(self):
        source = r'''
#include "profile_policy.h"
#include <cassert>
#include <string>
using OhosOpenvpn::ValidateProfile;
int main() {
 const std::string valid = "client\r\ndev tun\nproto udp\nremote vpn.example 1194\n"
   "remote-cert-tls server\n<ca>\nactual-certificate-data\n</ca>\n"
   "<cert>\ncertificate\n</cert>\n<key>\nprivate-key\n</key>\n";
 assert(ValidateProfile(valid));
 assert(ValidateProfile("# comment\n; comment\n\tclient\n--dev tun\n"));
 assert(ValidateProfile("<connection>\nremote one.example 1194\nproto udp6\n</connection>\n"));
 assert(ValidateProfile("ca [inline]\n<ca>\ncertificate\n</ca>\n"));
 assert(ValidateProfile("<auth-user-pass>\nname\npassword\n</auth-user-pass>\n"));
 for (const char *escape : {
   "daemon", "--daemon", "\"daemon\"", "d\\aemon", "user root", "group root",
   "config /private/other.conf", "cd /private", "chroot /", "up /tmp/script",
   "down /tmp/script", "route-up /tmp/script", "route-pre-down /tmp/script",
   "ipchange /tmp/script", "tls-verify /tmp/script", "plugin /tmp/plugin.so",
   "management /tmp/foreign unix", "management-client", "management-hold",
   "dev-node unix:/tmp/foreign", "setenv OHOS_OPENVPN_READY_SOCKET /tmp/foreign",
   "script-security 3", "writepid /tmp/file", "log /tmp/file", "log-append /tmp/file",
   "status /tmp/file", "replay-persist /tmp/file", "tls-export-cert /tmp/dir",
   "auth-user-pass /private/other", "ca /private/other", "askpass /private/other",
   "engine dynamic", "pkcs11-providers /tmp/plugin.so", "dev tap", "dev-type tap",
   "<connection>\ndaemon\n</connection>", "<connection>\n<connection>\n</connection>\n</connection>",
   "</connection>", "<key>\nunclosed", "<ca>\ncert\n</ca>\ndaemon",
 }) assert(!ValidateProfile(valid + escape + "\n"));
 assert(!ValidateProfile(std::string("client\n\0daemon\n", 15)));
 assert(!ValidateProfile("client\n\001remote host\n"));
 assert(!ValidateProfile(std::string(1024 * 1024 + 1, '#')));
 assert(!ValidateProfile(""));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cpp, binary = directory / 'probe.cpp', directory / 'probe'
            cpp.write_text(source)
            subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(HEADERS),
                str(cpp), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
