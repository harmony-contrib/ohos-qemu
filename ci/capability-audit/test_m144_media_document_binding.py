"""Exact creation-branch fixtures; not real Mojo or guest acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/web/arkweb/m144_media_document_binding'
PATCH = COMPONENT / '0001-bind-custom-player-factory-to-current-document.patch'


class MediaDocumentBindingTests(unittest.TestCase):
    def test_exact_branch_current_document_rejection_and_injected_factory(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {
            'src/arkweb/chromium_ext/content/renderer/media_interface_factory_for_include.cc'})
        lines = next(iter(sections.values()))[0][2]
        start = lines.index('  if (interface_broker_) {')
        body = '\n'.join(lines[start:])
        source = r'''
#include <cassert>
#include <memory>
#include <utility>
#include <vector>
struct Params { int source; };
struct Request { int document, client, receiver, player, source; };
std::vector<Request> delivered;
struct Endpoint {
  int document=-1; bool rejected=false;
  std::vector<Request> queued;
  void CreateCustomMediaPlayerRenderer(int client,int receiver,int player,const Params& params) {
    queued.push_back({document,client,receiver,player,params.source});
  }
  void Drain() {
    if(!rejected) delivered.insert(delivered.end(),queued.begin(),queued.end());
    queued.clear();
  }
};
namespace media { namespace mojom { using InterfaceFactory=Endpoint; } }
namespace mojo {
template<class T> struct Remote {
  std::shared_ptr<T> endpoint=std::make_shared<T>();
  auto BindNewPipeAndPassReceiver() { return endpoint; }
  T* operator->() { return endpoint.get(); }
  ~Remote() { endpoint->Drain(); }
};
}
struct Broker {
  int document=0,bindings=0; bool rejected=false;
  void GetInterface(std::shared_ptr<Endpoint> endpoint) {
    ++bindings; endpoint->document=document; endpoint->rejected=rejected;
  }
};
struct Factory {
  Broker* interface_broker_=nullptr;
  Endpoint cached; int cached_reads=0;
  Endpoint* GetMediaInterfaceFactory() { ++cached_reads; return &cached; }
  void Create(int client_extension_remote,int receiver,int player_id,const Params& params) {
'''
        main = r'''
  }
};
int main() {
  Broker broker; Factory factory; factory.interface_broker_=&broker;
  // Keep a bound old-document cache: do not deliver its disconnect first.
  factory.cached.document=-1;
  for(int document=0;document<128;++document) {
    broker.document=document;
    factory.Create(document+1,document+2,document+3,Params{document+4});
    assert(delivered.size()==static_cast<unsigned>(document+1));
    auto actual=delivered.back();
    assert(actual.document==document && actual.client==document+1);
    assert(actual.receiver==document+2 && actual.player==document+3 && actual.source==document+4);
    assert(factory.cached_reads==0 && factory.cached.document==-1 && factory.cached.queued.empty());
  }
  assert(broker.bindings==128);
  // A rejected new-document broker must not fall back to the cached factory.
  broker.rejected=true;
  factory.Create(11,12,13,Params{14});
  assert(broker.bindings==129 && delivered.size()==128 && factory.cached_reads==0);
  // The explicitly injected no-broker constructor preserves its original path.
  Factory injected; injected.cached.document=55;
  injected.Create(31,32,33,Params{34});
  assert(injected.cached_reads==1 && injected.cached.queued.size()==1);
  injected.cached.Drain(); auto actual=delivered.back();
  assert(actual.document==55 && actual.client==31 && actual.receiver==32 && actual.player==33 && actual.source==34);
}
'''
        compile_run(source + body + main, language='c++')

    def test_idempotent_component_and_native_hap_source_context_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, PATCH)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(source)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            subprocess.run(['git', '-C', str(source), 'apply', '--check', '--reverse', str(PATCH)], check=True)
        bootstrap = (ROOT / 'patches/common/web/arkweb/m144_window_contract/apply_with_core_build.sh').read_text()
        self.assertIn('m144_media_document_binding/apply.sh', bootstrap)
        self.assertIn('m144_media_document_binding',
                      (ROOT / 'scripts/package_m144_arkweb_core_in_docker.sh').read_text())
        self.assertIn('m144_media_document_binding',
                      (ROOT / 'ci/capability-audit/check_m144_release_patch_baseline.py').read_text())


if __name__ == '__main__':
    unittest.main()
