"""Exact inherited environments and real two-way measured breakpoint boundaries."""
import json
import math
from pathlib import Path
import re
from PIL import Image
from build_arkui_env_reader_probe import BUNDLE, CONTRACTS
from guest_ui import select_node, NodeNotReady

ENV_PHASES = ('initial','updated','font-reset','removed')
# Native height breakpoints use height / width, including equality.
READER_STEPS = (
    ('initial','env-reader-reader',2,[180,120,1,0]),
    ('resized','env-reader-resize',3,[280,300,2,1]),
    ('restored','env-reader-restore',4,[180,120,1,0]),
    ('below','env-reader-below',6,[199,120,1,0]),
    ('at','env-reader-at',7,[200,120,2,0]),
    ('ratio-sm-below','env-reader-ratio-sm-below',8,[200,159,2,0]),
    ('ratio-sm-at','env-reader-ratio-sm-at',9,[200,160,2,1]),
    ('ratio-lg-below','env-reader-ratio-lg-below',10,[200,249,2,1]),
    ('ratio-lg-at','env-reader-ratio-lg-at',11,[200,250,2,2]),
    ('xs-below','env-reader-xs-below',12,[99,120,0,1]),
    ('xs-at','env-reader-xs-at',13,[100,80,1,1]),
    ('lg-at','env-reader-lg-at',14,[300,240,3,1]),
    ('xl-at','env-reader-xl-at',15,[400,250,4,0]),
)


def rows(text, nonce, uid):
    if re.fullmatch('[0-9a-f]{32}',nonce or '') is None or type(uid) is not int or uid//200000!=100:
        raise ValueError('actual ordinary environment/reader caller required')
    observed = [json.loads(line) for line in text.splitlines() if line]
    requests = {'env.update.request','env.font.reset.request','reader.resize.request','reader.restore.request',
                *('reader.'+name+'.request' for name,_,_,_ in READER_STEPS[3:])}
    allowed = {'identity','density','env.outer','env.inner','env.outside','modifier.reader','reader.native','remove.request',*requests}
    for row in observed:
        if (set(row)!={'runId','family','cycle','phase','name','values','data'} or row['runId']!=nonce or
                row['family'] not in ('env','reader') or type(row['cycle']) is not int or row['cycle'] not in (0,1) or
                type(row['phase']) is not int or row['phase'] not in (0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15) or
                row['name'] not in allowed or not isinstance(row['values'],list) or type(row['data']) is not str):
            raise ValueError('failed, foreign or malformed environment/reader journal')
        name, values = row['name'],row['values']
        if name=='identity':
            if len(values)!=3 or any(type(v) is not int for v in values) or values[:2]!=[uid,uid] or values[2]<=0 or row['data']:
                raise ValueError('environment/reader PID differs from its ordinary installed caller')
        elif name=='density':
            if len(values)!=1 or type(values[0]) not in (int,float) or not .25<=values[0]<=8 or row['data']:
                raise ValueError('actual owning UIContext density missing')
        elif name.startswith('env.') and name not in requests:
            if (row['family']!='env' or len(values)!=2 or values[0] not in ('Ltr','Rtl','Auto') or
                    type(values[1]) not in (int,float) or not math.isfinite(values[1]) or not .1<=values[1]<=8):
                raise ValueError('native inherited environment or unconfigured font fallback failed')
        elif name=='reader.native':
            if (row['family']!='reader' or len(values)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values) or
                    not 0<=values[0]<=400 or not 0<=values[1]<=300 or
                    type(values[2]) is not int or not 0<=values[2]<=4 or type(values[3]) is not int or not 0<=values[3]<=2 or row['data']):
                raise ValueError('native reader dimensions or breakpoint indexes escaped bounds')
        elif name=='modifier.reader':
            if row['family']!='reader' or values!=[1,1] or row['data']: raise ValueError('reader inherited reset or chain failed')
        elif values!=[1] or row['data']: raise ValueError('environment/reader UI action failed')
    return observed


