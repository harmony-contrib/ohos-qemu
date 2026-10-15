"""Real method boundaries with node doubles and captured native failure; never guest acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run
from verify_lazy_layouts_results import verify
from verify_lazy_layouts_evidence import verify_evidence

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/arkui/ace_engine/lazy_dynamic_algorithm_update'
FIXTURE=Path(__file__).parent/'fixtures/lazy_algorithm_update_diagnostic'
spec=importlib.util.spec_from_file_location('lazy_algorithm_baseline',COMPONENT/'verify_source.py')
BASELINE=importlib.util.module_from_spec(spec);spec.loader.exec_module(BASELINE)

DOUBLES=r'''
#include <cassert>
#include <functional>
#include <memory>
#include <utility>
#include <vector>
template<class T> using RefPtr=std::shared_ptr<T>;
enum class Axis { VERTICAL=0, HORIZONTAL=1 };
using OnVisibleIndexesChangeEvent=std::function<void(const std::vector<int>&)>;
struct LazyCustomLayoutAlgorithmParam {
 Axis axis=Axis::VERTICAL; OnVisibleIndexesChangeEvent callback;
 Axis GetAxis() const { return axis; }
 bool HasOnVisibleIndexesChange() const { return bool(callback); }
 const OnVisibleIndexesChangeEvent& GetOnVisibleIndexesChange() const { return callback; }
 void SetOnVisibleIndexesChange(OnVisibleIndexesChangeEvent&& value) { callback=std::move(value); }
};
struct FrameNode;
struct Pattern { virtual ~Pattern()=default; };
struct LazyDynamicLayoutPattern:Pattern {
 RefPtr<LazyCustomLayoutAlgorithmParam> customParams_; Axis axis_=Axis::VERTICAL;
 std::weak_ptr<FrameNode> host; int validations=0;
 explicit LazyDynamicLayoutPattern(const RefPtr<LazyCustomLayoutAlgorithmParam>& param):customParams_(param) {
  if(param)axis_=param->GetAxis();
 }
 RefPtr<FrameNode> GetHost() { return host.lock(); }
 void OnAttachToMainTree() { ++validations; }
 void UpdateCustomLayoutAlgorithmParam(const RefPtr<LazyCustomLayoutAlgorithmParam>& param);
};
struct FrameNode:std::enable_shared_from_this<FrameNode> {
 RefPtr<Pattern> pattern; bool mounted=true; int replacements=0,dirty=0;
 template<class T> RefPtr<T> GetPattern() { return std::dynamic_pointer_cast<T>(pattern); }
 bool IsOnMainTree() const { return mounted; }
 void ReplacePattern(const RefPtr<Pattern>& next) { ++replacements;pattern=next; }
 void MarkDirtyNode(int) { ++dirty; }
};
struct DynamicLayoutNode {
 static RefPtr<FrameNode> node;
 static std::pair<RefPtr<FrameNode>,bool> GetOrCreateDynamicLayoutNode(
   const char*,int,const std::function<RefPtr<Pattern>()>& factory) {
  if(node)return {node,false};node=std::make_shared<FrameNode>();node->pattern=factory();
  node->GetPattern<LazyDynamicLayoutPattern>()->host=node;return {node,true};
 }
};
RefPtr<FrameNode> DynamicLayoutNode::node;
struct ViewStackProcessor {
 static ViewStackProcessor* GetInstance() { static ViewStackProcessor stack;return &stack; }
 int ClaimNodeId() { return 1; }
 void Push(const RefPtr<FrameNode>&) {}
};
struct AceType {
 template<class T,class... Args> static RefPtr<T> MakeRefPtr(Args&&... args) {
  return std::make_shared<T>(std::forward<Args>(args)...);
 }
};
struct LazyDynamicLayoutModelNG {
 void Create(const RefPtr<LazyCustomLayoutAlgorithmParam>& customParams);
 static void UpdatePropertyFromCustomParam(const RefPtr<FrameNode>& frameNode,
   const RefPtr<LazyCustomLayoutAlgorithmParam>& customParams);
};
#define CHECK_NULL_VOID(value) do { if(!(value))return; } while(0)
#define ACE_LAYOUT_SCOPED_TRACE(...) ((void)0)
constexpr int PROPERTY_UPDATE_MEASURE=1;
'''


def method(text,name):
    start=text.index('void '+name+'(');body=text.index('{',start);depth=0
    for index in range(body,len(text)):
        if text[index]=='{':depth+=1
        elif text[index]=='}':
            depth-=1
            if depth==0:return text[start:index+1]+'\n'
    raise ValueError('complete real native method required')


class LazyAlgorithmUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.fixture=json.loads((FIXTURE/'fixture.json').read_text())
        for name,sha in self.fixture['files_sha256'].items():self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),sha)
        for relative,original,_ in BASELINE.FILES:
            data=(FIXTURE/Path(relative).name).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),original)
            target=self.root/BASELINE.PROJECT/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)

    def methods(self):
        model=(self.root/BASELINE.PROJECT/BASELINE.FILES[0][0]).read_text()
        pattern=(self.root/BASELINE.PROJECT/BASELINE.FILES[1][0]).read_text()
        return (method(model,'LazyDynamicLayoutModelNG::UpdatePropertyFromCustomParam')+
            method(model,'LazyDynamicLayoutModelNG::Create')+method(pattern,'LazyDynamicLayoutPattern::UpdateCustomLayoutAlgorithmParam'))

    def test_captured_real_scroll_helper_failure_cannot_close_five_types(self):
        with self.assertRaisesRegex(ValueError,'real dynamic top callback missing'):
            verify((FIXTURE/'native-results.log').read_text(),self.fixture['nonce'],self.fixture['uid'])
        self.assertFalse(self.fixture['first_artifact_behavior_gate_passed'])

    def test_compilation_only_or_partial_callback_success_cannot_register_five_contracts(self):
        for scope in ('compiled_only','waterflow_only','old_R44_diagnostic'):
            with self.subTest(scope=scope),self.assertRaisesRegex(ValueError,'exact packaged guest'):
                verify_evidence(dict(status='pass',scope=scope),'a'*64,'foreign','arm64','phone','foreign')

    def test_ledger_rejects_diagnostic_assisted_and_foreign_acceptance_scope(self):
        from verify_gap_closure import behavior_results
        for change in ('diagnostic','assisted','foreign'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'boot').mkdir();(root/'lazy-layouts').mkdir()
                archive='a'*64;boot_id='11111111-1111-1111-1111-111111111111'
                (root/'lazy-layouts/evidence.json').write_text(json.dumps(dict(status='pass',archive_sha256=archive,boot_id=boot_id)))
                boot=dict(status='pass',purpose='acceptance',scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                    archive_sha256=archive,test_environment=dict(boot_id=boot_id,external_keepalive=False,device_type='phone'))
                if change=='diagnostic':boot['purpose']='diagnostic'
                elif change=='assisted':boot['diagnostic_assistance']=True
                else:boot['archive_sha256']='b'*64
                (root/'boot/boot.json').write_text(json.dumps(boot))
                with self.assertRaisesRegex(ValueError,'unchanged fresh acceptance package'):
                    behavior_results(root,boot_id,archive,'phone')

    def test_pinned_model_replaces_pattern_while_repaired_model_preserves_component_state(self):
        check=r'''
int main() {
 LazyDynamicLayoutModelNG model;auto first=std::make_shared<LazyCustomLayoutAlgorithmParam>();
 model.Create(first);auto node=DynamicLayoutNode::node;auto pattern=node->pattern;
 auto next=std::make_shared<LazyCustomLayoutAlgorithmParam>();model.Create(next);
 assert(node==DynamicLayoutNode::node);assert(node->dirty==2);
 bool same=node->pattern==pattern;
'''
        compile_run(DOUBLES+self.methods()+check+'assert(!same&&node->replacements==1);}\n',language='c++')
        self.assertEqual(self.apply().returncode,0)
        compile_run(DOUBLES+self.methods()+check+r'''
 assert(same&&node->replacements==0);assert(node->GetPattern<LazyDynamicLayoutPattern>()->customParams_==next);
 model.Create(nullptr);assert(node->pattern==pattern);assert(!node->GetPattern<LazyDynamicLayoutPattern>()->customParams_);
 model.Create(first);assert(node->pattern==pattern);assert(node->GetPattern<LazyDynamicLayoutPattern>()->customParams_==first);
}
''',language='c++')

    def test_real_parameter_update_preserves_or_overrides_callbacks_and_validates_changed_axis(self):
        self.assertEqual(self.apply().returncode,0)
        compile_run(DOUBLES+self.methods()+r'''
int main() {
 for(int oldAxis=0;oldAxis<2;++oldAxis)for(int nextAxis=0;nextAxis<2;++nextAxis)
 for(int mounted=0;mounted<2;++mounted)for(int oldCallback=0;oldCallback<2;++oldCallback)
 for(int newCallback=0;newCallback<2;++newCallback) {
  int oldHits=0,newHits=0;auto old=std::make_shared<LazyCustomLayoutAlgorithmParam>();
  old->axis=static_cast<Axis>(oldAxis);if(oldCallback)old->callback=[&](const auto&){++oldHits;};
  auto next=std::make_shared<LazyCustomLayoutAlgorithmParam>();next->axis=static_cast<Axis>(nextAxis);
  if(newCallback)next->callback=[&](const auto&){++newHits;};
  auto node=std::make_shared<FrameNode>();node->mounted=mounted;
  auto pattern=std::make_shared<LazyDynamicLayoutPattern>(old);pattern->host=node;node->pattern=pattern;
  pattern->UpdateCustomLayoutAlgorithmParam(next);
  assert(pattern->customParams_==next&&pattern->axis_==next->axis);
  assert(pattern->validations==int(mounted&&oldAxis!=nextAxis));
  if(next->callback)next->callback({0,1});assert(oldHits==int(oldCallback&&!newCallback));assert(newHits==newCallback);
  next->SetOnVisibleIndexesChange({});auto reset=std::make_shared<LazyCustomLayoutAlgorithmParam>();reset->axis=next->axis;
  pattern->UpdateCustomLayoutAlgorithmParam(reset);assert(!reset->HasOnVisibleIndexesChange());
  pattern->UpdateCustomLayoutAlgorithmParam(reset);assert(!reset->HasOnVisibleIndexesChange());
  pattern->UpdateCustomLayoutAlgorithmParam(nullptr);assert(!pattern->customParams_&&pattern->axis_==Axis::VERTICAL);
 }
 LazyDynamicLayoutPattern noHost(nullptr);auto horizontal=std::make_shared<LazyCustomLayoutAlgorithmParam>();
 horizontal->axis=Axis::HORIZONTAL;noHost.UpdateCustomLayoutAlgorithmParam(horizontal);assert(noHost.validations==0);
}
''',language='c++')

    def test_exact_replay_rejects_partial_or_unknown_edits_atomically(self):
        self.assertEqual(self.apply().returncode,0);self.assertEqual(self.apply().returncode,0)
        expected={relative:(self.root/BASELINE.PROJECT/relative).read_bytes() for relative,_,_ in BASELINE.FILES}
        first=self.root/BASELINE.PROJECT/BASELINE.FILES[0][0]
        first.write_bytes((FIXTURE/first.name).read_bytes());self.assertNotEqual(self.apply().returncode,0)
        self.assertEqual((self.root/BASELINE.PROJECT/BASELINE.FILES[1][0]).read_bytes(),expected[BASELINE.FILES[1][0]])
        first.write_bytes(b'unknown edited source');self.assertNotEqual(self.apply().returncode,0);self.assertEqual(first.read_bytes(),b'unknown edited source')


if __name__=='__main__':unittest.main()
