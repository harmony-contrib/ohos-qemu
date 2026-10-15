"""Strict actual lazy waterflow/dynamic callbacks, layout changes and painted views."""
import json
import re
from pathlib import Path
from PIL import Image
from build_arkui_lazy_layouts_probe import BUNDLE, CONTRACTS
from guest_ui import select_node, NodeNotReady


def rows(text, nonce, uid):
    if re.fullmatch('[0-9a-f]{32}',nonce or '') is None or type(uid) is not int or uid<20000000:
        raise ValueError('actual ordinary lazy-layout caller identity required')
    result=[json.loads(line) for line in text.splitlines() if line]
    allowed={'identity','create.request','modifier.water.reset','modifier.water','modifier.dynamic.reset',
        'modifier.dynamic','visible.water','visible.dynamic','algorithm.measure','algorithm.layout',
        'algorithm.no-helper','change.request','scroll.request.last','scroll.request.first','remove.request'}
    allowed.update(('nodes.change.before','nodes.change.after'))
    for row in result:
        if (set(row)!={'runId','kind','cycle','name','values','error'} or row['runId']!=nonce or
            row['kind'] not in ('water','dynamic') or type(row['cycle']) is not int or row['cycle'] not in (0,1) or
            row['name'] not in allowed or row['error']!='' or not isinstance(row['values'],list) or
            any(type(value) is not int for value in row['values'])):
            raise ValueError('failed, foreign, or malformed real lazy-layout journal')
        values=row['values'];name=row['name']
        if name=='identity':
            if len(values)!=3 or values[:2]!=[uid,uid] or values[2]<=0:raise ValueError('ordinary native lazy-layout UID/PID differs')
        elif name=='visible.water':
            if row['kind']!='water' or len(values)!=2 or not 0<=values[0]<=values[1]<40:raise ValueError('waterflow visible range escaped item bounds')
        elif name=='visible.dynamic':
            if row['kind']!='dynamic' or not values or values!=sorted(set(values)) or min(values)<0 or max(values)>=40:
                raise ValueError('dynamic visible indices escaped real item bounds')
        elif name.startswith('nodes.'):
            if len(values)!=2 or min(values)<=0:raise ValueError('actual child/factory frame identities missing')
        elif name.startswith('algorithm.'):
            if row['kind']!='dynamic' or len(values)<2 or values[0] not in (40,60) or values[1]!=40:
                raise ValueError('custom lazy algorithm did not measure its real children')
            if name=='algorithm.measure' and (len(values)!=6 or values[3]<=values[2] or values[4] not in (0,1) or not 0<=values[5]<40):
                raise ValueError('real scroll helper measurement/axis/inactive range invalid')
            if name!='algorithm.measure' and len(values)!=2:raise ValueError('native layout callback shape differs')
        elif values!=[1]:raise ValueError('real lazy modifier chain or action failed')
    return result


def verify(text, nonce, uid):
    observed=rows(text,nonce,uid)
    groups=[('water',0),('water',1),('dynamic',0),('dynamic',1)]
    if not observed or [(row['kind'],row['cycle']) for row in observed]!=sorted(
        [(row['kind'],row['cycle']) for row in observed],key=groups.index):
        raise ValueError('both ordered creation cycles of both native lazy factories required')
    pids=[]
    for kind,cycle in groups:
        values=[row for row in observed if (row['kind'],row['cycle'])==(kind,cycle)]
        indices={}
        for name in ('identity','create.request','change.request','scroll.request.last','scroll.request.first','remove.request'):
            matches=[index for index,row in enumerate(values) if row['name']==name]
            if len(matches)!=1:raise ValueError('one real '+name+' per lazy factory cycle required')
            indices[name]=matches[0]
        if list(indices.values())!=sorted(indices.values()) or indices['identity']!=0 or indices['remove.request']!=len(values)-1:
            raise ValueError('lazy creation/change/scroll/removal order or late callback failed')
        pids.append(values[0]['values'][2])
        identities=[]
        for name in ('nodes.change.before','nodes.change.after'):
            actual=[row['values'] for row in values if row['name']==name]
            if len(actual)!=1:raise ValueError('both actual native child/factory identities required')
            identities.append(actual[0])
        if identities[0]!=identities[1]:raise ValueError('native layout change replaced the child/factory frame nodes')
        for name in ('modifier.'+kind+'.reset','modifier.'+kind):
            modifier=[index for index,row in enumerate(values) if row['name']==name]
            if not modifier or not indices['create.request']<modifier[0]<indices['change.request']:
                raise ValueError('actual typed lazy factory modifier/reset missing')
        for first,last,boundary in (('create.request','change.request','top'),('change.request','scroll.request.last','top'),
                                   ('scroll.request.last','scroll.request.first','bottom'),('scroll.request.first','remove.request','top')):
            callbacks=[row['values'] for row in values[indices[first]+1:indices[last]] if row['name']=='visible.'+kind]
            if not callbacks:raise ValueError('real '+kind+' '+boundary+' callback missing')
            actual=callbacks[-1]
            if boundary=='top' and actual[0]!=0:raise ValueError('native lazy callback failed top boundary')
            if boundary=='bottom' and actual[-1]!=39:raise ValueError('native lazy callback failed last item boundary')
        if kind=='dynamic':
            for step in (40,60):
                if not any(row['name']=='algorithm.measure' and row['values'][0]==step for row in values) or not any(
                    row['name']=='algorithm.layout' and row['values'][0]==step for row in values):
                    raise ValueError('both actual lazy algorithm measure/layout implementations required')
            if not any(row['name']=='algorithm.measure' and row['values'][2]>0 for row in values):
                raise ValueError('lazy algorithm helper never observed actual scrolling')
    if len(set(pids))!=1:raise ValueError('lazy factory recreation changed caller process')
    return list(CONTRACTS)


