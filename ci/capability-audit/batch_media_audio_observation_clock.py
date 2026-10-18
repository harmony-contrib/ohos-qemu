"""Own and independently replay a real digital-zero ES1370 DAC1 measurement stream.

The original QEMU WAV must still satisfy its unchanged frame/time/audio checks.
This observer has no AudioFramework focus or public-player implementation role.
"""
import json
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import time

from guest_ui import command_exit
from guest_process_identity import starttime_shell,uids_shell,cleanup_producer_shell
from batch_media_audio_haptic_project import checked,record,require

DEVICE='hw:CARD=AudioPCI,DEV=1,SUBDEV=0'
HARDWARE='cat /proc/asound/cards && cat /proc/asound/pcm && cat /proc/asound/card0/pcm1p/sub0/status && cat /proc/asound/card0/pcm1p/sub0/hw_params'


def remote_checked(remote):
    require(isinstance(remote,str) and re.fullmatch('/data/local/tmp/qemu-mic-[a-f0-9]{32}',remote),'exact new clock directory required')
    return remote


def wrapper(remote,marker):
    remote_checked(remote)
    require(re.fullmatch('__PCM_CHILD_EXIT_[a-f0-9]{32}__=',marker),'exact clock child nonce required')
    inner=('umask 077; set -C; printf "%s\\n" "$$" > '+remote+'/producer.pid || exit 1; '
        'task_clock_start=$( '+starttime_shell('$$')+') || exit 1; '
        'printf "%s\\n" "$task_clock_start" > '+remote+'/producer.start || exit 1; '
        'unset LD_LIBRARY_PATH LD_PRELOAD; exec '+remote+'/alsa_inject --seconds 180')
    return 'sh -c '+shlex.quote(inner)+'; task_clock_rc=$?; printf "\\n'+marker+'%s\\n" "$task_clock_rc"'


def identity_script(remote):
    remote_checked(remote)
    return ('task_clock_pid=$(cat '+remote+'/producer.pid) || exit 1; '
        'case "$task_clock_pid" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'printf "%s\\n" "$task_clock_pid"; cat '+remote+'/producer.start || exit 1; '
        'readlink /proc/$task_clock_pid/exe || exit 1; '+starttime_shell('$task_clock_pid')+'; '+uids_shell('$task_clock_pid'))


def identity(raw,remote):
    fields=raw.splitlines()
    require(len(fields)==5 and re.fullmatch('[1-9][0-9]*',fields[0]) and
        re.fullmatch('[1-9][0-9]*',fields[1]) and fields[1]==fields[3] and
        fields[2]==remote+'/alsa_inject' and fields[4]=='0 0 0 0','clock process generation/executable/UID differs')
    return dict(pid=int(fields[0]),starttime=int(fields[1]))


def hardware(raw,pid):
    def one(pattern):
        values=re.findall(pattern,raw,re.M);require(len(values)==1,'actual DAC1 hardware field missing/ambiguous');return values[0]
    require(re.search(r'^ 0 \[AudioPCI\s*\]: ENS1370 - Ensoniq AudioPCI$',raw,re.M) and
        re.search(r'^00-01: ES1370/2 : ES1370 DAC1 : playback 1$',raw,re.M),'actual separate ES1370 DAC1 missing')
    require(one(r'^state: ([A-Z]+)$')=='RUNNING' and int(one(r'^owner_pid\s*: ([1-9][0-9]*)$'))==pid and
        one(r'^access: (.+)$')=='RW_INTERLEAVED' and one(r'^format: (.+)$')=='S16_LE' and
        one(r'^channels: ([0-9]+)$')=='2' and one(r'^rate: (.+)$')=='44100 (44100/1)',
        'actual clock must own the independent running stereo DAC1')


def remove_script(remote):
    remote_checked(remote)
    return ('test -d '+remote+' && test ! -L '+remote+' && test "$(stat -c \'%u %a\' '+remote+
        ')" = "0 700" && rm -rf '+remote+' && test ! -e '+remote+' && test ! -L '+remote)


