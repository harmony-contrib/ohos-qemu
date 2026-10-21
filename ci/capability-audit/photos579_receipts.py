"""Pure interpretation of actual Owner/Collector receipts and caller journals."""
from pathlib import Path
import hashlib
import json
import re
import shlex

from guest_ui import command_exit, bounds
from photos579_raw import need, checked, ref, document, wire, loads


class Raw:
    def __init__(self, rows, *, boot, target, merged=False, qmp=()):
        self.rows, self.boot, self.target = rows,boot,target
        self.normal, self.programs, self.received = [],[],{}
        self.bodies = {}
        self.prefixes = {}
        self.copied_receives = []
        self.qmp = list(qmp)
        for row in rows:
            need(row['boot_id']==boot and not row['timed_out'], 'same boot actual completed command')
            argv=row['argv']
            if merged:
                need(row['stream_layout']=='stdout_stderr_merged_by_original_collector', 'original merged transport retained')
                raw=checked(row['log']).read_text()
                code=row.get('transport_exit_code',row['exit_code'])
                normal={key:row[key] for key in ('argv','exit_code','boot_id','timed_out','stream_layout')}
                normal.update(merged_stream=row['log'],stderr_separate=None)
                if 'timeout_seconds' in row: normal['timeout_seconds']=row['timeout_seconds']
                if 'transport_exit_code' in row:
                    normal.update(program_stdout=row['stdout_ref'],transport_exit_code=code,
                        transport_stdout=row['transport_stdout_ref'],envelope_exit_code=row['envelope_exit_code'])
                program,body,guest_code=None,raw,code
                if len(argv)==5 and argv[1:4]==['-t',target,'shell']:
                    mark=re.fullmatch(r'(.*); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[a-f0-9]{32}__=)%s\\n" "\$task_ui_rc"',argv[4],re.S)
                    need(mark is not None,'actual original Collector footer')
                    body,guest_code=command_exit(raw,mark[2]);program=mark[1]
                    inner=re.fullmatch(r'(.*); apps579_rc=\$\?; printf "\\n(__APPS579_EXIT_[a-f0-9]{32}__=)%s\\n" "\$apps579_rc"',program,re.S)
                    if inner:
                        need(guest_code==0 and row['envelope_exit_code']==0 and code==0,'actual original outer transport success')
                        body,guest_code=command_exit(body,inner[2]);words=shlex.split(inner[1])
                        need(len(words)==3 and words[:2]==['sh','-c'] and shlex.join(words)==inner[1],'isolated original program')
                        program=words[2]
                        need(checked(row['stdout_ref']).read_text()==body and row['exit_code']==guest_code,
                            'actual merged guest status/body differ')
                need(row.get('stderr') is None,'Collector never supplies a separate invented stderr')
            else:
                observed=wire(row,boot=boot,target=target)
                program,body,guest_code=observed['script'],observed['body'],observed['exit_code']
                normal={key:row[key] for key in ('argv','exit_code','boot_id','timed_out')}
                normal.update(stdout=row['stdout_ref'],stderr=row['stderr_ref'])
            self.normal.append(normal)
            self.programs.append(dict(script=program,body=body,exit_code=guest_code,argv=argv))
            for name in ('stdout_ref','shell_stdout_ref'):
                if name in row:
                    item=row[name]
                    self.bodies[(item['path'],item['sha256'])]=(program,checked(item).read_text(),guest_code)
            if len(argv)>=4 and argv[1:4]==['-t',target,'file']:
                need(len(argv)==7 and argv[4] in ('send','recv'),'actual finite HDC file transfer')
                need(row.get('transport_exit_code',row['exit_code'])==0,'actual transfer failed')
                if argv[4]=='recv':
                    local=Path(argv[6]); actual=ref(local)
                    self.received[(actual['path'],actual['sha256'])]=argv[5]
        for row in self.qmp:
            need(row['boot_id']==boot and row['completed'] is True,'actual original completed QMP')
            request=[loads(line) for line in checked(row['request']).read_text().splitlines() if line]
            replies=[loads(line) for line in checked(row['response']).read_text().splitlines() if line]
            need(any(r.get('execute')==row['execute'] and r.get('arguments',{})==row['arguments'] for r in request) and
                any(r.get('id')=='request' and r.get('return')==row['reply'] and 'error' not in r for r in replies),
                'actual QMP wire association')
        self.command_programs=list(zip(self.normal,self.programs))

    def add_collector_ui(self, commands):
        """Actual original GuestUi bypasses CollectorIO.command, not ownership.

        Only actual original rows from captured callback cuts are added. Their
        stream is explicitly merged; they are not fabricated IO receipts.
        """
        seen={row['log']['path'] for row in self.rows}
        selected=[]
        for row in commands:
            if row['raw']['path'] in seen: continue
            seen.add(row['raw']['path'])
            selected.append(dict(argv=row['argv'],exit_code=row['exit_code'],boot_id=self.boot,
                timed_out=row['timed_out'],timeout_seconds=row['timeout_seconds'],
                stream_layout='stdout_stderr_merged_by_original_collector',stdout_ref=row['raw'],
                log=row['raw'],stdout=checked(row['raw']).read_text(),stderr=None))
        extra=Raw(selected,boot=self.boot,target=self.target,merged=True)
        self.programs.extend(extra.programs);self.command_programs.extend(extra.command_programs)
        self.bodies.update(extra.bodies);self.received.update(extra.received)
        return extra.normal

    @staticmethod
    def collector_normal(row,boot):
        return dict(argv=row['argv'],exit_code=row['exit_code'],boot_id=boot,
            timed_out=row['timed_out'],timeout_seconds=row['timeout_seconds'],
            stream_layout='stdout_stderr_merged_by_original_collector',
            merged_stream=row['raw'],stderr_separate=None)

    def body(self, value, script=None):
        checked(value);key=(value['path'],value['sha256'])
        need(key in self.bodies,'body has no original command')
        actual,text,code=self.bodies[key]
        need(script is None or actual==script,'fixed actual guest script differs')
        return text,code

    def has(self, script, *, zero=True, rows=None):
        candidates=self.programs if rows is None else [program for receipt,program in self.command_programs if receipt in rows]
        found=[row for row in candidates if row['script']==script and (not zero or row['exit_code']==0)]
        need(found,'actual original program absent: '+script)
        return found

    def transported(self, value, remote=None):
        checked(value);key=(value['path'],value['sha256'])
        if key in self.received and (remote is None or self.received[key]==remote): return self.received[key]
        # Original CollectorIO.receive really copies its actual Collector recv
        # to its Apps child directory. Retain both physical references. Never
        # relabel that copy as the original HDC destination.
        need(remote is not None,'copied receive requires exact original remote')
        matching=[(actual_path,digest) for (actual_path,digest),source in self.received.items()
            if digest==value['sha256'] and source==remote and Path(actual_path).read_bytes()==checked(value).read_bytes()]
        need(matching,'actual guest receive/copy bytes absent')
        self.copied_receives.append(dict(copied=value,actual_receives=[dict(path=p,sha256=s) for p,s in matching],remote=remote))
        return remote

    def combined(self,value,commands):
        content=checked(value).read_bytes();latest={}
        for row in commands:
            argv=row['argv']
            if len(argv)==7 and argv[1:5]==['-t',self.target,'file','recv'] and argv[5].endswith('.jsonl'):
                latest[argv[5]]=Path(argv[6]).read_bytes()
        need(latest and content==b''.join(latest[key] for key in sorted(latest)),
            'combined identity journal differs from actual final per-file receives')
        return [loads(line) for line in content.decode().splitlines() if line]

    def frame(self, value):
        path=checked(value)
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        if (value['path'],value['sha256']) not in self.received:
            need(any(row['execute']=='screendump' and row['arguments']=={'filename':str(path)} for row in self.qmp),
                'frame has no actual receive or original QMP screendump')

    def layout(self, value):
        actual=document(value)
        matches=[row for row in self.programs if row['script'] and row['script'].startswith('cat ') and
            row['exit_code']==0 and row['body'].strip().startswith(('{','[')) and loads(row['body'])==actual]
        need(matches,'UI tree not associated with actual guest dump read')
        for row in matches:
            remote=shlex.split(row['script'])
            if len(remote)==2:
                expected='test ! -e '+shlex.quote(remote[1])+' && uitest dumpLayout -p '+shlex.quote(remote[1])
                if any(p['script'] and (p['script']==expected or p['script'].startswith(expected+' -b ')) and
                    p['exit_code']==0 for p in self.programs):
                    return actual
        raise ValueError('actual guest dump creation absent')

    def node(self, value, layout):
        tree=self.layout(layout); found=[]
        def visit(node,owner=''):
            attrs=node['attributes'];owner=attrs.get('bundleName') or owner
            if attrs==value['attributes'] and owner==value['bundle'] and list(bounds(attrs['bounds']))==value['rect']:
                need(attrs.get('visible')=='true','selected actual node hidden');found.append(node)
            for child in node.get('children',[]): visit(child,owner)
        for node in tree if type(tree) is list else [tree]: visit(node)
        need(len(found)==1,'exact selected actual node absent/ambiguous')
        return found[0]

    def click(self, value, layout, commands):
        self.node(value,layout);x,y,w,h=value['rect']
        self.has('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2),rows=commands)

    def journal(self, collected, *, run, role, bundle, case, uid=None, request=None):
        files=collected['journal_files'];bodies=[];values=[]
        for item in files:
            raw=checked(item['raw']).read_bytes();remote=item['remote']
            self.transported(item['raw'],remote)
            need(raw.endswith(b'\n') and raw.startswith(self.prefixes.get(remote,b'')), 'actual journal truncate/replacement')
            self.prefixes[remote]=raw;bodies.append(raw)
            rows=[loads(line) for line in raw.decode().splitlines() if line]
            need(rows,'nonempty real caller journal')
            for index,row in enumerate(rows):
                need(type(row['seq']) is int and row['seq']==index and row['run_id']==run and row['bundle']==bundle and
                    row['role']==role and row['kind']==case and
                    type(row['pid']) is int and row['pid']>0 and type(row['uid']) is int and
                    remote.endswith('-'+str(row['pid'])+'.jsonl') and (uid is None or row['uid']==uid),
                    'actual caller nonce/UID/process/file sequence mismatch')
                if index: need(rows[index-1]['active_ms']<=row['active_ms'],'guest monotonic journal reversal')
            values.extend(rows)
        need(checked(collected['journal']).read_bytes()==b''.join(bodies),'combined journal differs from original receives')
        for binary in collected['binaries']:
            candidates=[row for row in values if row['event']=='media-bytes' and row['request_id']==binary['request_id']]
            need(len(candidates)==1,'one actual byte emission')
            detail=loads(candidates[0]['value'])
            name='apps579-media-'+binary['request_id']+'.bin'
            need(detail['file']==name or detail['file'].endswith('/'+name),'actual media artifact name')
            self.transported(binary['raw'],'/data/app/el2/100/base/'+bundle+'/files/'+name)
            need(detail['sha256'].lower()==binary['raw']['sha256'] and detail['size']==checked(binary['raw']).stat().st_size==binary['bytes'],
                'actual media hash/size differ')
        return [row for row in values if request is None or row['request_id']==request]


def value(rows,event):
    found=[row for row in rows if row['event']==event]
    need(len(found)==1,'one actual '+event)
    return loads(found[0]['value'])


def success(rows):
    need(any(row['event']=='request' for row in rows) and any(row['event']=='done' for row in rows) and
        not any(row['event'] in ('error','request-error','page-error','form-component-error') for row in rows),
        'actual public request failed or incomplete')


def denial(rows,code=None):
    found=[row for row in rows if row['event']=='error' and row['code'] in (201,202,13900001,13900012)]
    need(len(found)==1 and (code is None or found[0]['code']==code) and
        loads(found[0]['value'])['codeType']=='number' and not any(row['event'] in
        ('done','media-bytes','ungranted-uri-read-returned') for row in rows),'actual numeric foreign denial required')


def nonce_image(binary,nonce):
    from PIL import Image
    need(re.fullmatch('[a-f0-9]{32}',nonce),'fresh 128bit challenge')
    with Image.open(checked(binary)) as image:
        need(image.format=='JPEG' and image.size==(64,64),'actual nonce JPEG decode')
        image=image.convert('RGB')
        for tile in range(16):
            v=int(nonce[tile*2:tile*2+2],16)
            wanted=(32+v%160,32+(v*3+tile)%160,32+(v*7+tile)%160)
            samples=[image.getpixel((tile%4*16+x,tile//4*16+y)) for x in (5,8,11) for y in (5,8,11)]
            need(all(max(abs(a-b) for a,b in zip(pixel,wanted))<=12 for pixel in samples),
                'independently decoded actual nonce tiles differ')
    return dict(width=64,height=64,tiles=16,nonce=nonce,jpeg=binary)
