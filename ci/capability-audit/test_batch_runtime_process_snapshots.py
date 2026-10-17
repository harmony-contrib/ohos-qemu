"""Synthetic protocol and executed POSIX fixture tests; never guest evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import batch_network_openvpn_runtime_collect as scan

BOOT = '11111111-2222-3333-4444-555555555555'
NONCE = 'a' * 32
BUNDLE = 'org.harmonycontrib.liveinputsqa'


def hx(value): return (value.encode() if isinstance(value,str) else value).hex()


def proc_stat(pid, *, ppid=1, pgrp=0, start=123, state='S', flags=0, comm='unit process'):
    fields=[state,str(ppid),str(pgrp),'0','0','-1',str(flags)]+['0']*12+[str(start)]+['0']*30
    return f'{pid} ({comm}) '+' '.join(fields)+'\n'


def queries(pid, *, mode='vpn', exe='/system/bin/init', uid=0, argv=None, ppid=1,pgrp=0,start=123, maps=None):
    stat=proc_stat(pid,ppid=ppid,pgrp=pgrp,start=start)
    result={'stat':(0,hx(stat)), 'exe':(0,hx(exe))}
    selected=exe in scan.HELPERS if mode=='vpn' else mode=='maps' and maps is not None
    if mode=='uid' or selected:
        result['status']=(0,hx(f'Name:\tunit\nPid:\t{pid}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n'))
        result['cmdline']=(0,hx(b'\0'.join(arg.encode() for arg in (argv or [exe]))+b'\0'))
    if mode=='maps':
        head={key:result[key] for key in ('stat','exe')}
        head['maps_match']=(1,'') if maps is None else (0,'')
        head.update({key:value for key,value in result.items() if key not in head}); result=head
    if mode=='uid':
        result['uid_hint']=(0,hx(f'{uid}\t{uid}\t{uid}\t{uid}'))
        selected=uid>10000 or bool(argv and argv[0].startswith(BUNDLE))
    if mode=='maps':
        if maps is not None: result['maps']=(0,hx(maps))
    if selected: result['stat_after']=(0,hx(stat))
    return result


def frame(*, mode='vpn',nonce=NONCE,boot=BOOT,uid=None,bundle=None,records=None,start_ids=None,end_ids=None,direct=None,entries=()):
    records=records if records is not None else {1:queries(1,mode=mode,ppid=0)}
    start_ids=list(records) if start_ids is None else start_ids
    end_ids=start_ids if end_ids is None else end_ids
    first='|'.join(('BEGIN','PROCESS_V2',nonce,boot,mode,'-' if uid is None else str(uid),'-' if bundle is None else hx(bundle),scan.PROCESS_CONTRACT_ID))
    lines=[first,'LIST|start|'+hx('\n'.join(map(str,start_ids)))]; count=0
    for pid,items in records.items():
        lines.append('PID|'+str(pid))
        for op,(rc,data) in items.items(): lines.append(f'Q|{pid}|{op}|{rc}|{data}'); count+=1
        lines.append(f'TERMINAL|{pid}|{len(items)}')
    lines.append('LIST|end|'+hx('\n'.join(map(str,end_ids))))
    if direct is None and mode=='vpn':
        direct={'ancestor-list':(0,hx('.\n..\nvpn')),'parent-stat':(0,hx('1098:1098:700:directory:2:1:10')),
                'parent-list':(0,hx('.\n..\nqemu_openvpn')),'root-stat':(0,hx('1098:1098:700:directory:2:1:11')),
                'root-list':(0,hx('.\n..'+''.join('\n'+name for name,_,_ in entries)))}
    for name,(rc,data) in (direct or {}).items(): lines.append(f'D|{name}|{rc}|{data}')
    for name,rc,data in entries: lines.append(f'R|{hx(name)}|{rc}|{data}')
    lines.append(f'END|{nonce}|{len(records)}|{count}|{len(entries)}')
    return '\n'.join(lines)+'\n'


def replace_payload(raw, old, new):
    lines=raw.splitlines(); changed=False
    for i,line in enumerate(lines):
        parts=line.split('|'); position=4 if parts[0]=='Q' else 3 if parts[0] in ('D','R') else None
        if position is not None:
            data=bytes.fromhex(parts[position]); a=old.encode(); b=new.encode()
            if a in data: parts[position]=data.replace(a,b).hex(); lines[i]='|'.join(parts); changed=True
    if not changed: raise AssertionError('counterexample did not change a payload')
    return '\n'.join(lines)+'\n'


class SnapshotProtocolTests(unittest.TestCase):
    def parse(self,raw,**kwargs): return scan.parse_snapshot(raw,NONCE,BOOT,**kwargs)

    def test_complete_idle_is_valid_and_legacy_partial_is_not(self):
        value=self.parse(frame()); self.assertEqual(value['processes'],{}); self.assertIn(1,value['stats'])
        for raw in ('S|'+proc_stat(1), '__LIVE_PROCESS_SCAN_DONE__\n',frame().rsplit('END|',1)[0]):
            with self.assertRaises(ValueError): self.parse(raw)
        with self.assertRaises(ValueError): scan.parse_snapshot(frame())

    def test_nonce_boot_counts_pid_terminal_and_hex_fail_closed(self):
        raw=frame()
        variants=[raw.replace(NONCE,'b'*32,1),raw.replace(BOOT,'22222222-2222-3333-4444-555555555555'),
                  raw.replace(f'END|{NONCE}|1|2|0',f'END|{NONCE}|2|2|0'),raw.replace('TERMINAL|1|2\n',''),
                  raw.replace('LIST|start|31','LIST|start|310a32'),raw.replace('Q|1|exe|0|','Q|1|exe|0|0')]
        for bad in variants:
            with self.subTest(raw=bad[:80]),self.assertRaises(ValueError): self.parse(bad)

    def test_kernel_and_zombie_keep_pgid_and_do_not_require_exe(self):
        records={1:queries(1,ppid=0)}
        for pid,state,flags in ((2,'I',scan.KERNEL_PROCESS_CONTRACT['PF_KTHREAD']),(3,'Z',0)):
            records[pid]={'stat':(0,hx(proc_stat(pid,state=state,flags=flags,pgrp=88))),
                          'exe':(1,''),'exe_target':(1,hx(f'stat: /proc/{pid}/exe: No such file or directory'))}
        value=self.parse(frame(records=records)); self.assertEqual(value['stats'][2]['pgrp'],88); self.assertEqual(value['stats'][3]['pgrp'],88)
        records[2]['exe']=(1,hx('readlink: /proc/2/exe: Permission denied'))
        with self.assertRaises(ValueError): self.parse(frame(records=records))

    def test_proved_gone_not_permission_error_or_live_missing(self):
        records={1:queries(1,ppid=0),23:{'stat':(1,hx('od: /proc/23/stat: No such file or directory')),
                                      'exe':(1,''),'exe_target':(1,hx('stat: /proc/23/exe: No such file or directory'))}}
        self.assertIn(23,self.parse(frame(records=records,end_ids=[1]))['gone'])
        with self.assertRaises(scan.SnapshotRace): self.parse(frame(records=records))
        records[23]['stat']=(1,hx('od: /proc/23/stat: Permission denied'))
        with self.assertRaises(ValueError): self.parse(frame(records=records,end_ids=[1]))

    def test_silent_readlink_requires_independent_enoent_target_proof(self):
        records={1:queries(1,ppid=0),2:{'stat':(0,hx(proc_stat(2,state='I',flags=scan.KERNEL_PROCESS_CONTRACT['PF_KTHREAD']))),
            'exe':(1,''),'exe_target':(1,hx('stat: /proc/2/exe: No such file or directory'))}}
        self.assertEqual(self.parse(frame(records=records))['classifications'][2],'kernel')
        for target in ((0,hx('regular file')),(1,hx('stat: /proc/2/exe: Permission denied')),(1,'')):
            records[2]['exe_target']=target
            with self.assertRaises(ValueError): self.parse(frame(records=records))
        del records[2]['exe_target']
        with self.assertRaises(ValueError): self.parse(frame(records=records))

    def test_real_argv_boundaries_empty_argument_and_control_text(self):
        args=[scan.HELPERS[0],'space value','line\nEND|forged','']
        records={1:queries(1,ppid=0),23:queries(23,exe=scan.HELPERS[0],uid=1098,argv=args,pgrp=23)}
        value=self.parse(frame(records=records)); self.assertEqual(value['processes'][23]['argv'],args)
        records[23]['cmdline']=(0,hx(b'not terminated'))
        with self.assertRaises(ValueError): self.parse(frame(records=records))

    def test_generation_change_retries_whole_capture_only(self):
        records={1:queries(1,ppid=0),23:queries(23,exe=scan.HELPERS[0],uid=1098)}
        records[23]['stat_after']=(0,hx(proc_stat(23,start=999)))
        with self.assertRaises(scan.SnapshotRace): self.parse(frame(records=records))
        called=[]
        def shell(script,label):
            called.append(label); nonce=NONCE if len(called)==1 else 'b'*32
            return frame(nonce=nonce,records=records) if len(called)==1 else frame(nonce=nonce)
        with patch.object(scan.secrets,'token_hex',side_effect=[NONCE,'b'*32]),patch.object(scan.time,'sleep'):
            _,value=scan.capture_snapshot(shell,'snapshot',BOOT)
        self.assertEqual(called,['snapshot-0','snapshot-1']); self.assertFalse(value['processes'])

    def test_private_hidden_entries_and_stat_error_not_empty(self):
        entry=('..hidden',0,hx('1098:1098:600:regular file:1:1:12'))
        self.assertEqual(self.parse(frame(entries=[entry]))['entries'],['..hidden|1098:1098:600:regular file'])
        with self.assertRaises(ValueError): self.parse(frame(entries=[('backend.lock',1,hx('stat: Permission denied'))]))

    def test_uid_known_unknown_and_query_error_cannot_fake_done(self):
        for uid in (None,20001):
            records={1:queries(1,mode='uid',ppid=0),23:queries(23,mode='uid',exe='/system/bin/appspawn',uid=20001,argv=[BUNDLE+':worker'])}
            value=self.parse(frame(mode='uid',uid=uid,bundle=BUNDLE,records=records),mode='uid',uid=uid,bundle=BUNDLE)
            self.assertIn(23,value['processes'])
            records[23]['cmdline']=(7,hx('partial output then error'))
            with self.assertRaises(ValueError): self.parse(frame(mode='uid',uid=uid,bundle=BUNDLE,records=records),mode='uid',uid=uid,bundle=BUNDLE)


    def test_uid_zombie_is_not_clean_and_maps_query_error_is_not_nonmatch(self):
        records={1:queries(1,mode='uid',ppid=0),23:{
            'stat':(0,hx(proc_stat(23,state='Z'))),'exe':(1,hx('readlink: /proc/23/exe: No such file or directory')),
            'exe_target':(1,hx('stat: /proc/23/exe: No such file or directory')),
            'status':(0,hx('Name:\tunit\nPid:\t23\nUid:\t20001\t20001\t20001\t20001\n'))}}
        value=self.parse(frame(mode='uid',uid=20001,bundle=BUNDLE,records=records),mode='uid',uid=20001,bundle=BUNDLE)
        self.assertIn(23,value['processes'])
        lib='/system/lib64/libwallpaper_service.z.so'
        direct={stage+'-'+kind:(0,hx('1 2 4096' if kind=='stat' else 'b'*64+'  '+lib))
                for stage in ('file-before','file-after') for kind in ('stat','hash')}
        records={1:queries(1,mode='maps',ppid=0)}
        self.parse(frame(mode='maps',records=records,direct=direct),mode='maps',library=lib)
        records[1]['maps_match']=(2,hx('grep: /proc/1/maps: Permission denied'))
        with self.assertRaisesRegex(ValueError,'process query failed'):
            self.parse(frame(mode='maps',records=records,direct=direct),mode='maps',library=lib)


class ExecutedPosixFixtureTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name); proc=root/'proc'; proc.mkdir()
        boot=proc/'sys/kernel/random'; boot.mkdir(parents=True); (boot/'boot_id').write_text(BOOT+'\n')
        for pid,exe,uid in ((1,'/system/bin/init',0),(23,scan.HELPERS[0],1098)):
            directory=proc/str(pid); directory.mkdir(); (directory/'stat').write_text(proc_stat(pid,ppid=0 if pid==1 else 1,pgrp=pid))
            (directory/'exe').symlink_to(exe); (directory/'cmdline').write_bytes(exe.encode()+b'\0')
            (directory/'status').write_text(f'Name:\tunit\nPid:\t{pid}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
        private=root/'public/vpn/qemu_openvpn'; private.mkdir(parents=True); (private/'backend.lock').touch()
        tools=root/'bin'; tools.mkdir()
        for name in ('cat','ls','od','readlink','sed'): (tools/name).symlink_to(shutil.which(name))
        stat=tools/'stat'; stat.write_text('#!'+sys.executable+'''\nimport os,stat,sys
path=sys.argv[-1]
if os.environ.get('UNIT_FAIL_STAT'):
 print('stat: '+path+': Permission denied',file=sys.stderr);sys.exit(1)
s=os.stat(path);kind='directory' if stat.S_ISDIR(s.st_mode) else 'regular file'
print(str(s.st_uid)+':'+str(s.st_gid)+':'+oct(s.st_mode&0o777)[2:]+':'+kind+':'+str(s.st_nlink)+':'+str(s.st_dev)+':'+str(s.st_ino))
'''); stat.chmod(0o700)
        return root,proc,private,tools

    def execute(self,proc,private,tools,*,mode='vpn',uid=None,bundle=None,**env):
        script=scan._snapshot_script(NONCE,BOOT,proc_root=str(proc),private_root=str(private),mode=mode,uid=uid,bundle=bundle)
        return subprocess.run(['/bin/sh'],input=script,text=True,capture_output=True,timeout=20,env=dict(os.environ,PATH=str(tools),**env))

    def test_no_tr_in_path_and_actual_posix_fixture_decodes(self):
        _,proc,private,tools=self.fixture(); result=self.execute(proc,private,tools)
        self.assertEqual(result.returncode,0,result.stderr); parsed=scan.parse_snapshot(result.stdout,NONCE,BOOT)
        self.assertEqual(parsed['processes'][23]['argv'],[scan.HELPERS[0]])
        self.assertFalse((tools/'tr').exists())

    def test_uid_posix_fixture_preserves_actual_nul_arguments(self):
        _,proc,private,tools=self.fixture()
        (proc/'23/status').write_text('Name:\tunit\nPid:\t23\nUid:\t20001\t20001\t20001\t20001\n')
        (proc/'23/cmdline').write_bytes(BUNDLE.encode()+b'\0space value\0\0')
        result=self.execute(proc,private,tools,mode='uid',uid=20001,bundle=BUNDLE)
        self.assertEqual(result.returncode,0,result.stderr)
        parsed=scan.parse_snapshot(result.stdout,NONCE,BOOT,mode='uid',uid=20001,bundle=BUNDLE)
        self.assertEqual(parsed['processes'][23]['argv'],[BUNDLE,'space value',''])
        (proc/'23/cmdline').write_bytes(b'')
        result=self.execute(proc,private,tools,mode='uid',uid=20001,bundle=BUNDLE)
        self.assertEqual(result.returncode,0,result.stderr)
        with self.assertRaises(ValueError): scan.parse_snapshot(result.stdout,NONCE,BOOT,mode='uid',uid=20001,bundle=BUNDLE)

    def test_stat_permission_error_and_broken_link_are_not_empty(self):
        _,proc,private,tools=self.fixture(); result=self.execute(proc,private,tools,UNIT_FAIL_STAT='1')
        self.assertEqual(result.returncode,0,result.stderr)
        with self.assertRaises(ValueError): scan.parse_snapshot(result.stdout,NONCE,BOOT)
        (private/'..broken').symlink_to(private/'missing'); result=self.execute(proc,private,tools)
        self.assertNotEqual(result.returncode,0)

    def test_od_partial_failure_propagates(self):
        _,proc,private,tools=self.fixture(); real_od=os.readlink(tools/'od'); (tools/'od').unlink()
        od=tools/'od'; od.write_text('#!'+sys.executable+'\nimport os,sys\nif sys.argv[-1].endswith("/cmdline"):\n print(" 2f 73");sys.exit(7)\nos.execv('+repr(real_od)+',["od"]+sys.argv[1:])\n'); od.chmod(0o700)
        result=self.execute(proc,private,tools); self.assertEqual(result.returncode,0,result.stderr)
        with self.assertRaises(ValueError): scan.parse_snapshot(result.stdout,NONCE,BOOT)


if __name__=='__main__': unittest.main()
