#!/usr/bin/env python3
"""Exercise the actual virtual VDI class, not a booted HDI/service/decoder."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "patches/common/drivers/peripheral/vibrator/files/qemu_virtual_vibrator.cpp"

# Standalone type fixtures mirror the fields used from the V1_1 header. The
# product build, not these fixtures, validates the upstream virtual ABI.
PREAMBLE = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>
#define HDF_SUCCESS 0
#define HDF_ERR_INVALID_PARAM -2
#define HDF_ERR_NOT_SUPPORT -3
#define HDF_LOGI(...) ((void)0)
struct DeviceVibratorInfo { int32_t deviceId; int32_t vibratorId; };
enum HdfVibratorModeVdi { VDI_VIBRATOR_MODE_ONCE, VDI_VIBRATOR_MODE_PRESET,
    VDI_VIBRATOR_MODE_HDHAPTIC, VDI_VIBRATOR_MODE_BUTT };
enum { VDI_EFFECT_TYPE_TIME, VDI_EFFECT_TYPE_PRIMITIVE, VDI_EFFECT_TYPE_BUTT };
struct HdfVibratorInfoVdi {
    bool isSupportIntensity, isSupportFrequency;
    uint16_t intensityMaxValue, intensityMinValue;
    int16_t frequencyMaxValue, frequencyMinValue;
    int32_t deviceId, vibratorId, position, isLocal;
};
struct HdfTimeEffectVdi { int32_t delay, time; uint16_t intensity; int16_t frequency; };
struct HdfPrimitiveEffectVdi { int32_t delay, effectId; uint16_t intensity; };
union HdfEffectVdi { HdfTimeEffectVdi timeEffect; HdfPrimitiveEffectVdi primitiveEffect; };
struct HdfCompositeEffectVdi { int32_t type; std::vector<HdfEffectVdi> effects; };
struct HdfEffectInfoVdi { int32_t duration; bool isSupportEffect; };
struct HapticPaketVdi {};
struct HapticCapacityVdi {
    bool isSupportHdHaptic, isSupportPresetMapping, isSupportTimeDelay;
    int32_t vibratorId; bool reserved0; int32_t reserved1;
};
struct Clock {
    using time_point = std::chrono::steady_clock::time_point;
    static inline time_point current {};
    static time_point now() { return current; }
    static void advance(uint64_t ms) { current += std::chrono::milliseconds(ms); }
};
HdfEffectVdi item(int32_t delay, int32_t time, uint16_t intensity = 50, int16_t frequency = 0) {
    HdfEffectVdi result {}; result.timeEffect = {delay, time, intensity, frequency}; return result;
}
bool running(QemuVirtualVibrator &v);
'''


def run_class(program):
    source = SOURCE.read_text()
    body = source.split("constexpr int32_t QEMU_DEVICE_ID", 1)[1].split("\nint32_t CreateVdiInstance", 1)[0]
    body = "constexpr int32_t QEMU_DEVICE_ID" + body
    body = body.replace(" : public IVibratorInterfaceVdi", "").replace(" override", "")
    preamble = PREAMBLE.replace("bool running(QemuVirtualVibrator &v);", "")
    helper = "\nbool running(QemuVirtualVibrator &v) { bool state = false; assert(v.IsVibratorRunning(state) == 0); return state; }\n"
    compiler = shutil.which("clang++")
    if not compiler:
        raise RuntimeError("clang++ is required for VDI sanitizer regressions")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "vibrator.cpp"
        binary = Path(directory) / "vibrator"
        path.write_text(preamble + body + helper + program)
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-g", str(path), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


class VirtualVibratorTests(unittest.TestCase):
    def test_upstream_relative_start_and_terminal_stop(self):
        run_class(r'''
int main() {
    QemuVirtualVibrator v; assert(v.Init() == 0);
    // Events at 0..100 and 200..250; upstream appends stop at 250.
    HdfCompositeEffectVdi sequence {VDI_EFFECT_TYPE_TIME,
        {item(0,100), item(200,50), item(50,0,0)}};
    assert(v.EnableCompositeEffect(sequence) == 0);
    assert(running(v)); Clock::advance(249); assert(running(v));
    Clock::advance(1); assert(!running(v));
    // Overlap: the last-started event does not necessarily end last.
    sequence.effects = {item(0,100), item(50,10), item(10,0,0)};
    assert(v.EnableCompositeEffect(sequence) == 0);
    Clock::advance(99); assert(running(v)); Clock::advance(1); assert(!running(v));
    // A service fragment can contain just the final delay/stop item.
    sequence.effects = {item(30,0,0)}; assert(v.EnableCompositeEffect(sequence) == 0);
    Clock::advance(29); assert(running(v)); Clock::advance(1); assert(!running(v));
    assert(v.StartOnce(100) == 0);
    sequence.effects = {item(0,0,0)}; assert(v.EnableCompositeEffect(sequence) == 0);
    assert(!running(v));
}
''')

    def test_invalid_input_overflow_keeps_previous_deadline(self):
        run_class(r'''
int main() {
    QemuVirtualVibrator v; v.Init();
    std::vector<HdfCompositeEffectVdi> invalid {
        {VDI_EFFECT_TYPE_TIME, {}}, {VDI_EFFECT_TYPE_BUTT, {item(0,10)}},
        {VDI_EFFECT_TYPE_TIME, {item(-1,10)}}, {VDI_EFFECT_TYPE_TIME, {item(0,-1)}},
        {VDI_EFFECT_TYPE_TIME, {item(0,0,50)}},
        {VDI_EFFECT_TYPE_TIME, {item(0,0,0,1)}},
        {VDI_EFFECT_TYPE_TIME, {item(0,0,0),item(10,20)}},
        {VDI_EFFECT_TYPE_TIME, {item(INT32_MAX,INT32_MAX),item(INT32_MAX,2)}}
    };
    for (const auto &sequence : invalid) {
        assert(v.StartOnce(10) == 0);
        assert(v.EnableCompositeEffect(sequence) == HDF_ERR_INVALID_PARAM);
        Clock::advance(9); assert(running(v)); Clock::advance(1); assert(!running(v));
    }
    // Full UINT32_MAX duration is accepted exactly, not clamped from overflow.
    HdfCompositeEffectVdi limit {VDI_EFFECT_TYPE_TIME,
        {item(INT32_MAX,INT32_MAX),item(1,INT32_MAX)}};
    assert(v.EnableCompositeEffect(limit) == 0);
    Clock::advance(UINT32_MAX - 1); assert(running(v));
    Clock::advance(1); assert(!running(v));
}
''')

    def test_capabilities_are_time_only(self):
        run_class(r'''
int main() {
    QemuVirtualVibrator v; v.Init(); HapticCapacityVdi capacity {};
    assert(v.GetHapticCapacity(capacity) == 0);
    assert(capacity.isSupportTimeDelay);
    assert(!capacity.isSupportHdHaptic && !capacity.isSupportPresetMapping);
    assert(capacity.vibratorId == 0);
    HdfCompositeEffectVdi primitive {VDI_EFFECT_TYPE_PRIMITIVE, {item(0,10)}};
    assert(v.EnableCompositeEffect(primitive) == HDF_ERR_NOT_SUPPORT);
    assert(v.EnableVibratorModulation(10,50,50) == HDF_ERR_NOT_SUPPORT);
    assert(v.StartByIntensity("effect",50) == HDF_ERR_NOT_SUPPORT);
    assert(v.PlayHapticPattern({}) == HDF_ERR_NOT_SUPPORT);
    std::vector<HdfVibratorInfoVdi> info;
    assert(v.GetDeviceVibratorInfo(info) == 0 && info.size() == 1);
    assert(!info[0].isSupportIntensity && !info[0].isSupportFrequency && info[0].isLocal == 1);
}
''')

    def test_one_shot_cancel_device_filter_and_reinitialization(self):
        run_class(r'''
int main() {
    QemuVirtualVibrator v; v.Init(); assert(!running(v));
    assert(v.StartOnce(0) == HDF_ERR_INVALID_PARAM);
    assert(v.StartOnce({0,0},20) == 0);
    assert(v.StartOnce({1,0},500) == HDF_ERR_INVALID_PARAM);
    assert(v.Stop({0,1},VDI_VIBRATOR_MODE_ONCE) == HDF_ERR_INVALID_PARAM);
    Clock::advance(19); assert(running(v)); Clock::advance(1); assert(!running(v));
    assert(v.StartOnce({-1,-1},10) == 0);
    assert(v.Stop(VDI_VIBRATOR_MODE_BUTT) == HDF_ERR_INVALID_PARAM && running(v));
    assert(v.Stop({-1,-1},VDI_VIBRATOR_MODE_ONCE) == 0 && !running(v));
    assert(v.StartOnce(10) == 0); assert(v.StopVibrateBySessionId({0,0},1) == 0 && !running(v));
    assert(v.StartOnce(10) == 0); assert(v.Init() == 0 && !running(v));
}
''')

    def test_preset_query_and_unknown_effect_do_not_fake_support(self):
        run_class(r'''
int main() {
    QemuVirtualVibrator v; v.Init(); HdfEffectInfoVdi info {-1, true};
    assert(v.GetEffectInfo("haptic.clock.timer", info) == 0);
    assert(info.isSupportEffect && info.duration == 100);
    assert(v.Start("haptic.clock.timer") == 0);
    Clock::advance(99); assert(running(v)); Clock::advance(1); assert(!running(v));
    assert(v.StartOnce(10) == 0);
    assert(v.GetEffectInfo("qemu.unknown.effect", info) == 0);
    assert(!info.isSupportEffect && info.duration == 0);
    assert(v.Start("qemu.unknown.effect") == HDF_ERR_NOT_SUPPORT);
    assert(v.GetEffectInfo("", info) == HDF_ERR_INVALID_PARAM);
    assert(!info.isSupportEffect && info.duration == 0);
    assert(v.Start("") == HDF_ERR_INVALID_PARAM);
    assert(v.Start({1,0}, "haptic.clock.timer") == HDF_ERR_INVALID_PARAM);
    Clock::advance(9); assert(running(v)); Clock::advance(1); assert(!running(v));
}
''')


if __name__ == "__main__":
    unittest.main()
