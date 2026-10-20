#!/usr/bin/env python3
"""Finite exact-source installer boundaries. No SDK, npm, compiler or guest."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest

R=Path(__file__).resolve().parents[2]
REL=Path('patches/common/third_party/jsframework/native_test_bridge')
C=R/REL
HELPERS={'apply_exact_component.py':'be60d0be4e741af2768f1936779f94aac5d778cd2d627db898353b3b3d47cc65','exact_source_states.py':'d876f46528b81323414866a97987ac72d82a5b7e748cddda8d8fef01e239e1a2'}
def digest(x):return hashlib.sha256(x).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Source496(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='js496-',dir=tempfile.gettempdir());self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.root=self.work/'source';self.root.mkdir()
        self.program=self.work/'program';self.component=self.program/REL
        shutil.copytree(C,self.component)
        for name,sha in HELPERS.items():
            raw=(R/'patches/lib'/name).read_bytes();self.assertEqual(digest(raw),sha)
            p=self.program/'patches/lib'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.m=load('js496_'+self.work.name.replace('-','_'),self.component/'verify_source.py')
        self.write('original')
        self.tmp=self.work/'temporary';self.tmp.mkdir()
        self.env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',TMPDIR=str(self.tmp),GIT_CEILING_DIRECTORIES=str(self.work),GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null')
        self.commands=[]
        self.addCleanup(self.no_git)
    def no_git(self):
        self.assertEqual(list(self.work.rglob('.git')),[])
        self.assertEqual(list(self.work.rglob('index')),[])
        self.assertEqual(list(self.work.rglob('HEAD')),[])
    def write(self,state):
        for name,_,_ in self.m.FILES:
            p=self.root/self.m.PROJECT/name;p.parent.mkdir(parents=True,exist_ok=True)
            if p.is_symlink():p.unlink()
            if p.is_dir():shutil.rmtree(p)
            p.write_bytes((self.component/'fixtures'/state/self.m.PROJECT/name).read_bytes())
    def snapshot(self):
        result={}
        for p in self.root.rglob('*'):
            if p.is_symlink():result[str(p.relative_to(self.root))]=('link',os.readlink(p))
            elif p.is_file():result[str(p.relative_to(self.root))]=('file',digest(p.read_bytes()),p.stat().st_nlink)
            else:result[str(p.relative_to(self.root))]=('directory',)
        return result
    def run_command(self,argv,success=True):
        p=subprocess.run(argv,capture_output=True,text=True,env=self.env,timeout=20)
        self.commands.append(dict(argv=argv,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
        self.assertEqual(p.returncode==0,success,p.stdout+p.stderr)
        return p
    def entry(self,success=True,extra=()):
        return self.run_command(['/bin/bash',str(self.component/'apply.sh'),'--source-root',str(self.root),*extra],success)
    def refuse_entry_unchanged(self):
        before=self.snapshot();self.entry(False);self.assertEqual(before,self.snapshot())
    def test_01_actual_revision_metadata_and_fixtures(self):
        lock=json.loads((R/'scripts/openharmony_7_0_release_source_lock.json').read_bytes())
        projects=[x for x in lock['projects'] if x['path']=='third_party/jsframework']
        self.assertEqual(len(projects),1);self.assertEqual(projects[0]['revision'],self.m.REVISION)
        self.m.metadata();self.assertEqual(len(self.m.FILES),2)
        for name,b,a in self.m.FILES:
            for state,expected in [('original',b),('final',a)]:self.assertEqual(digest((self.component/'fixtures'/state/self.m.PROJECT/name).read_bytes()),expected)
    def test_02_before_and_require_final(self):
        self.assertFalse(self.m.validate(self.root))
        with self.assertRaises(ValueError):self.m.validate(self.root,True)
    def test_03_real_apply_final_repeat_and_cli_false_gates(self):
        self.entry();self.assertTrue(self.m.validate(self.root,True));before=self.snapshot();self.entry();self.assertEqual(before,self.snapshot())
        p=self.run_command([sys.executable,'-B',str(self.component/'verify_source.py'),'--source-root',str(self.root),'--require-patched'])
        v=json.loads(p.stdout);self.assertTrue(v['patched'])
        for key in ['compiled','native_linux_mocha_passed','runtime_passed','first_artifact_behavior_gate_passed']:self.assertIs(v[key],False)
    def test_04_each_unknown_rejects_before_write(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');p=self.root/self.m.PROJECT/name;p.write_bytes(p.read_bytes()+b'\nUNREVIEWED\n');self.refuse_entry_unchanged()
    def test_05_each_missing_rejects_before_write(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');(self.root/self.m.PROJECT/name).unlink();self.refuse_entry_unchanged()
    def test_06_each_mixed_state_rejects(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');(self.root/self.m.PROJECT/name).write_bytes((self.component/'fixtures/final'/self.m.PROJECT/name).read_bytes());self.refuse_entry_unchanged()
    def test_07_each_leaf_symlink_rejects(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');p=self.root/self.m.PROJECT/name;target=self.work/'foreign';target.write_bytes(p.read_bytes());p.unlink();p.symlink_to(target);self.refuse_entry_unchanged();p.unlink();target.unlink()
    def test_08_parent_symlink_rejects(self):
        p=self.root/self.m.PROJECT/'test';dest=self.work/'foreign-dir';p.rename(dest);p.symlink_to(dest,target_is_directory=True);self.refuse_entry_unchanged()
    def test_09_each_hardlink_rejects(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');p=self.root/self.m.PROJECT/name;target=self.work/'foreign';target.write_bytes(p.read_bytes());p.unlink();os.link(target,p);self.refuse_entry_unchanged();p.unlink();target.unlink()
    def test_10_each_nonregular_rejects(self):
        for name,_,_ in self.m.FILES:
            with self.subTest(name=name):
                self.write('original');p=self.root/self.m.PROJECT/name;p.unlink();p.mkdir();self.refuse_entry_unchanged()
    def test_11_wrong_revision_metadata_rejects(self):
        p=self.component/'source_states.json';v=json.loads(p.read_bytes());v['revision']='0'*40;p.write_text(json.dumps(v));self.refuse_entry_unchanged()
    def test_12_duplicate_metadata_rejects(self):
        p=self.component/'source_states.json';raw=p.read_text();p.write_text(raw.replace('{','{"project":"foreign",',1));self.refuse_entry_unchanged()
    def test_13_foreign_patch_rejects(self):
        p=self.component/self.m.PATCH;p.write_bytes(p.read_bytes()+b'\n# FOREIGN\n');self.refuse_entry_unchanged()
    def test_14_extra_numbered_patch_rejects(self):
        (self.component/'0002-foreign.patch').write_text('FOREIGN\n');self.refuse_entry_unchanged()
    def test_15_metadata_symlink_rejects(self):
        p=self.component/'source_states.json';dest=self.work/'foreign-metadata';dest.write_bytes(p.read_bytes());p.unlink();p.symlink_to(dest);self.refuse_entry_unchanged()
    def test_16_fixed_entry_rejects_component_override(self):
        before=self.snapshot();self.entry(False,['--component-dir',str(self.work/'foreign-component')]);self.assertEqual(before,self.snapshot())
    def test_17_original_generic_stage_only_managed_pair(self):
        helper=load('generic_stage496',self.program/'patches/lib/apply_exact_component.py')
        staged=self.work/'stage';staged.mkdir()
        from unittest.mock import patch
        before=self.snapshot()
        with patch.dict(os.environ,self.env,clear=True):
            patches=helper.prepare_stack(self.root,self.component,self.m,staged)
        self.assertEqual(len(patches),1);self.assertEqual(before,self.snapshot())
        self.assertTrue(self.m.validate(staged/'source',True))
        targets={str(p.relative_to(staged/'source')) for p in (staged/'source').rglob('*') if p.is_file()}
        self.assertEqual(targets,{str(Path(self.m.PROJECT)/name) for name,_,_ in self.m.FILES})
    def test_18_real_private_patch_reverse(self):
        self.entry()
        for options in [['--check'],[]]:self.run_command(['git','-C',str(self.root),'apply','-R',*options,str(self.component/self.m.PATCH)])
        self.assertFalse(self.m.validate(self.root))
        for name,b,_ in self.m.FILES:self.assertEqual(digest((self.root/self.m.PROJECT/name).read_bytes()),b)
        self.entry();self.assertTrue(self.m.validate(self.root,True))
    def test_19_bash_syntax(self):
        self.run_command(['/bin/bash','-n',str(self.component/'apply.sh')])

if __name__=='__main__':unittest.main()
