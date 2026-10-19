"""Mandatory registration must match the real suite producers, without resources."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]


def function(path,name):
    return next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name==name)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mandatory():
    values={}
    for n in ast.parse((ROOT/'scripts/verify_first_artifact_gate.py').read_text()).body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('REQUIRED_CHECKS','REPRESENTATIVE_CHECKS'):
            values[n.targets[0].id]=set(ast.literal_eval(n.value.args[0]))
        elif isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='REQUIRED_CHECKS':
            values['REQUIRED_CHECKS']|=set(ast.literal_eval(n.value.args[0]))
    return values['REQUIRED_CHECKS']|values['REPRESENTATIVE_CHECKS']


def registration_names():
    run=function(ROOT/'ci/capability-audit/run_packaged_qemu_suite.py','run')
    names={n.args[0].value for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and
           n.func.id=='check' and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str)}
    # These two actual bounded loops register check(persona)/check(family).
    for n in ast.walk(run):
        if not isinstance(n,ast.For):continue
        targets={x.id for x in ast.walk(n.target) if isinstance(x,ast.Name)}
        calls=[c for c in ast.walk(n) if isinstance(c,ast.Call) and isinstance(c.func,ast.Name) and c.func.id=='check' and
               isinstance(c.args[0],ast.Name) and c.args[0].id in targets]
        if not calls:continue
        bound={c.args[0].id for c in calls}
        if bound=={'family'}:
            source=ast.parse((ROOT/'ci/capability-audit/parallel_runtime_suite.py').read_text())
            names|=set(ast.literal_eval(next(x.value for x in source.body if isinstance(x,ast.Assign) and
                       any(isinstance(t,ast.Name) and t.id=='FAMILIES' for t in x.targets))))
        elif bound=={'persona'} and isinstance(n.target,ast.Tuple) and n.target.elts[0].id=='persona':
            names|={row.elts[0].value for row in n.iter.elts}
        else:raise AssertionError('unreviewed dynamic mandatory registration')
    return names


def normal_dispatch():
    source=ROOT/'ci/capability-audit/run_packaged_qemu_suite.py';run=function(source,'run')
    check=copy.deepcopy(next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='check'))
    loop=next(n for n in ast.walk(run) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and
        n.target.id=='persona' and isinstance(n.iter,ast.Name) and n.iter.id=='personas')
    body=next(n.body for n in loop.body if isinstance(n,ast.With))
    first=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and any(
        isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='normal_results' for t in n.targets))
    dispatch=ast.parse('def dispatch(persona,path,record):\n pass\n').body[0]
    dispatch.body=copy.deepcopy(body[first:])
    state=dict(report={'checks':{}},normal_results={},json=json,checksum=digest,save=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[check,dispatch],type_ignores=[])),str(source),'exec'),state)
    return state


class MandatoryRegistration(unittest.TestCase):
    def test_all_47_required_checks_have_actual_registration(self):
        required=mandatory();self.assertEqual(len(required),47)
        self.assertEqual(required-registration_names(),set())

    def test_audio_revoke_registers_original_raw_command_and_hash_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'evidence.json';path.write_text('{"status":"pass","scope":"MOCK"}')
            state=normal_dispatch();record={'argv':['MOCK-owned-producer'],'exit_code':0}
            state['dispatch']('audio-revoke',path,record)
            self.assertEqual(state['report']['checks'],{'audio-revoke':dict(status='pass',evidence=str(path),sha256=digest(path),commands=[record])})
            self.assertIs(state['report']['checks']['audio-revoke']['commands'][0],record)
            state['save'].assert_called_once_with()

    def test_failed_revoke_child_cannot_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'evidence.json';path.write_text('{"status":"fail"}')
            state=normal_dispatch()
            with self.assertRaisesRegex(ValueError,'child behavior verifier failed'):state['dispatch']('audio-revoke',path,{})
            self.assertEqual(state['report']['checks'],{})

    def test_unrelated_or_unknown_persona_does_not_create_revoke_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'evidence.json';path.write_text('{"status":"pass"}')
            for persona,expected in (('web','arkweb'),('rpc-runtime','rpc-runtime'),('unknown-MOCK',None)):
                with self.subTest(persona=persona):
                    state=normal_dispatch();state['dispatch'](persona,path,{'argv':['MOCK'],'exit_code':0})
                    self.assertEqual(set(state['report']['checks']),{expected} if expected else set())

    def test_original_final_gate_keeps_nonzero_bool_and_hash_rejections(self):
        source=ROOT/'scripts/verify_first_artifact_gate.py';verify=function(source,'verify')
        loop=next(n for n in ast.walk(verify) if isinstance(n,ast.For) and isinstance(n.iter,ast.Name) and n.iter.id=='required')
        guard=next(n for n in loop.body if isinstance(n,ast.If) and any(isinstance(x,ast.Constant) and
            x.value=='missing, changed or unsuccessful real behavior evidence: ' for x in ast.walk(n)))
        checked=ast.parse('def checked(record,path):\n pass\n').body[0]
        checked.body=[ast.parse("commands=record.get('commands',[])").body[0],copy.deepcopy(guard)]
        namespace=dict(checksum=digest,name='audio-revoke')
        exec(compile(ast.fix_missing_locations(ast.Module(body=[checked],type_ignores=[])),str(source),'exec'),namespace)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()/'evidence.json';p.write_text('MOCK')
            good=dict(status='pass',sha256=digest(p),commands=[dict(argv=['MOCK'],exit_code=0)])
            namespace['checked'](good,p)
            for code in (True,False,1,-9,None):
                bad=copy.deepcopy(good);bad['commands'][0]['exit_code']=code
                with self.subTest(code=code),self.assertRaises(ValueError):namespace['checked'](bad,p)
            bad=copy.deepcopy(good);bad['sha256']='0'*64
            with self.assertRaises(ValueError):namespace['checked'](bad,p)

    def payload(self):
        path=ROOT/'scripts/verify_first_artifact_gate.py';node=copy.deepcopy(function(path,'verified_payload'))
        tree=ast.parse(path.read_text())
        representative=next(n.value.args[0] for n in tree.body if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='REPRESENTATIVE_CHECKS' for t in n.targets))
        namespace=dict(json=json,Path=Path,sys=sys,checksum=digest,__file__=str(path),
            REPRESENTATIVE_CHECKS=frozenset(ast.literal_eval(representative)))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),namespace)
        return namespace['verified_payload']

    def test_original_gate_dispatches_exact_revoke_arguments_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()/'evidence.json';payload=dict(status='pass',archive_sha256='a'*64,boot_id='MOCK-boot')
            p.write_text(json.dumps(payload));identity=dict(sha256='a'*64,archive=str(Path(tmp).resolve()/'MOCK-archive'))
            env=dict(boot_id='MOCK-boot',guest_arch='arm64')
            import verify_audio_revoke_results as actual
            with patch.object(actual,'verify_evidence') as verifier:
                self.payload()('audio-revoke',p,identity,env)
                verifier.assert_called_once_with(payload,Path(identity['archive']),'MOCK-boot','arm64')
            with patch.object(actual,'verify_evidence',side_effect=ValueError('MOCK strict replay rejected')):
                with self.assertRaisesRegex(ValueError,'strict replay rejected'):self.payload()('audio-revoke',p,identity,env)

    def test_actual_strict_revoke_verifier_rejects_outer_pass_without_native_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp).resolve()/'MOCK-NOT-ARCHIVE';archive.write_bytes(b'SYNTHETIC')
            p=Path(tmp).resolve()/'evidence.json';p.write_text(json.dumps(dict(status='pass',persona='WRONG',
                archive_sha256=digest(archive),boot_id='MOCK-boot',arch='arm64',failures=[])))
            with self.assertRaisesRegex(ValueError,'ordinary active revoke'):
                self.payload()('audio-revoke',p,dict(sha256=digest(archive),archive=str(archive)),dict(boot_id='MOCK-boot',guest_arch='arm64'))


if __name__=='__main__':unittest.main()
