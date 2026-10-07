#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from run_root_probe import digest
from verify_gap_closure import behavior_results
from verify_sensor_health_resolution import verify as verify_resolution


CHECKER = Path(__file__).resolve().parents[2] / (
    'patches/common/interface/sdk-js/sensor_health_permission/verify_source.py')
spec = importlib.util.spec_from_file_location('sensor_health_permission_contract', CHECKER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SensorHealthPermissionContractTests(unittest.TestCase):
    def test_three_legacy_overloads_use_only_registered_checked_permission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdk = root / 'interface/sdk-js/api/@ohos.sensor.d.ts'
            backend = root / 'base/sensors/sensor/utils/common/include/permission_util.h'
            definitions = root / ('base/security/access_token/services/accesstokenmanager/'
                                  'permission_definitions.json')
            for path in (sdk, backend, definitions):
                path.parent.mkdir(parents=True, exist_ok=True)
            contract = ('/**\n * @permission ohos.permission.READ_HEALTH_DATA\n'
                        ' * @param { SensorType.SENSOR_TYPE_ID_HEART_RATE } type\n */\n')
            sdk.write_text(contract * 3)
            backend.write_text('const std::string READ_HEALTH_DATA_PERMISSION = '
                               '"ohos.permission.READ_HEALTH_DATA";')
            definitions.write_text(json.dumps({'definePermissions': [{
                'name': 'ohos.permission.READ_HEALTH_DATA', 'grantMode': 'user_grant',
                'availableLevel': 'normal',
                'deviceTypes': ['phone', '2in1', 'tablet', 'tv', 'wearable']}]}))
            metadata = module.verify(root)
            raw = json.dumps({'kind': 'definition', 'permissionName': 'ohos.permission.READ_HEALTH_DATA',
                'result': 0, 'grantMode': 0, 'availableLevel': 1, 'availableType': 0,
                'provisionEnable': False, 'distributedSceneEnable': False,
                'isKernelEffect': False, 'hasValue': False}) + '\n'
            source_definitions = json.loads(definitions.read_text())
            self.assertEqual(verify_resolution(metadata, source_definitions, raw,
                                               metadata['patch_sha256']),
                             ('ohos.permission.HEALTH_DATA', 'ohos.permission.HEART_RATE'))
            with self.assertRaises(ValueError):
                verify_resolution(metadata, source_definitions, raw.replace('"grantMode": 0',
                                                                         '"grantMode": 1'),
                                  metadata['patch_sha256'])
            with self.assertRaises(ValueError):
                verify_resolution(metadata, source_definitions, raw, '0' * 64)
            sdk.write_text(sdk.read_text().replace('READ_HEALTH_DATA', 'HEALTH_DATA', 1))
            with self.assertRaises(ValueError):
                module.verify(root)
            sdk.write_text(contract * 3)
            definitions.write_text(json.dumps({'definePermissions': []}))
            with self.assertRaises(ValueError):
                module.verify(root)

    def test_package_metadata_and_actual_registry_close_only_false_legacy_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'boot/extract/package'
            directory.mkdir(parents=True)
            patch_file = CHECKER.with_name('0001-document-the-registered-heart-rate-permission.patch')
            metadata = {'status': 'pass', 'schema_version': 1,
                'scope': 'three_Sensor_deprecated_overloads_match_registered_checked_health_permission',
                'permission': 'ohos.permission.READ_HEALTH_DATA',
                'legacy_unregistered_names': ['ohos.permission.HEALTH_DATA',
                                              'ohos.permission.HEART_RATE'],
                'patch_sha256': digest(patch_file),
                'source_sha256': {name: 'a' * 64 for name in module.SOURCE_FILES}}
            contract = directory / 'sensor-health-permission.json'
            contract.write_text(json.dumps(metadata))
            (root / 'boot/boot.json').write_text(json.dumps({'status': 'pass',
                'purpose': 'acceptance', 'archive_sha256': 'archive',
                'initial_package_file_sha256': {'sensor-health-permission.json': digest(contract)},
                'test_environment': {'boot_id': 'fresh', 'freshly_extracted_directory': str(directory)}}))
            permissions = root / 'permission-registry'
            permissions.mkdir()
            definitions = permissions / 'definitions.json'
            definitions.write_text(json.dumps({'definePermissions': [{
                'name': 'ohos.permission.READ_HEALTH_DATA', 'grantMode': 'user_grant',
                'availableLevel': 'normal',
                'deviceTypes': ['phone', '2in1', 'tablet', 'tv', 'wearable']}]}))
            raw = permissions / 'stdout.jsonl'
            raw.write_text(json.dumps({'kind': 'definition',
                'permissionName': 'ohos.permission.READ_HEALTH_DATA', 'result': 0,
                'grantMode': 0, 'availableLevel': 1, 'availableType': 0,
                'provisionEnable': False, 'distributedSceneEnable': False,
                'isKernelEffect': False, 'hasValue': False}) + '\n')
            (permissions / 'result.json').write_text(json.dumps({'status': 'pass',
                'archive_sha256': 'archive', 'boot_id': 'fresh', 'kind': 'permission-registry',
                'device': 'phone', 'kernel_boot_id_unchanged': True,
                'definitions': str(definitions), 'definitions_sha256': digest(definitions),
                'log_sha256': digest(raw), 'run_id': 'run', 'probe_exit_code': 0,
                'result': {'verified': True}}))
            with patch('verify_permission_results.verify', return_value={'verified': True}):
                closed = behavior_results(root, 'fresh', 'archive', 'phone')
            self.assertIn('permission:ohos.permission.HEALTH_DATA', closed)
            self.assertIn('permission:ohos.permission.HEART_RATE', closed)
            self.assertIn('behavior:api26-permission-registry-gaps-phone', closed)
            contract.write_text(json.dumps(metadata | {'patch_sha256': '0' * 64}))
            with patch('verify_permission_results.verify', return_value={'verified': True}):
                closed = behavior_results(root, 'fresh', 'archive', 'phone')
            self.assertNotIn('permission:ohos.permission.HEALTH_DATA', closed)