def pixels(screenshot,layout,nonce,kind,cycle,phase):
    with Image.open(screenshot) as source:
        if source.format!='PNG':raise ValueError('actual lazy compositor PNG required')
        image=source.convert('RGB')
    if phase=='removed':
        node=select_node(layout,BUNDLE,text='removed '+nonce+':'+str(cycle+1))
        for index in range(40):
            try:select_node(layout,BUNDLE,identifier='lazy-layouts-item-'+str(index))
            except NodeNotReady:continue
            raise ValueError('removed lazy factory retained visible children')
        if sum(color in ((221,238,255),(170,204,221)) for color in image.getdata())>100:
            raise ValueError('removed lazy factory retained painted children')
        nodes=[node];items=[]
    else:
        items=[39] if phase=='bottom' else [0,1,2]
        nodes=[select_node(layout,BUNDLE,text=nonce+':'+str(index)) for index in items]
        for index,node in zip(items,nodes):
            if node['attributes'].get('id')!='lazy-layouts-item-'+str(index):raise ValueError('foreign lazy item node')
        if kind=='water' and phase!='bottom':
            a,b,c=[node['rect'] for node in nodes]
            if not a[0]<b[0] or a[1]!=b[1]:raise ValueError('native waterfall did not lay out actual columns')
            if phase=='initial' and not c[1]>a[1]:raise ValueError('native initial waterfall did not use two columns')
            if phase in ('changed','top') and (not b[0]<c[0] or c[1]!=a[1]):raise ValueError('native waterfall did not change to three columns')
        if kind=='dynamic' and phase!='bottom':
            a,b,c=[node['rect'] for node in nodes]
            if not a[0]==b[0]==c[0] or not a[1]<b[1]<c[1]:raise ValueError('native custom lazy algorithm did not lay out children')
    metrics=[];fingerprint=[]
    for offset,node in enumerate(nodes):
        x,y,w,h=node['rect']
        if x+w>image.width or y+h>image.height:raise ValueError('lazy child offscreen')
        crop=image.crop((x,y,x+w,y+h));colors=list(crop.getdata());dark=sum(max(color)<90 for color in colors)
        if dark<25:raise ValueError('actual lazy challenged text pixels not presented')
        background=None
        if phase!='removed':
            item=items[offset];rgb=(221,238,255) if item%2==0 else (170,204,221)
            background=sum(color==rgb for color in colors)
            if background<100:raise ValueError('actual lazy child color not presented')
        metrics.append(dict(rect=node['rect'],dark_pixels=dark,item_background_pixels=background))
        fingerprint.extend([str(node['rect']).encode(),crop.tobytes()])
    return metrics,b''.join(fingerprint)


def verify_presentations(phases,nonce):
    expected={kind+':'+str(cycle)+':'+phase for kind in ('water','dynamic') for cycle in (0,1)
              for phase in ('initial','changed','bottom','top','removed')}
    if set(phases)!=expected:raise ValueError('both real lazy factories require all change/scroll/removal/recreation views')
    for key,record in phases.items():
        kind,cycle,phase=key.split(':');presentation=record['presentation'];samples=presentation['samples']
        if presentation['status']!='pass_presentation_only' or len(samples)<3:raise ValueError('stable actual lazy presentation missing')
        stable=[]
        for sample in samples[-3:]:
            metrics,fingerprint=pixels(sample['screenshot'],json.loads(Path(sample['layout']).read_text()),nonce,kind,int(cycle),phase)
            if metrics!=sample['metrics']:raise ValueError('lazy layout compositor metrics changed')
            stable.append(fingerprint)
        if len(set(stable))!=1:raise ValueError('three actual consecutive stable lazy frames required')
    for kind in ('water','dynamic'):
        for cycle in (0,1):
            before=phases[kind+':'+str(cycle)+':initial']['presentation']['samples'][-1]['metrics']
            after=phases[kind+':'+str(cycle)+':changed']['presentation']['samples'][-1]['metrics']
            if kind=='water' and after[0]['rect'][2]>=before[0]['rect'][2]:raise ValueError('native column-count update never changed measured child width')
            if kind=='dynamic':
                first=before[1]['rect'][1]-before[0]['rect'][1];second=after[1]['rect'][1]-after[0]['rect'][1]
                if not 1.45*first<=second<=1.55*first:raise ValueError('new native custom algorithm did not change actual row spacing')
    return True
