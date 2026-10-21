"""Finite clock-global control integration; Root keeps its original resources.

The caller explicitly supplies original bindings, source-admitted Coordinator
class and actual fixed Root clock admission. JSON cannot select an implementation.
"""
import inspect,re,shlex
from pathlib import Path
import control_session_global579 as session
from onset579_global_bridge import profile_from_config

def admit_input(spec,*,archive_sha256,profile,domain,bindings,inventory_io_ref):
    bindings.need(type(spec) is dict and set(spec)=={'actors','helpers','signer_dist','signer_jar','control404','onset579'},
                  'unchanged six AU keys; explicit global descriptor only')
    control=bindings.load(bindings.checked(spec['control404']))
    bindings.need(control['tools']==spec['onset579']['tools'],'one actual three-helper build for both global windows')
    return session.configuration(bindings.checked(spec['control404']),archive_sha256=archive_sha256,
        profile_descriptor=profile,domain=domain,inventory_io_ref=inventory_io_ref)

class CollectorAdapterGlobal579:
    """Only the concrete existing Coordinator can reach the original collector."""
    def __init__(self,collector,admitted,*,bindings,coordinator_type):
        self.b=bindings
        self.b.need(type(collector) is coordinator_type and inspect.getfile(coordinator_type) in self.b.verify_sources(),
               'fixed source-admitted original Coordinator projection required')
        self.c=collector;self.admitted=admitted
        self.args=collector.args;self.guest=collector.guest;self.env=collector.guest.env;self.remote=collector.remote
        self.value=collector.value;self.value['archive_sha256']=self.value['archive']['sha256']
        self.value.setdefault('received',[])
    def persist(self):return self.c.save()
    def observe(self,script,label):return self.c.observe(script,label)
    def shell(self,script,label):return self.c.shell(script,label)
    def command(self,argv,label):return self.c.command(argv,label)
    def receive(self,remote,label):
        value=self.c.receive(remote,label,uid=0)
        self.b.need(value['remote']==remote and value['uid']==0 and value['mode']==600,'actual root private CONTROL ledger required')
        self.value.setdefault('control480_downloads',[]).append(value);self.persist()
        return value['file']
    def stage(self,source,remote,uid,*,executable):
        expected={self.remote+'/control404':self.admitted.control,self.remote+'/status377':self.admitted.status}
        self.b.need(remote in expected and uid==0 and executable is True and self.b.checked(source)==expected[remote],'only original two fixed C tools may be staged')
        self.c.publish(expected[remote],remote,0)
        raw=self.c.observe('chmod 0700 '+remote+' && test "$(stat -c "%u %a" '+remote+')" = "0 700" && sha256sum '+remote,'480-fixed-tool-'+Path(remote).name)
        self.b.need(self.b.checked(raw).read_text().split()==[self.b.sha(expected[remote]),remote],'actual staged fixed native bytes differ')


