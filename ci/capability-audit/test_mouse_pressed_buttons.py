"""Execute the actual converter mask block; not a guest physical-input pass."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/mouse_pressed_buttons'
PATCH = COMPONENT / '0001-preserve-real-pressed-button-mask.patch'


class MousePressedButtonsTests(unittest.TestCase):
    def test_real_mask_all_combinations_movement_and_release(self):
        hunks = patch_sections(PATCH)
        self.assertEqual(list(hunks), ['foundation/arkui/ace_engine/adapter/ohos/entrance/mmi_event_convertor.cpp'])
        actual = '\n'.join(hunks[next(iter(hunks))][0][2])
        original = '\n'.join(hunks[next(iter(hunks))][0][1])
        compile_run(r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <set>
enum class MouseButton : int32_t { NONE_BUTTON=0, LEFT_BUTTON=1, RIGHT_BUTTON=2, MIDDLE_BUTTON=4 };
namespace OHOS::MMI {
struct PointerEvent {
    enum { MOUSE_BUTTON_LEFT=0, MOUSE_BUTTON_RIGHT=1, MOUSE_BUTTON_MIDDLE=2 };
    std::set<int32_t> held;
    const std::set<int32_t>& GetPressedButtons() const { return held; }
};
}
struct Converted { int32_t pressedButtons=-1; };
int convert(const std::shared_ptr<OHOS::MMI::PointerEvent>& pointerEvent) {
    Converted events;
''' + actual + r'''
    return events.pressedButtons;
}
int old_convert(const std::shared_ptr<OHOS::MMI::PointerEvent>& pointerEvent) {
    Converted events;
''' + original + r'''
    return events.pressedButtons;
}
int main() {
    auto pointer=std::make_shared<OHOS::MMI::PointerEvent>();
    for(int repeat=0;repeat<128;++repeat) {
        for(int mask=0;mask<8;++mask) {
            pointer->held.clear();
            for(int bit=0;bit<3;++bit) { if(mask&(1<<bit)) pointer->held.insert(bit); }
            assert(convert(pointer)==mask);
            // The pinned AND-from-zero bug must remain distinguishable.
            assert(old_convert(pointer)==0);
            for(int motion=0;motion<8;++motion) assert(convert(pointer)==mask);
            for(int bit=0;bit<3;++bit) {
                pointer->held.erase(bit);
                assert(convert(pointer)==(mask&(~((1<<(bit+1))-1))));
            }
            assert(convert(pointer)==0);
        }
        // Extended buttons do not become the three legacy mask bits.
        pointer->held={6,7}; assert(convert(pointer)==0);
        pointer->held.insert(0); assert(convert(pointer)==1);
    }
}
''', language='c++')

    def test_pre_gn_component_integration_without_dispatch_policy_change(self):
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('/mouse_pressed_buttons/apply.sh', script)
        self.assertIn('bash "${MOUSE_PRESSED_BUTTONS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', script)
        patch = PATCH.read_text()
        self.assertEqual(patch.count('+        pressedButtons |='), 3)
        self.assertNotIn('DispatchMouseToTouchEvent', patch)
        self.assertNotIn('GetRawDx', patch)
        self.assertNotIn('SetSourceType', patch)

    def test_pointer_journal_is_passive_and_separate_from_spring_results(self):
        page = (ROOT / 'ci/capability-audit/spring_loading_probe.ets').read_text()
        journal = page.split('private pointer(event: MouseEvent): void {', 1)[1].split('private record(', 1)[0]
        for expression in ('event.action', 'event.button', 'event.displayX', 'event.displayY',
                           'event.pressedButtons', '-pointer.log'):
            self.assertIn(expression, journal)
        for forbidden in ('stopPropagation(', 'this.callback(', 'this.record(', 'startDrag(', 'setData('):
            self.assertNotIn(forbidden, journal)
        runner = (ROOT / 'ci/capability-audit/run_normal_hap_probe.py').read_text()
        self.assertIn('failure-actual-spring-pointer', runner)


if __name__ == '__main__': unittest.main()
