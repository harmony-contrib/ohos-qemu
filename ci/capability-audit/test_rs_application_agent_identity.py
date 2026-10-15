"""Actual full registration branch with Binder doubles; never guest acceptance."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_2d/application_agent_identity'
PARENT = COMPONENT.with_name('async_caller_identity')


def load(directory, name):
    spec = importlib.util.spec_from_file_location(name, directory / 'verify_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = load(COMPONENT, 'rs_agent_identity_baseline')
PRIOR = load(PARENT, 'rs_agent_prior_identity_baseline')

DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
using pid_t = int;
template<class T> using sptr = std::shared_ptr<T>;
struct Remote { bool valid = true; };
struct IApplicationAgent {};
template<class T> sptr<T> iface_cast(const sptr<Remote>& object) {
 return object->valid ? std::make_shared<T>() : nullptr;
}
enum class RSIClientToRenderConnectionInterfaceCode : uint32_t { REGISTER_APPLICATION_AGENT = 7 };
struct MessageOption {
 static constexpr uint32_t TF_ASYNC = 1; uint32_t flags;
 uint32_t GetFlags() const { return flags; }
};
struct Parcel {
 int forgedPid = 1, reads = 0; sptr<Remote> remote;
 sptr<Remote> ReadRemoteObject() { ++reads; return remote; }
};
[[maybe_unused]] constexpr int ERR_NONE = 0, ERR_INVALID_STATE = -7, ERR_NULL_OBJECT = -8;
static int wirePid, trustedPid, realReads, registrations, lastPid;
static std::map<int, sptr<IApplicationAgent>> agents;
static int GetCallingPid() { return wirePid; }
struct IPCSkeleton { static int GetCallingRealPid() { ++realReads; return trustedPid; } };
static void RegisterApplicationAgent(int pid, sptr<IApplicationAgent> agent) {
 assert(agent); ++registrations; lastPid = pid; agents[pid] = agent;
}
#define RS_PROFILER_PATCH_PID(data,pid) ((void)0)
'''


class ApplicationAgentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = gzip.decompress(base64.b64decode((ROOT / 'ci/capability-audit/fixtures/rs_async_parent_prepared.json.gz.b64').read_bytes()))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '2399d493af1667763a38baee0df0056b76acda34fcfca04041283795d38381f7')
        fixture = json.loads(raw)
        self.assertEqual(set(fixture), {entry[0] for entry in PRIOR.FILES})
        for relative, _, final in PRIOR.FILES:
            data = base64.b64decode(fixture[relative])
            self.assertEqual(hashlib.sha256(data).hexdigest(), final)
            target = self.root / PRIOR.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.assertTrue(PRIOR.validate(self.root, require_patched=True))
        self.target = self.root / BASELINE.PROJECT / BASELINE.FILES[0][0]

    def apply(self, component=COMPONENT):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def branch(self):
        source = self.target.read_text()
        match = re.search(r'        case static_cast<uint32_t>\(RSIClientToRenderConnectionInterfaceCode::REGISTER_APPLICATION_AGENT\): \{[\s\S]*?^        }', source, re.M)
        self.assertIsNotNone(match)
        return 'int dispatch(MessageOption option, Parcel& data) { int ret=ERR_NONE; switch (7u) {\n' + match.group() + '\n} return ret; }\n'

    def test_original_oneway_agent_cannot_receive_real_owner_notification(self):
        compile_run(DOUBLES + self.branch() + r'''
int main() { wirePid=0; trustedPid=231; Parcel data; data.remote=std::make_shared<Remote>();
 assert(dispatch({1},data)==ERR_NONE); assert(registrations==1&&lastPid==0&&realReads==0);
 assert(agents.count(0)==1&&agents.count(231)==0); }
''', language='c++')

    def test_real_registration_branch_identity_boundaries_and_distinct_owners(self):
        self.assertEqual(self.apply().returncode, 0)
        compile_run(DOUBLES + self.branch() + r'''
int main() {
 for(int wire:{-1,0,1,37,9999}) for(int trusted:{-1,0,1,118,231})
  for(unsigned flags=0;flags<8;++flags) for(int remote=0;remote<3;++remote) {
   wirePid=wire; trustedPid=trusted; realReads=registrations=0; lastPid=-99; agents.clear();
   Parcel data; data.forgedPid=999999;
   if(remote) { data.remote=std::make_shared<Remote>(); data.remote->valid=remote==1; }
   bool fallback=wire==0&&(flags&1); int expectedPid=fallback?trusted:wire;
   int result=dispatch({flags},data);
   assert(realReads==int(fallback));
   if(expectedPid<=0) { assert(result==ERR_INVALID_STATE&&registrations==0&&data.reads==0); }
   else if(remote!=1) { assert(result==ERR_NULL_OBJECT&&registrations==0&&data.reads==1); }
   else { assert(result==ERR_NONE&&registrations==1&&lastPid==expectedPid&&data.reads==1);
    assert(agents.count(expectedPid)==1&&agents.count(data.forgedPid)==0); }
  }
 agents.clear(); wirePid=0; Parcel data; data.remote=std::make_shared<Remote>();
 trustedPid=118; assert(dispatch({1},data)==ERR_NONE);
 trustedPid=231; assert(dispatch({1},data)==ERR_NONE);
 assert(agents.size()==2&&agents.count(118)&&agents.count(231));
}
''', language='c++')

    def test_parent_replay_preserves_exact_successor_and_rejects_mixed_stack(self):
        self.assertEqual(self.apply().returncode, 0)
        expected = {entry[0]: (self.root / PRIOR.PROJECT / entry[0]).read_bytes() for entry in PRIOR.FILES}
        for _ in range(2):
            self.assertEqual(self.apply(PARENT).returncode, 0)
            self.assertEqual(self.apply().returncode, 0)
            self.assertEqual(expected, {name: (self.root / PRIOR.PROJECT / name).read_bytes() for name in expected})
        other = self.root / PRIOR.PROJECT / PRIOR.HEADER
        other.write_bytes(b'foreign partial parent header\n')
        before = self.target.read_bytes()
        self.assertNotEqual(self.apply(PARENT).returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)

    def test_child_rejects_unknown_and_symlink_without_mutating_target(self):
        self.target.write_bytes(self.target.read_bytes() + b'foreign\n')
        before = self.target.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)
        self.target.unlink()
        outside = self.root / 'outside.cpp'; outside.write_bytes(before)
        self.target.symlink_to(outside)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(outside.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