def environment(phase, label):
    if label=='inner': return ['Rtl',1],'inner-fixed'
    if label=='outside': return ['Auto',1],'unset'
    return (['Ltr',1],'outer-0') if phase=='initial' else (['Rtl',1.5 if phase=='updated' else 1],'outer-1')


def verify(text, nonce, uid):
    observed = rows(text,nonce,uid); pids = []; densities = []
    groups = [('env',0),('env',1),('reader',0),('reader',1)]
    ranks = {key:i for i,key in enumerate(groups)}
    if not observed or [ranks[(r['family'],r['cycle'])] for r in observed] != sorted(ranks[(r['family'],r['cycle'])] for r in observed):
        raise ValueError('both independent environment and reader creations must remain ordered')
    for family,cycle in groups:
        events = [r for r in observed if (r['family'],r['cycle'])==(family,cycle)]
        def one(name):
            found = [(i,r) for i,r in enumerate(events) if r['name']==name]
            if len(found)!=1: raise ValueError('one actual environment/reader event required: '+name)
            return found[0]
        identity_index,ident = one('identity');density_index,density = one('density');removed,_ = one('remove.request')
        if not identity_index==0<density_index<removed==len(events)-1:
            raise ValueError('environment/reader identity/removal ordering or late callback failed')
        pids.append(ident['values'][2]);densities.append(density['values'][0])
        if family=='env':
            update,_ = one('env.update.request');reset,_ = one('env.font.reset.request')
            if not density_index<update<reset<removed: raise ValueError('environment update/reset order differs')
            for phase,number,first,last in (('initial',0,density_index,update),('updated',1,update,reset),('font-reset',5,reset,removed)):
                for label in ('outer','inner','outside'):
                    found = [r for r in events[first+1:last] if r['name']=='env.'+label]
                    values,data = environment(phase,label)
                    if not found or any(r['phase']!=number or r['values']!=values or r['data']!=data for r in found):
                        raise ValueError('native '+phase+' inherited or isolated '+label+' environment differs')
        else:
            if not any(r['name']=='modifier.reader' and r['phase']==2 for r in events): raise ValueError('real reader factory not reset on recreation')
            request_indices = [density_index]
            for name,_,_,_ in READER_STEPS[1:]:
                request_name = 'reader.'+({'resized':'resize','restored':'restore'}.get(name,name))+'.request'
                request_indices.append(one(request_name)[0])
            request_indices.append(removed)
            if request_indices!=sorted(request_indices): raise ValueError('reader breakpoint action order differs')
            for index,(name,_,number,expected) in enumerate(READER_STEPS):
                first,last = request_indices[index:index+2]
                callbacks = [r for r in events[first+1:last] if r['name']=='reader.native']
                if not callbacks or any(r['phase']!=number for r in callbacks) or callbacks[-1]['values']!=expected:
                    raise ValueError('native reader '+name+' two-way measurement or equality boundary failed')
    if len(set(pids))!=1 or len(set(densities))!=1: raise ValueError('reader/environment recreation changed process or UIContext')
    return list(CONTRACTS)