def stop_script(remote,pid):
    require(type(pid) is int and pid>0,'actual clock PID required')
    return 'test -d /proc/'+str(pid)+' || exit 1; '+cleanup_producer_shell(remote)


def log_rows(raw,marker,host_code):
    body,code=command_exit(raw,marker)
    require(type(host_code) is int and host_code==0 and code==0,'actual clock child/transport failed')
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'duplicate native clock key');value[key]=item
        return value
    lines=body.splitlines()
    require(len(lines)==2,'only actual native ready/end records may prove a clock')
    ready,end=[json.loads(line,object_pairs_hook=unique) for line in lines]
    require(set(ready)=={'event','pid','uid','device','rate','channels'} and ready['event']=='clock_ready' and
        type(ready['pid']) is int and ready['pid']>0 and type(ready['uid']) is int and ready['uid']==0 and
        ready['device']==DEVICE and type(ready['rate']) is int and ready['rate']==44100 and
        type(ready['channels']) is int and ready['channels']==2,'native clock readiness differs')
    require(set(end)=={'event','reason','written_frames','drop_rc','close_rc'} and end['event']=='clock_end' and
        end['reason']=='owned_sigterm' and type(end['written_frames']) is int and end['written_frames']>=8192 and
        type(end['drop_rc']) is int and type(end['close_rc']) is int and end['drop_rc']==end['close_rc']==0,
        'measurement clock was not deliberately stopped and closed successfully')
    return ready,end


class ObserverClock:
    def __init__(self,collector):
        self.collector=collector;self.process=None;self.stream=None;self.created=False
        self.row=dict(remote='/data/local/tmp/qemu-mic-'+secrets.token_hex(16),marker='__PCM_CHILD_EXIT_'+secrets.token_hex(16)+'__=')
        collector.value.setdefault('audio_observation_clocks',[]).append(self.row)

    def start(self,phase):
        c=self.collector;r=self.row;r['phase']=phase;remote=r['remote']
        c.shell('test ! -e '+remote+' && test ! -L '+remote,'fresh-clock-directory')
        # An ambiguous mkdir reply still requires owned cleanup or VM disposal.
        self.created=True;c.shell('mkdir -m 700 '+remote,'create-clock-directory')
        c.stage(c.value['clock_helper']['binary'],remote+'/alsa_inject',0,executable=True)
        r['argv']=[str(c.args.hdc),'-t',c.guest.target,'shell',wrapper(remote,r['marker'])]
        path=c.args.output/('clock-'+phase+'.log');self.stream=path.open('xb');r['started_ns']=time.monotonic_ns()
        self.process=subprocess.Popen(r['argv'],stdin=subprocess.DEVNULL,stdout=self.stream,stderr=subprocess.STDOUT,start_new_session=True)
        r['host_pid']=self.process.pid
        r['log_path']=str(path);c.persist();until=time.monotonic()+10
        while time.monotonic()<until:
            require(self.process.poll() is None,'clock exited before hardware-ready proof')
            if '"event":"clock_ready"' in path.read_text(errors='replace'):break
            c.guest.healthy();time.sleep(.1)
        else:raise ValueError('real clock failed to become ready')
        r['identity_before']=c.observe(identity_script(remote),'clock-identity-before')
        actual=identity(checked(r['identity_before']).read_text(),remote);r['identity']=actual
        r['hardware_before']=c.observe(HARDWARE,'clock-DAC1-before');hardware(checked(r['hardware_before']).read_text(),actual['pid'])
        # Settle the real hardware/mixer stream before starting the original
        # WAV. This adds no frames to that file and changes no time tolerance.
        r['hardware_ready_ns']=time.monotonic_ns();time.sleep(.5)
        require(self.process.poll() is None,'clock ended during hardware warmup')
        r['ready_ns']=time.monotonic_ns();c.persist()

    def stop(self):
        c=self.collector;r=self.row
        if self.process is None:return r
        remote=r['remote']
        require(self.process.poll() is None,'clock ended before the owned capture completed')
        r['identity_after']=c.observe(identity_script(remote),'clock-identity-after')
        actual=identity(checked(r['identity_after']).read_text(),remote)
        require(actual==r['identity'],'clock process generation changed')
        r['hardware_after']=c.observe(HARDWARE,'clock-DAC1-after');hardware(checked(r['hardware_after']).read_text(),actual['pid'])
        r['stop_requested_ns']=time.monotonic_ns()
        r['stop']=c.observe(stop_script(remote,actual['pid']),'stop-only-owned-clock')
        r['host_exit_code']=self.process.wait(timeout=10);self.stream.close();self.stream=None
        r['log']=record(Path(r['log_path']));ready,_=log_rows(checked(r['log']).read_text(),r['marker'],r['host_exit_code'])
        require(ready['pid']==actual['pid'],'native clock and process identity differ')
        r['gone']=c.observe(cleanup_producer_shell(remote),'owned-clock-gone')
        r['removed']=c.observe(remove_script(remote),'remove-only-owned-clock-files')
        self.process=None;self.created=False;r['finished_ns']=time.monotonic_ns();c.persist();return r

    def dispose(self):
        c=self.collector;r=self.row;remote=r['remote']
        errors=[];guest_gone=not self.created
        if self.created:
            try:
                r['emergency_cleanup']=c.observe(cleanup_producer_shell(remote),'emergency-only-owned-clock');guest_gone=True
            except Exception as error:errors.append('guest clock cleanup unproved: '+str(error))
        if self.process is not None:
            try:
                try:r['emergency_host_exit_code']=self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    errors.append('clock HDC client required forced leader cleanup; guest closure remains independent')
                    self.process.terminate()
                    try:r['emergency_host_exit_code']=self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill();r['emergency_host_exit_code']=self.process.wait(timeout=3)
                self.process=None
            except Exception as error:errors.append('owned clock HDC leader reap unproved: '+str(error))
            finally:
                if self.stream is not None:self.stream.close();self.stream=None
                r['emergency_log']=record(Path(r['log_path']))
        if self.created and guest_gone:
            try:
                r['emergency_removed']=c.observe(remove_script(remote),'emergency-owned-clock-files');self.created=False
            except Exception as error:errors.append('clock files cleanup unproved: '+str(error))
        r['emergency_errors']=errors
        c.persist()
        if errors:raise ValueError('; '.join(errors))


