"""Protect the exact GNSS component/bridge ownership and actual ABI dependency."""
import importlib.util,json,subprocess,shutil
from pathlib import Path
import unittest
import test_batch_system_sensor_installers as previous


def candidate(base):
    # Real fixture Git commits exercise both mandatory project checks. Their
    # synthetic revisions belong only to this private component copy; the
    # shipped manifest keeps both actual fixed OpenHarmony revisions unchanged.
    component=base/'fixed-gnss-component'
    shutil.copytree(previous.ROOT/'patches/common/device/qemu/external_gnss',component)
    root=base/'gnss';previous.prepare(root,previous.HERE/'fixtures/batch_system/external_gnss')
    manifest=json.loads((component/'manifest.json').read_text())
    for name in manifest['files']:(root/name).parent.mkdir(parents=True,exist_ok=True)
    for relative in manifest['projects']:
        project=root/relative;project.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','init','-q',str(project)],check=True)
        subprocess.run(['git','-C',str(project),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                        '-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null',
                        'commit','-qm','synthetic installer fixture','--allow-empty'],check=True)
        manifest['projects'][relative]=subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()
    manifest['revision']=manifest['projects'][manifest['project']]
    (component/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('gnss_apply',component/'apply.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    manifest,_=guard.load_manifest()
    return 'gnss',root,component,guard,manifest


class GnssInstallerTests(previous.ExactInstallerTests):
    def candidates(self):
        yield candidate(self.base)

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
