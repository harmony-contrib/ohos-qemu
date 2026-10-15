"""Strict bounded LazyColumn journal and actual compositor verification."""
import json
from pathlib import Path
import re
from PIL import Image
from build_arkui_lazy_types_probe import BUNDLE, CONTRACTS
from guest_ui import select_node, NodeNotReady


def rows(text, nonce, uid):
    if re.fullmatch('[0-9a-f]{32}', nonce or '') is None or type(uid) is not int or uid < 20000000:
        raise ValueError('actual ordinary caller identity required')
    result = [json.loads(line) for line in text.splitlines() if line]
    allowed = {'identity','create.request','modifier.column.reset','modifier.column','visible.column',
               'scroll.request.last','scroll.request.first','remove.request'}
    for row in result:
        if (set(row) != {'runId','cycle','name','values','error'} or row['runId'] != nonce or
            type(row['cycle']) is not int or row['cycle'] not in (0,1) or row['name'] not in allowed or
            row['error'] != '' or not isinstance(row['values'],list) or
            any(type(value) is not int for value in row['values'])):
            raise ValueError('failed, foreign, or malformed native LazyColumn journal')
        values = row['values']
        if row['name'] == 'identity':
            if len(values) != 3 or values[:2] != [uid,uid] or values[2] <= 0:
                raise ValueError('LazyColumn caller is not the installed ordinary application')
        elif row['name'] == 'visible.column':
            if len(values) != 2 or not 0 <= values[0] <= values[1] < 40:
                raise ValueError('native visible indexes escaped the real item bounds')
        elif values != [1]: raise ValueError('native attribute chain or UI action failed')
    return result


def verify(text, nonce, uid):
    observed = rows(text,nonce,uid)
    if not observed or [row['cycle'] for row in observed] != sorted(row['cycle'] for row in observed):
        raise ValueError('two ordered native creation cycles required')
    for cycle in (0,1):
        values = [row for row in observed if row['cycle']==cycle]
        indices = {}
        for name in ('identity','create.request','modifier.column.reset','modifier.column',
                     'scroll.request.last','scroll.request.first','remove.request'):
            matches=[index for index,row in enumerate(values) if row['name']==name]
            if len(matches)!=1: raise ValueError('exactly one real '+name+' per cycle required')
            indices[name]=matches[0]
        order=list(indices.values())
        if order != sorted(order) or indices['identity'] != 0 or indices['remove.request'] != len(values)-1:
            raise ValueError('creation/reset/scroll/removal order or post-removal quiet period failed')
        for first,last,boundary in (
            ('modifier.column','scroll.request.last','top'),
            ('scroll.request.last','scroll.request.first','bottom'),
            ('scroll.request.first','remove.request','top')):
            events=[row['values'] for row in values[indices[first]+1:indices[last]] if row['name']=='visible.column']
            if not events: raise ValueError('actual '+boundary+' visibility callback missing')
            start,end=events[-1]
            if (boundary=='top' and (start!=0 or not 4<=end<=6)) or (boundary=='bottom' and (end!=39 or not 33<=start<=35)):
                raise ValueError('native callback did not reach the requested '+boundary+' boundary')
    if observed[0]['values'][2] != next(row['values'][2] for row in observed if row['cycle']==1 and row['name']=='identity'):
        raise ValueError('lazy recreation changed caller process')
    return list(CONTRACTS)


def pixels(screenshot, layout, nonce, cycle, phase):
    with Image.open(screenshot) as source:
        if source.format!='PNG':raise ValueError('real lossless compositor PNG required')
        image=source.convert('RGB')
    identifiers = range(35,40) if phase=='bottom' else range(5)
    nodes=[];fingerprint=[];metrics=[]
    if phase=='removed':
        node=select_node(layout,BUNDLE,text='removed '+nonce+':'+str(cycle))
        if sum(color in ((221,238,255),(170,204,221)) for color in image.getdata())>100:
            raise ValueError('removed LazyColumn retained painted item pixels')
        # Removal must eliminate every real child, not merely hide the first one.
        for index in range(40):
            try: select_node(layout,BUNDLE,identifier='arkui-lazy-types-item-'+str(index))
            except NodeNotReady: continue
            raise ValueError('removed LazyColumn retained a visible child')
        nodes=[node]
    else:
        for index in identifiers:
            node=select_node(layout,BUNDLE,text=nonce+':'+str(index))
            if node['attributes'].get('id')!='arkui-lazy-types-item-'+str(index):
                raise ValueError('foreign lazy child text/id')
            nodes.append(node)
    for index,node in enumerate(nodes):
        x,y,w,h=node['rect']
        if x+w>image.width or y+h>image.height:raise ValueError('lazy compositor child is off-screen')
        crop=image.crop((x,y,x+w,y+h));colors=list(crop.getdata())
        dark=sum(max(color)<90 for color in colors)
        if dark<25:raise ValueError('actual lazy text pixels are not presented')
        background=None
        if phase!='removed':
            item=(35 if phase=='bottom' else 0)+index
            rgb=(221,238,255) if item%2==0 else (170,204,221)
            background=sum(color==rgb for color in colors)
            if background<100:raise ValueError('actual lazy item color is not presented')
        fingerprint.extend([str(node['rect']).encode(),crop.tobytes()])
        metrics.append(dict(rect=node['rect'],dark_pixels=dark,item_background_pixels=background))
    return metrics,b''.join(fingerprint)


def verify_presentations(phases, nonce):
    if set(phases)!={str(cycle)+':'+phase for cycle in (0,1) for phase in ('initial','bottom','top','removed')}:
        raise ValueError('all real lazy boundaries and recreation presentations required')
    for key,record in phases.items():
        cycle,phase=key.split(':'); samples=record['presentation']['samples']
        if record['presentation']['status']!='pass_presentation_only' or len(samples)<3:
            raise ValueError('stable actual lazy presentation missing')
        final=[]
        for sample in samples[-3:]:
            actual,_bytes=pixels(sample['screenshot'],json.loads(Path(sample['layout']).read_text()),nonce,int(cycle),phase)
            if actual!=sample['metrics']:raise ValueError('lazy compositor metrics changed')
            final.append(_bytes)
        if len(set(final))!=1:raise ValueError('three consecutive stable lazy frames required')
    return True