def verify_clock(row,capture,*,helper,hdc,target,observed,command_index):
    remote=remote_checked(row['remote']);actual=row['identity']
    require(row['argv']==[hdc,'-t',target,'shell',wrapper(remote,row['marker'])],'clock argv differs from actual owned protocol')
    ready,_=log_rows(checked(row['log']).read_text(),row['marker'],row['host_exit_code'])
    require(ready['pid']==actual['pid'],'native readiness and actual process differ')
    for suffix in ('before','after'):
        require(identity(observed(row['identity_'+suffix],identity_script(remote)),remote)==actual,'clock identity changed')
        hardware(observed(row['hardware_'+suffix],HARDWARE),actual['pid'])
    observed(row['stop'],stop_script(remote,actual['pid']));observed(row['gone'],cleanup_producer_shell(remote));observed(row['removed'],remove_script(remote))
    indexes=[command_index(row[n]) for n in ['identity_before','hardware_before','identity_after','hardware_after','stop','gone','removed']]
    require(all(a<b for a,b in zip(indexes,indexes[1:])),'actual clock raw cuts/stop/removal reordered')
    times=[row['started_ns'],row['ready_ns'],capture['host_begin_ns'],capture['host_end_ns'],row['stop_requested_ns'],row['finished_ns']]
    require(all(type(t) is int and t>0 for t in times) and all(a<b for a,b in zip(times,times[1:])) and
        row['finished_ns']-row['started_ns']<=185_000_000_000,'real clock did not bracket the complete original WAV interval')
    return dict(scope='actual digital-zero DAC1 measurement stream ONLY',pid=actual['pid'],binary=helper['binary'])
