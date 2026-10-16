"""Nonce/boot-bound foreground clock samples around the unchanged quiet gate."""
import importlib
import json
from pathlib import Path
import re
import secrets
import shlex
import time

from watchdog_clocks import parse, compare, capture_script
from run_root_probe import digest

SCOPE = 'actual_same_boot_clock_intervals_NOT_sleep_state_or_watchdog_recovery_proof'
PHASES = ('before-unassisted-stability', 'after-unassisted-stability')


def regular(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('absolute non-aliased clock evidence required')
    return path


def descriptor(path):
    path = regular(path); return {'path':str(path),'sha256':digest(path)}


def checked(value):
    path = regular(value['path'])
    if digest(path) != value['sha256']: raise ValueError('clock evidence changed')
    return path


def builder():
    return importlib.import_module('build_watchdog_clock_probe')


def sample_script(remote, nonce):
    return '(set -eu; cat /proc/sys/kernel/random/boot_id; ' + capture_script(remote,nonce) + '; cat /proc/sys/kernel/random/boot_id)'


def staging_script(directory, remote, token):
    return '(set -eu; test "$(id -u)" = 0; test ! -L '+shlex.quote(directory)+'; chmod 500 '+shlex.quote(remote)+\
        '; printf "CLOCK_STAGE_V1 '+token+'\\n"; stat -c "%u %g %a" '+shlex.quote(directory)+\
        '; stat -c "%u %g %a" '+shlex.quote(remote)+'; sha256sum '+shlex.quote(remote)+\
        '; printf "END_CLOCK_STAGE_V1 '+token+'\\n")'


def cleanup_script(directory, remote, checksum, token):
    return '(set -eu; test ! -L '+shlex.quote(directory)+'; test ! -L '+shlex.quote(remote)+\
        '; test "$(sha256sum '+shlex.quote(remote)+' | cut -d" " -f1)" = '+checksum+\
        '; rm -- '+shlex.quote(remote)+'; rmdir -- '+shlex.quote(directory)+'; test ! -e '+shlex.quote(directory)+\
        '; printf "CLOCK_HELPER_REMOVED '+token+'\\n")'


def raw_command(payload, index, argv):
    commands = payload['commands']
    if type(index) is not int or not 0 <= index < len(commands): raise ValueError('actual clock command missing')
    row = commands[index]
    if row['argv'] != argv or row.get('exit_code') != 0: raise ValueError('clock command failed or changed guest/operation')
    return checked({'path':row['log'],'sha256':row['sha256']}).read_text().replace('\r','')


class Observer:
    def __init__(self, guest, binary, receipt):
        self.guest = guest
        proof = builder().verify_build(regular(binary),regular(receipt),guest.arch)
        token = secrets.token_hex(16); directory = '/data/local/tmp/ohos-qemu-clocks-'+token
        self.value = {'schema_version':1,'scope':SCOPE,'boot_id':guest.report['test_environment']['boot_id'],
            'target':guest.target,'binary':descriptor(binary),'receipt':descriptor(receipt),'build':proof,
            'token':token,'directory':directory,'remote':directory+'/clock-pair-probe','observations':[],
            'cleanup_complete':False,'cleanup_errors':[]}
        guest.report['watchdog_clocks'] = self.value
        self.created = False; self.staged = False

    def shell(self, script, label, timeout=30):
        index = len(self.guest.report['commands'])
        raw = self.guest.command([self.guest.args.hdc,'-t',self.guest.target,'shell',script],label,timeout=timeout)
        return index,raw

    def prepare(self):
        v = self.value; directory = v['directory']; remote = v['remote']; token = v['token']
        index,raw = self.shell('(set -eu; test "$(id -u)" = 0; test ! -e '+directory+'; mkdir -m 700 '+directory+
            '; printf "CLOCK_DIRECTORY_CREATED '+token+'\\n")','clock-create-owned-directory')
        if raw.strip() != 'CLOCK_DIRECTORY_CREATED '+token: raise ValueError('actual owned clock directory was not created')
        self.created = True; v['create_command'] = index
        v['send_command'] = len(self.guest.report['commands'])
        self.guest.command([self.guest.args.hdc,'-t',self.guest.target,'file','send',v['binary']['path'],remote],
            'clock-send-built-helper')
        self.staged = True
        index,raw = self.shell(staging_script(directory,remote,token),'clock-actual-staged-identity')
        expected = ['CLOCK_STAGE_V1 '+token,'0 0 700','0 0 500',v['binary']['sha256']+'  '+remote,'END_CLOCK_STAGE_V1 '+token]
        if raw.splitlines() != expected: raise ValueError('deployed clock helper owner/mode/hash differs')
        v['staging_command'] = index

    def sample(self, phase):
        v = self.value
        if phase != PHASES[len(v['observations'])]: raise ValueError('clock phase order differs')
        nonce = secrets.token_hex(16); began = time.monotonic_ns()
        index,raw = self.shell(sample_script(v['remote'],nonce),'clock-'+phase)
        lines = raw.splitlines()
        if len(lines) != 3 or lines[0] != v['boot_id'] or lines[2] != v['boot_id']:
            raise ValueError('actual clock read belongs to another kernel or failed')
        value = parse(lines[1],nonce)
        v['observations'].append({'phase':phase,'nonce':nonce,'host_started_ns':began,
            'host_finished_ns':time.monotonic_ns(),'command_index':index,'value':value})
        if len(v['observations']) == 2: v['comparison'] = compare(v['observations'][0]['value'],value)

    def cleanup(self):
        v = self.value
        if v['cleanup_complete']: return
        try:
            if not self.created: return
            if not self.staged: raise ValueError('clock transfer incomplete; private VM cleanup required')
            index,raw = self.shell(cleanup_script(v['directory'],v['remote'],v['binary']['sha256'],v['token']),
                'clock-remove-only-owned-helper',timeout=5)
            if raw.strip() != 'CLOCK_HELPER_REMOVED '+v['token']: raise ValueError('clock cleanup lacks actual absence proof')
            v.update(cleanup_command=index,cleanup_complete=True)
        except BaseException as error:
            v['cleanup_errors'].append(type(error).__name__+': '+str(error))


def verify(payload, required=False):
    v = payload.get('watchdog_clocks')
    if v is None and not required: return None
    env = payload['test_environment']
    if (not isinstance(v,dict) or type(v.get('schema_version')) is not int or v.get('schema_version') != 1 or v.get('scope') != SCOPE or
            v.get('boot_id') != env['boot_id'] or v.get('target') != env['target'] or
            v.get('cleanup_complete') is not True or v.get('cleanup_errors') != [] or
            re.fullmatch('[a-f0-9]{32}',v.get('token','')) is None):
        raise ValueError('complete same-boot clock observations and cleanup required')
    if builder().verify_build(checked(v['binary']),checked(v['receipt']),env['guest_arch']) != v['build']:
        raise ValueError('clock helper build provenance differs')
    token = v['token']; directory = '/data/local/tmp/ohos-qemu-clocks-'+token; remote=directory+'/clock-pair-probe'
    if (v['directory'],v['remote']) != (directory,remote): raise ValueError('clock helper escaped its owned directory')
    # HDC executable is obtained from the exact original staging transfer, not
    # an arbitrary first host command (which may have started the shared server).
    send = payload['commands'][v['send_command']]; hdc = send['argv'][0]
    if send['argv'][1:] != ['-t',env['target'],'file','send',v['binary']['path'],remote] or send.get('exit_code') != 0:
        raise ValueError('actual clock helper transfer differs')
    checked({'path':send['log'],'sha256':send['sha256']})
    def argv(script): return [hdc,'-t',env['target'],'shell',script]
    created = raw_command(payload,v['create_command'],argv('(set -eu; test "$(id -u)" = 0; test ! -e '+directory+
        '; mkdir -m 700 '+directory+'; printf "CLOCK_DIRECTORY_CREATED '+token+'\\n")'))
    if created.strip() != 'CLOCK_DIRECTORY_CREATED '+token: raise ValueError('owned clock directory creation differs')
    staged = raw_command(payload,v['staging_command'],argv(staging_script(directory,remote,token)))
    if staged.splitlines() != ['CLOCK_STAGE_V1 '+token,'0 0 700','0 0 500',v['binary']['sha256']+'  '+remote,'END_CLOCK_STAGE_V1 '+token]:
        raise ValueError('staged clock helper identity differs')
    rows = v.get('observations',[])
    if len(rows) != 2 or [r['phase'] for r in rows] != list(PHASES) or rows[0]['nonce'] == rows[1]['nonce']:
        raise ValueError('two unique ordered clock challenges required')
    for row in rows:
        if (type(row.get('host_started_ns')) is not int or type(row.get('host_finished_ns')) is not int or
                not 0 < row['host_started_ns'] <= row['host_finished_ns']): raise ValueError('actual clock read interval missing')
        raw = raw_command(payload,row['command_index'],argv(sample_script(remote,row['nonce']))); lines=raw.splitlines()
        if len(lines) != 3 or lines[0] != env['boot_id'] or lines[2] != env['boot_id'] or parse(lines[1],row['nonce']) != row['value']:
            raise ValueError('raw actual boot-bound clock observation differs')
    if rows[1]['host_started_ns'] < rows[0]['host_finished_ns'] or compare(rows[0]['value'],rows[1]['value']) != v.get('comparison'):
        raise ValueError('actual clock phases or elapsed intervals differ')
    quiet = payload.get('stable_seconds_without_external_keepalive')
    if type(quiet) is not int or rows[1]['host_started_ns'] - rows[0]['host_finished_ns'] < quiet * 1000000000:
        raise ValueError('clock observations do not enclose the actual quiet stability interval')
    cleanup = raw_command(payload,v['cleanup_command'],argv(cleanup_script(directory,remote,v['binary']['sha256'],token)))
    if cleanup.strip() != 'CLOCK_HELPER_REMOVED '+token: raise ValueError('clock helper cleanup differs')
    indices = [v['create_command'],v['send_command'],v['staging_command'],rows[0]['command_index'],rows[1]['command_index'],v['cleanup_command']]
    if indices != sorted(set(indices)): raise ValueError('actual clock deployment/sample/cleanup command order differs')
    return v['comparison']
