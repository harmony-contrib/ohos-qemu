#!/usr/bin/env python3
"""Run real GNSS/fusion producer functions with frozen HDI/provider boundaries.

The previous six-patch prefix must reproduce the regressions. Dependency doubles
are bounded host checks, not real GNSS/WLAN evidence or packaged runtime closure.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import subprocess
import tempfile
import unittest

from batch_location_runtime_fixture import runtime_sources, function
import test_batch_location_gnss_runtime as gnss_fixture
import test_batch_location_fusion_runtime as fusion_fixture
import test_batch_location_business_runtime as business_fixture

ACCURACY_CONTRACT = Path(__file__).parent / 'fixtures/batch_location/location_accuracy_compatibility_before.json'


GNSS_MAIN = r'''
int main(int argc, char** argv) {
 assert(argc == 2);int scenario = std::stoi(argv[1]);
 auto* service = GnssAbility::GetInstance();GnssEventCallback callback;
 LocationInfo fix{};
 fix.fieldValidity = GNSS_LOCATION_LAT_VALID | GNSS_LOCATION_LONG_VALID |
     GNSS_LOCATION_HORIZONTAL_ACCURACY_VALID;
 fix.latitude = 31.25;fix.longitude = 121.5;fix.horizontalAccuracy = 3.5;
 fix.timeSinceBoot = 1000000000;fix.timeForFix = 1700000034567LL;
 if (scenario == 0) {
  // No fix and individual missing mandatory fields cannot become a real point.
  for (uint32_t mask : {0u, 1u, 2u, 32u, 33u, 34u}) {
   auto invalid = fix;invalid.fieldValidity = mask;
   assert(callback.ReportLocation(invalid) == ERR_INVALID_VALUE && service->fixes.empty());
  }
 } else if (scenario == 1) {
  for (int field = 0; field < 9; ++field) {
   auto invalid = fix;
   switch (field) {
    case 0: invalid.latitude = std::numeric_limits<double>::quiet_NaN();break;
    case 1: invalid.longitude = std::numeric_limits<double>::infinity();break;
    case 2: invalid.latitude = 90.000001;break;
    case 3: invalid.latitude = -90.000001;break;
    case 4: invalid.longitude = 180.000001;break;
    case 5: invalid.longitude = -180.000001;break;
    case 6: invalid.horizontalAccuracy = -1;break;
    case 7: invalid.horizontalAccuracy = std::numeric_limits<float>::quiet_NaN();break;
    case 8: invalid.horizontalAccuracy = std::numeric_limits<float>::infinity();break;
   }
   assert(callback.ReportLocation(invalid) == ERR_INVALID_VALUE && service->fixes.empty());
  }
 } else if (scenario == 2) {
  // Position can be valid without a UTC clock sample. That sample cannot set time.
  assert(callback.ReportLocation(fix) == ERR_OK && service->fixes.size() == 1);
  assert(clockSamples.empty());
  fix.fieldValidity |= GNSS_LOCATION_TIME_VALID;
  for (int64_t invalid : {0LL, -1LL}) {
   fix.timeForFix = invalid;assert(callback.ReportLocation(fix) == ERR_OK);
   assert(clockSamples.empty());
  }
  fix.timeForFix = 1700000034567LL;assert(callback.ReportLocation(fix) == ERR_OK);
  assert(clockSamples == std::vector<int64_t>{fix.timeForFix});
 } else if (scenario == 3) {
  // Inclusive geographic/accuracy boundaries remain legal; flags survive intact.
  for (double lat : {-90.0, 0.0, 90.0}) for (double lon : {-180.0, 0.0, 180.0}) {
   fix.latitude = lat;fix.longitude = lon;fix.horizontalAccuracy = 0;
   assert(callback.ReportLocation(fix) == ERR_OK);
   auto& actual = service->fixes.back();
   assert(actual.latitude == lat && actual.longitude == lon && actual.accuracy == 0);
   assert(actual.validity == fix.fieldValidity && !actual.mock && actual.source == 1);
  }
 } else {
  // Accuracy is optional: preserve the actual raw field and its clear validity bit.
  fix.fieldValidity = GNSS_LOCATION_LAT_VALID | GNSS_LOCATION_LONG_VALID;
  for (float accuracy : {0.0f, -1.0f, 1234.0f,
      std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()}) {
   fix.horizontalAccuracy = accuracy;
   auto before = service->fixes.size();
   assert(callback.ReportLocation(fix) == ERR_OK && service->fixes.size() == before + 1);
   const auto& actual = service->fixes.back();
   assert(actual.latitude == fix.latitude && actual.longitude == fix.longitude);
   assert(actual.validity == fix.fieldValidity);
   assert(std::isnan(accuracy) ? std::isnan(actual.accuracy) : actual.accuracy == accuracy);
  }
  assert(clockSamples.empty());
 }
 std::cout << "GNSS producer scenario " << scenario << " passed at host boundaries\n";
}
'''

SKIING_UNKNOWN_MAIN = r'''
int main() {
 auto& manager=*ReportManager::GetInstance();auto request=std::make_shared<Request>();
 request->config->SetSportsType(4);auto point=std::make_unique<Location>();
 point->validity=3;int calls=0;
 for (double accuracy : {0.0, -1.0, 1234.0, std::numeric_limits<double>::quiet_NaN(),
     std::numeric_limits<double>::infinity()}) {
  point->accuracy=accuracy;point->timestamp=++bootNow;
  assert(manager.ReportLocationByCallback(request,point));
  assert(request->callback->calls==++calls && manager.skiingTracks_.empty());
 }
 point->validity=35;point->accuracy=5;point->timestamp=++bootNow;
 assert(manager.ReportLocationByCallback(request,point));assert(manager.skiingTracks_.size()==1);
 auto& history=manager.skiingTracks_.begin()->second;assert(history.sequence==1);
 point->validity=3;point->accuracy=0;point->timestamp=++bootNow;
 assert(manager.ReportLocationByCallback(request,point));assert(history.sequence==1);
 point->validity=35;point->accuracy=5;bootNow+=1000000000;point->timestamp=bootNow;
 assert(manager.ReportLocationByCallback(request,point));assert(history.sequence==2);
}
'''

FUSION_UNKNOWN_MAIN = r'''
int main() {
 auto* service=LocatorAbility::GetInstance();FusionFenceRequest req;
 req.identifier="unknown-accuracy";req.scene=1;req.fenceType=1;req.events=3;
 req.loiterMs=100000;req.expirationMs=100000;
 FusionGnssFence shape;shape.type=2;shape.radius=100;shape.expirationMs=100000;req.gnss={shape};
 sptr<IRemoteObject> callback=new IRemoteObject();assert(service->AddFusionFence(req,callback)==0);
 auto record=service->fusionFences_.front();auto point=std::make_unique<Location>();
 point->validity=3;
 for (double accuracy : {0.0, -1.0, 1234.0, std::numeric_limits<double>::quiet_NaN(),
     std::numeric_limits<double>::infinity()}) {
  point->accuracy=accuracy;point->stamp=++now;
  record->locationCallback->OnLocationReport(point);
  assert(callback->events.empty() && record->gnssTime==0);
 }
 point->validity=35;point->accuracy=1;point->stamp=++now;
 record->locationCallback->OnLocationReport(point);assert(callback->events==std::vector<int>{1});
 const auto validTime=record->gnssTime;
 point->validity=3;point->lon=0.002;point->accuracy=0;point->stamp=++now;
 record->locationCallback->OnLocationReport(point);
 assert(callback->events==std::vector<int>{1} && record->gnssTime==validTime);
 point->validity=35;point->accuracy=1;point->stamp=++now;
 record->locationCallback->OnLocationReport(point);assert(callback->events==std::vector<int>({1,2}));
 service->ClearFusionFences();service->fusionStopping_=false;service->CheckFusionFences();
 assert(!service->HasFusionFences());
}
'''

WIFI_MAIN = r'''
int main() {
 auto* service = LocatorAbility::GetInstance();auto* data = LocatorRequiredDataManager::GetInstance();
 FusionFenceRequest req;req.identifier="ordered";req.scene=1;req.fenceType=4;
 req.events=3;req.loiterMs=100000;req.expirationMs=100000;
 FusionWifiFence wifi;wifi.type=2;wifi.features.push_back({-40,3,{"aa:bb:cc:dd:ee:ff"}});
 req.wifi={wifi};sptr<IRemoteObject> callback=new IRemoteObject();
 assert(service->AddFusionFence(req,callback)==0);
 auto record=service->fusionFences_.front();
 auto scan=std::make_shared<LocatingRequiredData>();scan->wifi->bssid="aa:bb:cc:dd:ee:ff";
 const auto firstScan=now;data->scanTime=firstScan;scan->wifi->timestamp=now/1000;
 record->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>{1});
 // The completion timestamp owns the snapshot, independently of each AP's age.
 // Replayed or older snapshots must not reverse an already observed state.
 scan->wifi->rssi=-80;record->wifiCallback->OnLocatingDataChange({scan});
 assert(callback->events==std::vector<int>{1});
 now+=1000000000;data->scanTime=firstScan-1;
 record->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>{1});
 data->scanTime=now;
 record->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>({1,2}));
 // A new scan may retain an AP's still-fresh timestamp: do not dedup by min AP time.
 now+=1000000000;data->scanTime=now;scan->wifi->rssi=-40;
 record->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>({1,2,1}));
 scan->wifi->rssi=-80;data->scanTime=firstScan;
 record->wifiCallback->OnLocatingDataChange({scan});assert(callback->events==std::vector<int>({1,2,1}));
 auto old=record->wifiCallback;assert(service->RemoveFusionFence("ordered")==0);
 sptr<IRemoteObject> next=new IRemoteObject();assert(service->AddFusionFence(req,next)==0);
 data->scanTime=++now;old->OnLocatingDataChange({scan});assert(next->events.empty());
 service->ClearFusionFences();service->fusionStopping_=false;service->CheckFusionFences();
 assert(!service->HasFusionFences());
}
'''


def gnss_program(prefix=None, initial_strict=False):
    fixture = gnss_fixture.GnssRuntimeTests()
    fixture.sources = runtime_sources(prefix=prefix)
    fixture.abi = json.loads(gnss_fixture.ABI.read_text())
    program = '#include <cmath>\n' + fixture.harness().replace(
        'static void SetGpsTime(int64_t){}',
        'std::vector<int64_t> clockSamples;static void SetGpsTime(int64_t value){clockSamples.push_back(value);}'
    ).replace(gnss_fixture.MAIN, GNSS_MAIN)
    if initial_strict:
        snapshot = json.loads(ACCURACY_CONTRACT.read_text())['initial_strict_callback']
        assert hashlib.sha256(snapshot['text'].encode()).hexdigest() == snapshot['sha256']
        actual = function(fixture.sources[gnss_fixture.CALLBACK], 'int32_t GnssEventCallback::ReportLocation(')
        program = program.replace(actual, snapshot['text'])
    return program


def fusion_program(main, prefix=None):
    sources = runtime_sources(prefix=prefix)
    header = fusion_fixture.without_includes(sources['interfaces/inner_api/include/fusion_fence_request.h'])
    header = header.replace('namespace OHOS {', '').replace('namespace Location {', '')
    header = header.replace('} // namespace Location', '').replace('} // namespace OHOS', '')
    contract = json.loads((Path(__file__).parent / 'fixtures/batch_location/location_account_contract_before.json').read_text())
    service = fusion_fixture.SERVICE.replace('FROZEN_ACCOUNT_DECLARATIONS', '\n '.join(contract['header']['declarations']))
    source = sources['services/location_locator/locator/source/locator_ability.cpp']
    start = source.index('namespace {\nconstexpr int64_t FUSION_GNSS_FRESH_NS')
    # Keep the same complete fusion block as the existing service harness.
    end = source.index('ErrCode LocatorAbility::StartDistrictLocating(', start)
    return fusion_fixture.COMMON + fusion_fixture.SPTR + header + service + '\n'.join(
        contract['source']['functions'].values()) + source[start:end] + main


def skiing_program(prefix=None):
    sources = runtime_sources(prefix=prefix)
    source = sources['services/location_locator/locator/source/report_manager.cpp']
    actual = source[source.index('namespace {\nconstexpr int64_t TRACK_RETENTION_NS'):source.index('void ReportManager::LocationReportDelayTimeCheck(')]
    return '#include <limits>\n' + business_fixture.BASE + business_fixture.config_code(sources) + \
        business_fixture.TRACK + function(source, 'bool ReportManager::ReportLocationByCallback(') + actual + SKIING_UNKNOWN_MAIN


class ProducerEvidenceTests(unittest.TestCase):
    def compile_and_run(self, source, arguments, expect_success):
        with tempfile.TemporaryDirectory(prefix='batch-location-producer-evidence-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source)
            result = subprocess.run(['clang++', '-std=c++17', '-DFEATURE_GNSS_SUPPORT', '-DWIFI_ENABLE',
                '-DTEL_CORE_SERVICE_ENABLE', '-pthread', '-fsanitize=address,undefined', '-g',
                str(path / 'test.cpp'), '-o', str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for argument in arguments:
                result = subprocess.run([str(path / 'test'), *argument], capture_output=True, text=True,
                    env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1'},
                    preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
                if expect_success:
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                else:
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn('Assertion', result.stderr)

    def test_previous_prefix_reproduces_gnss_and_clock_failures(self):
        self.compile_and_run(gnss_program(prefix=6), [[str(i)] for i in range(3)], False)

    def test_current_gnss_validation_and_valid_boundaries(self):
        self.compile_and_run(gnss_program(), [[str(i)] for i in range(5)], True)

    def test_initial_cf32293_rejects_valid_position_without_optional_accuracy(self):
        self.compile_and_run(gnss_program(initial_strict=True), [['4']], False)

    def test_previous_prefix_accepts_unknown_accuracy_in_precision_consumers(self):
        self.compile_and_run(skiing_program(prefix=6), [[]], False)
        self.compile_and_run(fusion_program(FUSION_UNKNOWN_MAIN, prefix=6), [[]], False)

    def test_current_unknown_accuracy_preserves_normal_callback_and_precision_silence(self):
        self.compile_and_run(skiing_program(), [[]], True)
        self.compile_and_run(fusion_program(FUSION_UNKNOWN_MAIN), [[]], True)

    def test_accuracy_bit_matches_actual_frozen_hdi_contract(self):
        sources = runtime_sources()
        line = re.search(r'^constexpr int32_t LOCATION_FIELD_HORIZONTAL_ACCURACY_VALID = .*;$',
            sources['interfaces/inner_api/include/constant_definition.h'], re.M).group()
        abi = json.loads(gnss_fixture.ABI.read_text())
        raw = abi['/ohos/out/arm64_virt/gen/drivers/interface/location/gnss/v2_0/gnss_types.h']['text']
        enum = gnss_fixture.declaration(raw, 'enum GnssLocationValidity')
        self.compile_and_run('#include <cstdint>\n' + enum + line + '\n' +
            'static_assert(LOCATION_FIELD_HORIZONTAL_ACCURACY_VALID == GNSS_LOCATION_HORIZONTAL_ACCURACY_VALID);\nint main() {}\n', [[]], True)

    def test_previous_prefix_reproduces_replayed_scan_transition(self):
        self.compile_and_run(fusion_program(WIFI_MAIN, prefix=6), [[]], False)

    def test_current_scan_completion_order_and_owner_lifetime(self):
        self.compile_and_run(fusion_program(WIFI_MAIN), [[]], True)


if __name__ == '__main__':
    unittest.main()
