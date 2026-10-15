"""Reject branch or upstream collisions before merging capability workers."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_capability_agent_scope import check_scope


class CapabilityAgentScopeTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'docs/capability-audit/parallel-work-plan.json').read_text())
        self.target = 'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp'
        self.report = {'upstream_targets': [self.target], 'remaining_gaps': [],
                       'tests': [], 'integration_requests': []}
        self.report['requirements_review'] = {
            row['id']: {'status': 'pending_new_package'}
            for row in self.plan['agents']['network']['requirements']}
        self.changed = ['ci/capability-audit/test_batch_network_lifecycle.py']

    def check(self, **overrides):
        args = {'plan': self.plan, 'agent': 'network', 'changed': self.changed,
                'report': self.report, 'patch_targets': {self.target}, 'other_reports': []}
        return check_scope(**{**args, **overrides})

    def test_own_branch_and_all_nine_requirements_are_accepted_without_runtime_claim(self):
        result = self.check()
        self.assertEqual(result['requirements_reviewed'], 9)
        self.assertIs(result['first_artifact_behavior_gate_passed'], False)

    def test_parent_files_and_another_capability_are_rejected(self):
        for path in ['scripts/build_standard_qemu_in_docker.sh',
                     'ci/capability-audit/verify_gap_closure.py',
                     'patches/common/foundation/multimedia/media_library/new.patch']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'other-group'):
                self.check(changed=[path])

    def test_disjoint_repository_patches_cannot_change_the_same_upstream_source(self):
        with self.assertRaisesRegex(ValueError, 'same upstream'):
            self.check(other_reports=[{'upstream_targets': [self.target]}])
        with self.assertRaisesRegex(ValueError, 'upstream target owned'):
            self.check(report={**self.report, 'upstream_targets': [
                'foundation/graphic/graphic_2d/render_service.cpp']})

    def test_missing_or_extra_requirements_and_unreported_targets_are_rejected(self):
        report = copy.deepcopy(self.report)
        report['requirements_review'].pop(next(iter(report['requirements_review'])))
        with self.assertRaisesRegex(ValueError, 'every assigned'):
            self.check(report=report)
        report = copy.deepcopy(self.report)
        report['requirements_review']['unassigned:requirement'] = {}
        with self.assertRaisesRegex(ValueError, 'every assigned'):
            self.check(report=report)
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            self.check(patch_targets={self.target, 'foundation/communication/netmanager_base/new.cpp'})

    def test_path_aliases_and_missing_acceptance_handoff_are_rejected(self):
        for target in ['/ohos/absolute.cpp', 'foundation/../source.cpp', 'foundation//source.cpp']:
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.check(report={**self.report, 'upstream_targets': [target]})
        report = dict(self.report)
        del report['integration_requests']
        with self.assertRaisesRegex(ValueError, 'integration requests'):
            self.check(report=report)

    def test_component_directory_does_not_replace_explicit_upstream_ownership(self):
        target = 'foundation/ability/ability_runtime/frameworks/native/child_process/src/native_child_callback.cpp'
        report = {'requirements_review': {row['id']: {} for row in self.plan['agents']['system']['requirements']},
                  'upstream_targets': [target], 'remaining_gaps': [], 'tests': [], 'integration_requests': []}
        check_scope(self.plan, 'system', [
            'patches/common/foundation/ability/ability_runtime/native_child_process/0004-callback.patch'],
            report, {target}, [])
        with self.assertRaisesRegex(ValueError, 'upstream target owned'):
            check_scope(self.plan, 'system', [], {**report, 'upstream_targets': [
                'foundation/ability/ability_runtime/frameworks/native/appdata/new.cpp']}, set(), [])

    def test_one_cross_component_file_does_not_grant_its_parent_directory(self):
        target = 'device/qemu/common/virt_full/audio_alsa/vendor_capture.c'
        report = {'requirements_review': {row['id']: {} for row in self.plan['agents']['media']['requirements']},
                  'upstream_targets': [target], 'remaining_gaps': [], 'tests': [], 'integration_requests': []}
        check_scope(self.plan, 'media', [], report, {target}, [])
        for foreign in [target + '.other', 'device/qemu/common/virt_full/audio_alsa/vendor_render.c']:
            with self.subTest(path=foreign), self.assertRaisesRegex(ValueError, 'upstream target owned'):
                check_scope(self.plan, 'media', [], {**report, 'upstream_targets': [foreign]}, {foreign}, [])


if __name__ == '__main__':
    unittest.main()
