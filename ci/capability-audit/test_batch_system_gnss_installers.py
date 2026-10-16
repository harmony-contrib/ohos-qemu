"""Protect the exact GNSS component/bridge ownership and actual ABI dependency."""
import importlib.util,json,subprocess
from pathlib import Path
import unittest
import test_batch_system_sensor_installers as previous

class GnssInstallerTests(previous.ExactInstallerTests):
    def candidates(self):
        component=previous.ROOT/'patches/common/device/qemu/external_gnss'
        root=self.base/'gnss';previous.prepare(root,previous.HERE/'fixtures/batch_system/external_gnss')
        spec=importlib.util.spec_from_file_location('gnss_apply',component/'apply.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        manifest,_=guard.load_manifest()
        for name in manifest['files']:(root/name).parent.mkdir(parents=True,exist_ok=True)
        yield 'gnss',root,component,guard,manifest

    def test_actual_vendor_header_dependency_preserved(self):
        _,root,_,guard,manifest=next(self.candidates())
        header=root/next(iter(manifest['dependencies']));header.write_bytes(header.read_bytes()+b'// foreign ABI\n')
        before=header.read_bytes()
        with self.assertRaisesRegex(ValueError,'actual ABI dependency'):guard.apply(root)
        self.assertEqual(header.read_bytes(),before)

    def test_fixed_device_project_revision_required(self):
        _,root,_,guard,manifest=next(self.candidates())
        project=root/'device/qemu';subprocess.run(['git','init','-q',str(project)],check=True)
        subprocess.run(['git','-C',str(project),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                        'commit','-qm','fixture','--allow-empty'],check=True)
        before=self.snapshot(root,manifest)
        with self.assertRaisesRegex(ValueError,'source project revision'):guard.apply(root)
        self.assertEqual(self.snapshot(root,manifest),before)

if __name__=='__main__':unittest.main()
