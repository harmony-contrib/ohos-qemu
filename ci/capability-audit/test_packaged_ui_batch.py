"""Synthetic owned-VM batch and cleanup wiring; never actual image evidence."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import run_packaged_ui_batch as runner


class UiBatchTests(unittest.TestCase):
    def execute(self, root, *, failed=None, cleanup=True, restoration=True):
        guest = MagicMock(); guest.arch='arm64'; guest.device='phone'; guest.target='owned'; guest.udid='a'*64
        guest.report={'test_environment': {'boot_id': 'boot'}}
        guest.shell.side_effect=lambda script, label: {'power-shell timeout -o 86400000': 'Override screen off time to 86400000',
            'power-shell timeout -r': 'Restore screen off time' if restoration else 'failed',
            'cat /proc/sys/kernel/random/boot_id': 'boot'}.get(script, 'policy')
        before=dict(base_ms=30000, override_ms=None)
        archive=root/'archive';archive.write_text('synthetic NOT image')
        calls=[]
        def child(name):
            def run(args):
                calls.append(name); args.output.mkdir()
                result=dict(status='fail' if failed==name else 'pass', failures=['test failure'] if failed==name else [],
                            cleanup_verified=cleanup)
                (args.output/'evidence.json').write_text(json.dumps(result));return result
            return run
        with patch.object(runner,'QemuGuest') as constructor, patch.object(runner,'run_home',return_value={'status':'pass'}), \
                patch.object(runner,'power_timeout',side_effect=[before,dict(before,override_ms=86400000),before]), \
                patch.object(runner,'run_normal',side_effect=child('arkui-components')), \
                patch.object(runner,'run_luminance',side_effect=child('luminance-sampler')), \
                patch.object(runner,'run_blink',side_effect=child('screen-blink')), \
                patch.object(runner,'stop_previous_probe',return_value={'kernel_process_absent':True}) as stop:
            constructor.return_value.start.return_value=guest
            result=runner.run(argparse.Namespace(archive=archive,sdk=root/'sdk',hdc='hdc',output=root/'result'))
            stop.assert_called_once()
        guest.close.assert_called_once()
        self.assertIn('power-shell timeout -r',[call.args[0] for call in guest.shell.call_args_list])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        return result,calls

    def test_pass_is_only_three_probe_batch_not_full_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            result,calls=self.execute(Path(directory))
            self.assertEqual(result['status'],'pass');self.assertEqual(len(calls),3)

    def test_clean_failed_probe_retains_failure_and_collects_later_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            result,calls=self.execute(Path(directory),failed='arkui-components')
            self.assertEqual(result['status'],'fail');self.assertEqual(len(calls),3)
            self.assertIn('arkui-components',result['failures'][0])

    def test_unclean_probe_or_failed_policy_restoration_cannot_pass(self):
        for kwargs, count in (({'cleanup':False},2),({'restoration':False},3)):
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as directory:
                result,calls=self.execute(Path(directory),**kwargs)
                self.assertEqual(result['status'],'fail');self.assertEqual(len(calls),count)


if __name__=='__main__':unittest.main()