class ThreeUIDWindowGlobal579:
    def __init__(self,collector,*,domain,bindings,coordinator_type,inventory_io_ref):
        self.b=bindings;self.domain=domain
        self.b.need(getattr(collector.args,'root_branch',None)=='owner403','480 window requires true current403 parent branch')
        self.b.need(not hasattr(collector,'control480'),'one finite480 window only')
        profile=profile_from_config(self.b.load(collector.args.root_config))
        admitted,inventory=admit_input(collector.inputs,archive_sha256=collector.value['archive']['sha256'],profile=profile,domain=domain,bindings=bindings,inventory_io_ref=inventory_io_ref)
        self.c=collector;self.adapter=CollectorAdapterGlobal579(collector,admitted,bindings=bindings,coordinator_type=coordinator_type)
        self.window=session.ControlWindowGlobal579(self.adapter,admitted,inventory,'owner-start-480',domain=domain)
        self.row=self.window.row;self.row['binding480']=dict(schema='threeuid-CONTROL-global579/v1',
          coordinator_run=collector.run,boot=collector.boot,config=collector.inputs['control404'],
          profile=profile,action_begin=len(collector.value['actions']),action_end=None,owner_start=None)
        self.row['binding480']['guest_begin']=len(collector.guest.report['commands'])
        from onset579_global_bridge import WindowGlobalAF579
        self.onset579=WindowGlobalAF579(collector,self.window,domain=domain,bindings=bindings)
    def begin(self):
        import actor377
        self.b.need(Path(actor377.__file__)==self.b.KIT/'actor377.py' and actor377.STATE is not None,'original live constructor proxy required')
        import subprocess
        self.b.need(subprocess.Popen is actor377.ProxyPopen,'fixed original root-retained constructor only')
        self.onset579.prepare()
        self.window.begin()
        self.row['constructor480']=dict(actor=actor377.STATE['actor'],handles={
          name:dict(handle=getattr(child,'_handle'),pid=child.pid) for name,child in
          (('control',self.window.control),('status',self.window.status))})
        self.onset579.begin()
        self.row['binding480']['guest_armed']=len(self.c.guest.report['commands'])
        self.c.save();return self
    def owner_start(self,item):
        bind=self.row['binding480']
        self.b.need(item is self.c.value['actions'][bind['action_begin']] and item['role']=='owner' and item['action']=='start','actual first owner Start action required')
        self.b.need(bind['owner_start'] is None,'one owner Start binding')
        bind['owner_start']=dict(operation=item['operation'],request=item['request'],control_interval_ns=item['control_interval_ns'])
        self.onset579.owner_start()
        self.c.save()
    def finish(self):
        bind=self.row['binding480'];bind['action_end']=len(self.c.value['actions'])
        bind['guest_finish_begin']=len(self.c.guest.report['commands']);self.c.save()
        self.onset579.finish()
        self.onset579.dispose_files()
        self.window.finish()  # Original: sampler death/proc absence BEFORE DISARM.
        self.window.dispose_files()  # Quiescence first; public Stop/Release follows.
        bind['guest_finish_end']=len(self.c.guest.report['commands'])
        self.row['files_disposed480']=True;self.c.save()


class ControlSourcePolicyGlobal579:
    """One source-site-only addition, never a new Python/delegate entry.

    Original Policy still validates every actual tool/environment/cwd/argv.
    Root entry and pure admission/verifier libraries are absent from actors.
    """
    def __init__(self,original,*,bindings):
        self.b=bindings
        self.original=original;self.sources=original.sources
        import ast
        path=Path(session.__file__);tree=ast.parse(path.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ControlWindowGlobal579')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='spawn')
        calls=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
          isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='Popen']
        self.b.need(len(calls)==1,'one original412 raw native constructor')
        self.session_site=dict(path=str(path),sha256=self.b.sha(path),line=calls[0].lineno)
    def __getattr__(self,name):return getattr(self.original,name)
    def source_site(self,row):
        if row.get('path')==self.session_site['path']:
            self.b.need(row==self.session_site,'only the original exact412 native spawn site')
        return self.original.source_site(row)
    def child(self,argv,environment,cwd,owner):
        kind,entry=self.original.child(argv,environment,cwd,owner)
        self.b.need(entry!=self.session_site['path'],'native constructor source is not a Python/delegate actor entry')
        return kind,entry


def connect_native_source(children,coordinator,pins,*,bindings):
    b=bindings
    b.need(type(children.policy).__name__=='Policy' and Path(inspect.getfile(type(children.policy)))==b.KIT/'policy377.py',
      'original unwrapped current469 Policy required')
    b.need(str(b.HERE/'owner_entry414.py') not in children.policy.sources,'root-only library must not be an actor entry')
    fixed={str(path):pins[str(path)] for path in (coordinator,Path(session.__file__))}
    children.policy.sources=dict(children.policy.sources,**fixed)
    children.policy=ControlSourcePolicyGlobal579(children.policy,bindings=bindings)
    return fixed