def pixels(screenshot, layout, nonce, family, cycle, phase, density):
    with Image.open(screenshot) as source:
        if source.format!='PNG': raise ValueError('actual environment/reader compositor PNG required')
        image = source.convert('RGB')
    nodes = [select_node(layout,BUNDLE,identifier='env-reader-ready'),select_node(layout,BUNDLE,identifier='env-reader-state')]
    if (nodes[0]['attributes']['text']!=nonce or nodes[1]['attributes']['text']!=
            ('removed ' if phase=='removed' else 'active ')+family+' '+nonce+':'+str(cycle)):
        raise NodeNotReady('actual challenged environment/reader scene not presented')
    metrics = []; fingerprints = []
    if phase=='removed':
        for identifier in ('env-reader-factory','env-reader-native-marker',
                           'env-reader-outer-marker','env-reader-inner-marker','env-reader-outside-marker'):
            try: select_node(layout,BUNDLE,identifier=identifier)
            except NodeNotReady: continue
            raise ValueError('removed environment/reader retained a visible scene')
    elif family=='env':
        for label in ('outer','inner','outside'):
            values,data = environment(phase,label)
            marker = select_node(layout,BUNDLE,identifier='env-reader-'+label+'-marker')
            expected = nonce+':'+label+':'+data+':'+values[0]+':'+str(values[1])
            if marker['attributes']['text']!=expected: raise NodeNotReady('native environment marker does not match current inherited values')
            nodes.append(marker)
            a = select_node(layout,BUNDLE,identifier='env-reader-'+label+'-a')
            b = select_node(layout,BUNDLE,identifier='env-reader-'+label+'-b')
            if (a['rect'][0]<b['rect'][0]) is not (values[0]!='Rtl'):
                raise ValueError('actual child row did not follow inherited direction')
            # Saturated markers keep color management out of the layout check.
            for node,color in ((a,(255,0,0)),(b,(0,255,0))):
                x,y,w,h = node['rect'];crop = image.crop((x,y,x+w,y+h));colors = list(crop.get_flattened_data())
                # Captured 8-bit screenshots round-trip the green primary to
                # (2,255,0). Bound only this quantization; geometry, challenged
                # text, pixel counts and all stable-frame checks remain exact.
                painted = sum(max(abs(c[i]-color[i]) for i in range(3))<=2 for c in colors)
                dark = sum(max(c)<110 for c in colors)
                if painted<300 or dark<20: raise ValueError('actual environment child color or text not presented')
                metrics.append(dict(rect=node['rect'],background_pixels=painted,dark_pixels=dark))
                fingerprints.extend([str(node['rect']).encode(),crop.tobytes()])
    else:
        expected = next(row[3] for row in READER_STEPS if row[0]==phase)
        factory = select_node(layout,BUNDLE,identifier='env-reader-factory')
        if abs(factory['rect'][2]-expected[0]*density)>1.01 or abs(factory['rect'][3]-expected[1]*density)>1.01:
            raise ValueError('actual native reader geometry does not match its measured dimensions')
        marker = select_node(layout,BUNDLE,identifier='env-reader-native-marker')
        if marker['attributes']['text']!=nonce+':reader:'+':'.join(map(str,expected)):
            raise NodeNotReady('actual reader marker has not reached its native breakpoint boundary')
        nodes.append(marker)
    for node in nodes:
        x,y,w,h = node['rect']
        if x+w>image.width or y+h>image.height: raise ValueError('environment/reader compositor marker off-screen')
        crop = image.crop((x,y,x+w,y+h));dark = sum(max(c)<110 for c in crop.get_flattened_data())
        if dark<20: raise ValueError('actual environment/reader challenged text not painted')
        metrics.append(dict(rect=node['rect'],dark_pixels=dark));fingerprints.extend([str(node['rect']).encode(),crop.tobytes()])
    return metrics,b''.join(fingerprints)


def verify_presentations(phases, nonce, density):
    expected = {family+':'+str(cycle)+':'+phase for family,labels in
                (('env',ENV_PHASES),('reader',(*[r[0] for r in READER_STEPS],'removed'))) for cycle in (0,1) for phase in labels}
    if set(phases)!=expected: raise ValueError('all inherited environments and breakpoint boundaries must be presented twice')
    for key,record in phases.items():
        family,cycle,phase = key.split(':');samples = record['presentation']['samples']
        if record['presentation']['status']!='pass_presentation_only' or len(samples)<3:
            raise ValueError('three actual stable environment/reader frames missing')
        final = []
        for sample in samples[-3:]:
            actual,fingerprint = pixels(sample['screenshot'],json.loads(Path(sample['layout']).read_text()),nonce,family,int(cycle),phase,density)
            if actual!=sample['metrics']: raise ValueError('environment/reader compositor metrics changed')
            final.append(fingerprint)
        if len(set(final))!=1: raise ValueError('three consecutive identical environment/reader presentations required')
    return True
