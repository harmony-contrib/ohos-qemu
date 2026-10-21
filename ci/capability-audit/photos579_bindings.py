"""Seven fixed callbacks on Root's same held OwnedIO; no resource creation."""
from pathlib import Path
import json
import time
from photos579_base_bindings import bind as original_bind
from photos579_raw import PROCESS_SCRIPT, processes, ref, need, checked
from photos579_project import bundle
from photos579_project import sources

KEYS = ('prepare_callers','install','start','input','collect','network','cleanup')


def bind(io):
    sources()
    callbacks = original_bind(io)
    folder = io.output / 'photos579-callbacks'; folder.mkdir(exist_ok=False)
    serial = 0
    records = []
    def actual_input(action,payload):
        if action!='recent-nonce-pixels': return callbacks['input'](action,payload)
        import re
        from guest_ui import select_node,bounds,NodeNotReady,LayoutNotReady
        from batch_media_verify_wallpaper_runtime import pixels
        need(set(payload)=={'binary','nonce'} and re.fullmatch('[a-f0-9]{32}',payload['nonce']),
            'fixed actually returned nonce image only')
        checked(payload['binary'])
        from photos579_receipts import nonce_image
        nonce_image(payload['binary'],payload['nonce'])
        at,qt=len(io.receipts),len(io.qmp_receipts)
        deadline=time.monotonic()+30;samples=[]
        while len(samples)<2:
            try:
                tree,path=io.ui.layout(label='photos579_recent_nonce')
                host=select_node(tree,bundle('photos','normal'),identifier='apps579-recent')
                hx,hy,hw,hh=host['rect'];frame=io.frame('photos579_recent_nonce')
                matches={}
                def visit(node,owner=''):
                    attrs=node['attributes'];owner=attrs.get('bundleName') or owner
                    if owner in ('com.ohos.photos',bundle('photos','normal')) and attrs.get('visible')=='true' and attrs.get('type')=='Image':
                        x,y,w,h=bounds(attrs['bounds'])
                        if x>=hx and y>=hy and x+w<=hx+hw and y+h<=hy+hh:
                            try: metrics=pixels(frame['path'],payload['binary']['path'],[x,y,w,h],minimum_fraction=.85)
                            except ValueError: pass
                            else: matches[(x,y,w,h)]=dict(attributes=attrs,bundle=owner,rect=[x,y,w,h],metrics=metrics)
                    for child in node.get('children',[]): visit(child,owner)
                for node in tree if type(tree) is list else [tree]: visit(node)
                need(len(matches)<=1,'ambiguous real Recent nonce image')
                if not matches: raise NodeNotReady('actual Recent nonce not rendered')
                node=next(iter(matches.values()));metrics=node.pop('metrics')
                destination=folder/('recent_layout_%04d.json'%len(records)+'_'+str(len(samples)))
                destination.write_text(json.dumps(tree,ensure_ascii=False,indent=2)+'\n')
                samples.append(dict(layout=ref(destination),original_layout=str(path),frame=frame,
                    host_node=host,selected_node=node,metrics=metrics))
            except (NodeNotReady,LayoutNotReady): samples=[]
            need(time.monotonic()<deadline,'actual Recent provider did not render fresh nonce')
            if len(samples)<2: time.sleep(.5)
        return dict(boot_id=io.boot_id,archive_sha256=io.archive_sha256,binary=payload['binary'],nonce=payload['nonce'],
            samples=samples,commands=[io.ref_receipt(row) for row in io.receipts[at:]],qmp_records=io.qmp_receipts[qt:])
    def retain(value):
        nonlocal serial
        serial += 1
        path = folder / ('callback_%05d.json' % serial)
        with path.open('x') as stream:
            json.dump(value,stream,indent=2); stream.write('\n')
        records.append(ref(path))
        return records[-1]
    def actual_network(action, parameters):
        need(parameters == {} and action in ('provider-snapshot','provider-stop'), 'two finite actual provider observations')
        at,qmp_at = len(io.receipts),len(io.qmp_receipts)
        if action == 'provider-stop':
            row = io.shell('aa force-stop com.ohos.photos -u 100','photos579_provider_stop')
            need(row['exit_code'] == 0, 'actual provider stop rejected')
            value = dict(stop=row['stdout_ref'])
        else:
            deadline=time.monotonic()+15
            while True:
                row=io.shell(PROCESS_SCRIPT,'photos579_processes',allow_failure=True)
                if row['exit_code']==0:
                    native=processes(row['stdout'],io.boot_id); break
                need(row['exit_code']==42 and time.monotonic()<deadline,'actual PID snapshot raced or failed')
            ams=io.shell('aa dump -a -u 100','photos579_provider_ams')
            bms=io.shell('bm dump -n com.ohos.photos -u 100','photos579_provider_bms')
            types=io.shell('param get const.bms.supportAppTypes','photos579_compatibility')
            from photos579_base_bindings import bms_json,objects
            import re
            paths=sorted({row['hapPath'] for row in objects(bms_json(bms['stdout'])) if
                type(row.get('hapPath')) is str and row['hapPath'].endswith('.hap')})
            need(0<len(paths)<=8 and all(re.fullmatch(r'/(?:data/app|system/app|system/app/com\.ohos\.photos)/[A-Za-z0-9_./-]+\.hap',path) and
                '..' not in Path(path).parts for path in paths),'finite actual BMS provider HAP paths')
            packages=[]
            for number,remote in enumerate(paths):
                destination=folder/('provider_%04d_%02d.hap'%(len(records),number))
                io.receive(remote,destination,'photos579_provider_hap')
                packages.append(dict(remote=remote,raw=ref(destination)))
            value=dict(processes=row['stdout_ref'],ams=ams['stdout_ref'],bms=bms['stdout_ref'],
                app_types=types['stdout_ref'],observed_processes=native,packages=packages)
        return dict(value,boot_id=io.boot_id,archive_sha256=io.archive_sha256,
            commands=[io.ref_receipt(row) for row in io.receipts[at:]],qmp_records=io.qmp_receipts[qmp_at:])
    def wrap(name):
        original=callbacks[name]
        def fixed(*args):
            at,qmp_at=len(io.receipts),len(io.qmp_receipts)
            value=dict(schema='actual-photos579-callback-cut/v1',name=name,case='photos',args=list(args),
                boot_id=io.boot_id,archive_sha256=io.archive_sha256,before_monotonic_ns=time.monotonic_ns(),
                result=None,error=None)
            try:
                result=actual_network(*args) if name=='network' else actual_input(*args) if name=='input' else original(*args)
                value['result']=result
                return result
            except BaseException as error:
                value['error']=dict(type=type(error).__name__,message=str(error)); raise
            finally:
                value.update(after_monotonic_ns=time.monotonic_ns(),
                    commands=[io.ref_receipt(row) for row in io.receipts[at:]],qmp_records=io.qmp_receipts[qmp_at:])
                retain(value)
        return fixed
    return {name:wrap(name) for name in KEYS}, records
