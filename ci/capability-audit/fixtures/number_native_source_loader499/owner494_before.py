"""Dedicated Number-only entry using the reviewed profile393/CID396 Owner.

No signing, SDK build, Docker construction, guest attachment, arbitrary callback
selection or full-suite claim. Root supplies actual immutable input descriptors.
Resource execution is deliberately only run(...), not a CLI --execute shortcut.
"""
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import sys
import time
from types import SimpleNamespace

R = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = R / '.tmp/parallel-capability-20261016'
HERE = Path(__file__).resolve().parent
KIT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-suite-after488-generated/kit-054d684-494')
KIT_SHA = '3adab8ddc8fc3afba5f42779ba0e8644187f1ed1e84b0267d1044f4bec7ee2f6'
SOURCE_COMMIT = '054d684589538d12f6e6c1981ccff80c5137f8a3'
COLLECTOR = HERE.parent / 'number_local_collector411.py'
COLLECTOR_SHA = '6f9a1fff50af9c3111e70a9646fa8d1aab0836c1b7f9668a8eb8cca31feb84de'
HOST_PYTHON = '/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python'
ACTOR_SHA = 'a374f8f7b767203c5cad2d8edbff179fee6e85fd2483e6ae69e5e1dab4bf8b6b'
BOOT = R / 'ci/capability-audit/boot_package.py'
BOOT_SHA = 'c4faf147174534dcd50bdaa720777dd0281f5fb86056dea55892b8708b13db00'
HELPER_KIT = HERE / 'helper-kit'
HELPER_KIT_SHA = 'c5ae272eaa3c24f45c24f3010abecbe8dcf6fdc70a9c1ae286f62ea4f0e160a5'
ADMISSION_SHA = '3619c17e4d91db1e54106831ba4fd53f122e49be98d4c451ff8cc69710edc125'
UUID = r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}'
IDENTITY_SCRIPT = 'id -u; param get const.product.devicetype; uname -m'
ACCOUNT_SCRIPT = 'echo "bootevent.account.ready=$(param get bootevent.account.ready)"; hidumper -s AccountMgr -a "-os_account_infos"'
VERSION_SCRIPT = 'param get const.ohos.apiversion; param get const.ohos.fullname; param get bootevent.boot.completed; bm get --udid'
PHASES = {'system-granted': ('cycle', 'prepare-persist', 'verify-persist'),
          'system-readonly': ('system-denied',), 'ordinary': ('ordinary-denied',)}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path):
    p = Path(path)
    need(p.is_absolute() and p.resolve() == p and not p.is_symlink(), 'canonical actual file required')
    s = p.stat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular nonalias file required')
    return p


def write(path, row):
    with Path(path).open('x') as stream:
        json.dump(row, stream, indent=2, allow_nan=False); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    return dict(path=str(path), sha256=digest(path), bytes=Path(path).stat().st_size)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_frozen_kit(expected, kit, *, docker_alias=False):
    # Equivalent to original run_full_suite377.verify_kit, with a separately
    # pinned fixed manifest and the exact one permitted Docker alias only.
    manifest = regular(kit / 'manifest.json')
    need(digest(manifest) == expected, 'frozen private manifest differs')
    wanted = set()
    for row in json.loads(manifest.read_text())['members']:
        relative = Path(row['path'])
        need(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix() == row['path'] and
             row['path'] not in wanted, 'unsafe/duplicate frozen member')
        wanted.add(row['path']); path = kit / relative
        need(stat.S_IMODE(path.lstat().st_mode) == row['mode'], 'frozen member mode changed')
        if row['kind'] == 'symlink':
            need(docker_alias and row['path'] == 'bin/docker' and row['target'] == '../docker_shim377.py' and
                 path.is_symlink() and os.readlink(path) == row['target'] and path.resolve() == kit / 'docker_shim377.py',
                 'unknown private tool alias')
        else:
            need(row['kind'] == 'file' and not path.is_symlink() and path.is_file() and
                 path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], 'frozen member changed')
    actual = {p.relative_to(kit).as_posix() for p in kit.rglob('*') if p.is_file() or p.is_symlink()}
    need(actual == wanted | {'manifest.json'}, 'unlisted private source/cache/evidence members')


def source_modules():
    need(sys.dont_write_bytecode, 'root must use Python -B/PYTHONDONTWRITEBYTECODE; frozen kits are read-only')
    verify_frozen_kit(KIT_SHA, KIT, docker_alias=True)
    verify_frozen_kit(HELPER_KIT_SHA, HELPER_KIT)
    need(digest(regular(COLLECTOR)) == COLLECTOR_SHA and digest(regular(BOOT)) == BOOT_SHA and
         digest(regular(HERE / 'qmp_actor394.py')) == ACTOR_SHA and
         digest(regular(HERE / 'observer_admission396.py')) == ADMISSION_SHA,
         'fixed collector/boot/QMP/admission source changed')
    for name,path,pin in ((
        'napi_protocol411', HERE.parent/'napi_protocol411.py', '03ae5a3a5d5cdc4932e6421bc64c39e06880b701326682bb6dfaf0c4d7c5ec49'),
        ('native_observation411', HERE/'native_observation411.py', '0d3e7f9a238095e66fb9cd17806e62fa9ef518339940a376a515afa19f1571c5')):
        need(digest(regular(path)) == pin,'fixed Number411 supplement changed')
        if name in sys.modules: need(Path(sys.modules[name].__file__).resolve() == path,'foreign Number411 supplement')
    sys.path.insert(0,str(HERE)); sys.path.insert(0,str(HERE.parent))
    sys.path.insert(0, str(KIT)); sys.path.insert(1, str(R / 'ci/capability-audit'))
    for name in ('held376', 'policy377', 'run_full_suite_owner376', 'boot_package'):
        if name in sys.modules:
            expected = BOOT if name == 'boot_package' else KIT / (name + '.py')
            need(Path(sys.modules[name].__file__).resolve() == expected, 'foreign module already loaded: ' + name)
    import run_full_suite_owner376 as owner
    return owner, load(COLLECTOR, 'fixed_number_collector411')


class ProcBSDInfo(ctypes.Structure):
    # sys/proc_info.h:59..81, MAXCOMLEN=16 from sys/param.h:95.
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
    _fields_ += [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


def darwin_birth(pid):
    """Actual Darwin kernel start timeval, never a host sampling timestamp."""
    need(sys.platform == 'darwin' and type(pid) is int and pid > 0 and ctypes.sizeof(ProcBSDInfo) == 136,
         'reviewed Darwin proc_bsdinfo ABI only')
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    call = lib.proc_pidinfo
    call.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    call.restype = ctypes.c_int
    value = ProcBSDInfo()
    need(call(pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value)) == ctypes.sizeof(value),
         'actual kernel process-birth query failed')
    need(value.pid == pid and value.pgid == os.getpgid(pid) and value.uid == os.getuid() and
         value.start_sec > 0 and 0 <= value.start_usec < 1000000, 'kernel process identity differs')
    return dict(api='proc_pidinfo.PROC_PIDTBSDINFO', pid=pid, pgid=value.pgid,
                seconds=value.start_sec, microseconds=value.start_usec,
                incarnation=value.start_sec * 1000000 + value.start_usec,
                unit='Darwin kernel process start timeval in microseconds; NOT Linux ticks')


def block_identity(rows, directory):
    """Use actual QMP attached files, then actual stat; never guess an attachment."""
    need(type(rows) is list and rows, 'actual nonempty QMP block inventory required')
    root = Path(directory) / 'images'; result = []; selected = []
    for row in rows:
        need(type(row) is dict and type(row.get('device')) is str, 'typed block device required')
        inserted = row.get('inserted')
        if inserted is None:
            continue
        need(type(inserted) is dict and inserted.get('drv') == 'raw' and type(inserted.get('ro')) is bool,
             'only actual raw block attachments admitted')
        p = regular(inserted['file'])
        need(p.parent == root and inserted.get('image', {}).get('filename') == str(p),
             'attached file is not the actual current package image')
        s = p.stat()
        item = dict(device=row['device'], path=str(p), dev=s.st_dev, inode=s.st_ino,
                    bytes=s.st_size, mode=stat.S_IMODE(s.st_mode), read_only=inserted['ro'])
        result.append(item)
        if p.name == 'userdata.img' and inserted['ro'] is False:
            selected.append(item)
    need(len(selected) == 1 and len({r['path'] for r in result}) == len(result),
         'one actual attached writable userdata disk and no aliases required')
    return selected[0], sorted(result, key=lambda row: row['path'])


class Bridge:
    def __init__(self, owner, collector_module, spec, observer):
        self.owner, self.guest, self.c, self.spec = owner, owner.vm, collector_module, spec
        self.calls, self.reboot_count, self.original = [], 0, None
        self.installed_haps = set()
        self.observer = observer
        self.current_bms, self.phase_files, self.contexts, self.actual_pids = {}, {}, {}, {}
        self.observer_stat, self.runtime_boot = None, None
        self.native_observations = []
        self.out = owner.output / 'number-owner'; self.out.mkdir(mode=0o700)
        self.pulls = self.out / 'pulls'; self.pulls.mkdir(mode=0o700)

    def observer_status(self, raw):
        lines = raw.decode('ascii').splitlines()
        need(len(lines) == 2 and re.fullmatch(r'[0-9]+ [0-9]+ [0-7]{3,4} [0-9]+ [0-9]+ [0-9]+ [0-9]+', lines[0]),
             'actual uploaded helper stat grammar required')
        values = [int(v, 8 if i == 2 else 10) for i, v in enumerate(lines[0].split())]
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](.+)', lines[1])
        need(values[0] == 0 and values[2] == 0o500 and values[3] == self.observer.binary_record['bytes'] and
             values[4] > 0 and values[5] > 0 and values[6] == 1 and match is not None and
             match[1] == self.observer.binary_record['sha256'] and match[2] == self.c.TOKEN_QUERY,
             'actual uploaded helper UID/mode/size/device/inode/nonalias/full SHA differs')
        return dict(uid=values[0], gid=values[1], mode=values[2], bytes=values[3], dev=values[4],
                    inode=values[5], nlink=values[6], sha256=match[1], path=match[2])

    def check_observer_file(self):
        need(digest(regular(self.observer.binary)) == self.observer.binary_record['sha256'] and
             self.observer.binary.stat().st_size == self.observer.binary_record['bytes'],
             'admitted actual host ELF changed after build/recheck admission')
        result = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', self.c.stat_script(self.c.TOKEN_QUERY)],
                           'number-observer-actual-stat-and-full-hash')
        need(result['exit_code'] == 0 and not self.calls[-1]['transport_failure'], 'actual guest helper stat/hash failed')
        actual = self.observer_status(result['stdout'])
        if self.observer_stat is None:
            self.observer_stat = actual
        else:
            need(self.observer_stat == actual, 'uploaded helper inode/metadata/bytes changed before or after query')
        write(self.out / ('observer-stat-%04d.json' % len(self.calls)), actual)

    def verify_observer(self):
        self.check_observer_file()
        boot = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', 'cat', '/proc/sys/kernel/random/boot_id'],
                         'number-observer-actual-boot')
        value = boot['stdout'].decode('ascii').strip()
        need(boot['exit_code'] == 0 and not self.calls[-1]['transport_failure'] and re.fullmatch(UUID, value),
             'actual same guest boot required for observer runtime checks')
        if self.runtime_boot != value:
            product = sys.modules['fixed_number_admission396'].product_module()
            observations = []
            for soname in self.observer.needed:
                script = product.runtime_guest_script(self.observer.helper, soname)
                actual = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', script], 'number-actual-installed-DSO-' + soname)
                need(actual['exit_code'] == 0 and not self.calls[-1]['transport_failure'], 'actual guest installed DSO observation failed')
                observations.append(product.verify_guest_runtime_raw(self.observer.helper, soname,
                    actual['stdout'].decode('ascii'), archive_sha256=self.owner.config['archive']['sha256']))
            write(self.out / ('observer-runtime-%04d.json' % len(self.calls)),
                  dict(boot_id=value, actual_guest_DSOs=observations,
                       scope='same-new-guest installed DSO full hashes; NOT process loaded maps'))
            self.runtime_boot = value

    def prepare_observer(self):
        # No caller/permission action can precede actual source/build/ELF and
        #upload admission. Unknown preexisting guest files are never replaced.
        need(self.c.TOKEN_QUERY == '/data/local/tmp/number-token395' and self.observer_stat is None,
             'one fixed observer upload only')
        need(digest(regular(self.observer.binary)) == self.observer.binary_record['sha256'], 'actual admitted ELF changed')
        absence = 'test ! -e ' + self.c.TOKEN_QUERY + ' && test ! -L ' + self.c.TOKEN_QUERY
        row = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', absence], 'number-observer-target-must-be-absent')
        need(row['exit_code'] == 0 and not self.calls[-1]['transport_failure'], 'unknown existing guest helper target; untouched')
        row = self.leaf([self.owner.hdc, '-t', self.guest.target, 'file', 'send', str(self.observer.binary), self.c.TOKEN_QUERY],
                        'number-actual-admitted-ELF-upload', 90)
        need(row['exit_code'] == 0 and not self.calls[-1]['transport_failure'], 'actual observer upload failed')
        row = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', 'chmod', '500', self.c.TOKEN_QUERY],
                        'number-root-owned-observer-mode')
        need(row['exit_code'] == 0 and not self.calls[-1]['transport_failure'], 'actual observer mode failed')
        self.verify_observer()
        write(self.out / 'admitted-observer.json', self.observer.evidence)

    def require_profile_udids(self):
        """Fresh real BM identity, between two real boot reads, before install."""
        rows = []
        for argv, label in ((['cat', '/proc/sys/kernel/random/boot_id'], 'number-signing-current-boot-before'),
                            (['bm', 'get', '--udid'], 'number-signing-actual-BM-UDID'),
                            (['cat', '/proc/sys/kernel/random/boot_id'], 'number-signing-current-boot-after')):
            actual = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', *argv], label)
            need(type(actual['exit_code']) is int and actual['exit_code'] == 0 and
                 not self.calls[-1]['transport_failure'] and actual['stderr'] == b'',
                 'actual fresh Number BM/boot observation failed')
            rows.append(actual)
        before, bm, after = [row['stdout'].decode('ascii').replace('\r', '').splitlines() for row in rows]
        need(len(before) == len(after) == 1 and before == after and re.fullmatch(UUID, before[0]) and
             before[0] == self.guest.report['test_environment']['boot_id'],
             'pre-install UDID belongs to a changed or stale Number boot')
        need(len(bm) == 2 and bm[0] == 'udid of current device is :' and
             re.fullmatch('[A-Fa-f0-9]{64}', bm[1]) and bm[1].lower() not in ('0'*64, 'f'*64) and
             bm[1] == self.guest.udid, 'one actual BM UDID matching the fresh original boot is required')
        need(set(self.spec['roles']) == set(self.c.ROLES), 'exact three independently signed Number roles required')
        signatures = {}
        for role in self.c.ROLES:
            item = self.spec['roles'][role]
            receipt = self.c.checked(item['signing_receipt'])
            sign = self.c.decode(receipt.read_bytes())
            need(sign['status'] == 'pass' and sign['scope'] == 'actual_signature_profile_and_codesign_NOT_guest' and
                 sign['role'] == role and sign['unsigned_sha256'] == item['unsigned_hap']['sha256'] and
                 sign['signed_sha256'] == item['signed_hap']['sha256'],
                 'original independently verified signing receipt differs before install')
            profile = sign['verified_profile']
            need(profile['bundle-info']['bundle-name'] == self.c.ROLES[role][0] and
                 type(profile.get('debug-info')) is dict and
                 profile['debug-info'].get('device-ids') == [bm[1]],
                 'each exact signed profile must contain only this fresh Number BM UDID')
            self.c.checked(item['signing_receipt'])
            signatures[role] = dict(signing_receipt=self.c.record(receipt),
                                    signed_hap=item['signed_hap'], device_ids=profile['debug-info']['device-ids'])
        self.held()
        write(self.out / 'pre-install-profile-UDID.json', dict(
            scope='actual fresh Number boot/BM raw joined to all three independently verified signed profiles; NOT installation',
            boot_id=before[0], udid=bm[1], target=self.guest.target, archive_sha256=self.owner.config['archive']['sha256'],
            actual_calls=[dict(argv=r['argv'], exit_code=r['exit_code'], stdout_hex=r['stdout'].hex(),
                               stderr_hex=r['stderr'].hex()) for r in rows], signatures=signatures))

    def held(self):
        self.owner.held_binding(self.guest)
        s, n = os.fstat(self.owner.lease_fd), self.owner_module.LOCK.stat()
        need((s.st_dev, s.st_ino) == (n.st_dev, n.st_ino) and s.st_nlink == 1,
             'actual retained lease inode changed')
        fcntl.flock(self.owner.lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def leaf(self, argv, label, timeout=30, *, qmp=False):
        self.held()
        index = len(self.owner.authority.handles)
        log = self.out / ('command-%04d.log' % len(self.calls))
        try:
            if qmp:
                expected = [HOST_PYTHON, str(HERE / 'qmp_actor394.py'), '--socket', str(self.guest.qmp_path),
                            '--action', argv[-1]]
                need(argv == expected and argv[-1] in ('query-block', 'reset') and
                     digest(HERE / 'qmp_actor394.py') == ACTOR_SHA, 'unknown host constructor')
                actual, _, _ = self.owner.direct(argv, label=label, timeout=timeout, log=log)
            else:
                need(argv[:4] == [self.owner.hdc, '-t', self.guest.target, 'shell'] or
                     argv[:5] == [self.owner.hdc, '-t', self.guest.target, 'file', 'recv'] or
                     argv == [self.owner.hdc, '-t', self.guest.target, 'file', 'send', str(self.observer.binary), self.c.TOKEN_QUERY] or
                     argv[:4] == [self.owner.hdc, '-t', self.guest.target, 'install'], 'Number operation outside fixed HDC surface')
                actual, _, _ = self.owner.guest_command(self.guest, argv, label=label, timeout=timeout, log=log)
            need(len(self.owner.authority.handles) == index + 1 and
                 self.owner.authority.handles[index].argv == argv, 'one actual serial held command required')
            result = dict(argv=actual['argv'], exit_code=actual['exit_code'],
                stdout=(self.owner.output / ('leaf-%04d.stdout' % index)).read_bytes(),
                stderr=(self.owner.output / ('leaf-%04d.stderr' % index)).read_bytes())
            from hdc_transport import failed
            transport_failure = False if qmp else failed(result['stdout'].decode('utf-8', 'replace'), result['stderr'].decode('utf-8', 'replace'))
            row = dict(argv=argv, exit_code=result['exit_code'], stdout_hex=result['stdout'].hex(),
                       stderr_hex=result['stderr'].hex(), transport_failure=transport_failure, held_index=index)
            write(self.out / ('call-%04d.json' % len(self.calls)), row); self.calls.append(row)
            return result
        except BaseException as error:
            # Authority already retains timeout/unknown-child raw files/handles.
            write(self.out / ('command-exception-%04d.json' % len(self.calls)),
                  dict(argv=argv, error=type(error).__name__ + ': ' + str(error), held_index=index))
            raise

    def shell(self, argv):
        need(type(argv) is list and argv and all(type(x) is str and '\x00' not in x for x in argv), 'literal shell argv required')
        fixed = argv in (['param', 'get', 'const.global.region'], ['cat', '/proc/sys/kernel/random/boot_id'],
                         ['sync'], ['hilog', '-x'], [IDENTITY_SCRIPT], [ACCOUNT_SCRIPT], [VERSION_SCRIPT])
        bundles = {r[0]: role for role, r in self.c.ROLES.items()}
        bms = len(argv) == 4 and argv[:3] == ['bm', 'dump', '-n'] and argv[3] in bundles
        hap = len(argv) == 2 and argv[0] == 'sha256sum' and argv[1] in self.installed_haps
        start = any(argv == ['aa', 'start', '-b', row[0], '-a', 'EntryAbility', '--ps', 'run', self.spec['runs'][role],
                            '--ps', 'phase', phase, '--ps', 'number', self.spec['number']]
                    for role, row in self.c.ROLES.items() for phase in PHASES[role])
        find = next(((role, phase) for role in PHASES for phase in PHASES[role]
                     if argv == [self.c.find_script(self.spec['runs'][role], phase)]), None)
        observed_paths = {p for paths in self.phase_files.values() for p in paths}
        file_stat = any(argv == [self.c.stat_script(path)] for path in observed_paths)
        pidof = len(argv) == 2 and argv[0] == 'pidof' and argv[1] in bundles
        proc = any(argv == ['cat', '/proc/' + pid + '/' + leaf]
                   for pid in self.actual_pids.values() for leaf in ('status', 'cmdline', 'stat'))
        namespace = any(argv == [self.c.stat_script('/proc/' + self.actual_pids[role] + '/root' + context + '/' + Path(path).name,
                                     process_root=True)]
                        for (role, phase), context in self.contexts.items() if role in self.actual_pids
                        for path in self.phase_files.get((role, phase), ()))
        query = next((role for role, row in self.c.ROLES.items() if role in self.current_bms and
                      len(argv) == 5 and argv[0] == self.c.TOKEN_QUERY and argv[1] == self.spec['runs'][role] and
                      argv[2] in ('identity', *PHASES[role]) and argv[3] == row[0] and
                      argv[4] == str(self.current_bms[role]['token'])), None)
        import napi_protocol411 as napi
        napi_start = next((role for role,row in self.c.ROLES.items() if argv ==
            ['aa','start','-b',row[0],'-a','EntryAbility','--ps','run',self.spec['runs'][role],
             '--ps','phase','napi-read','--ps','number',self.spec['number'],'--ps','ownerRun',self.spec['runs']['system-granted']]),None)
        napi_find = next((role for role in self.c.ROLES if argv == [napi.find_script(self.spec['runs'][role])]),None)
        need(fixed or bms or hap or start or find is not None or file_stat or pidof or proc or namespace or query is not None or napi_start is not None or napi_find is not None,
             'unadmitted Number argv; only fixed producer/actual observed paths and tokens allowed')
        if start and argv[11] == 'cycle':
            self.capture_native411('datashare-cycle-before')
        if napi_start is not None:
            self.capture_native411(napi_start+'-before')
        if query is not None:
            self.verify_observer()
        actual = self.leaf([self.owner.hdc, '-t', self.guest.target, 'shell', *argv], 'number-read-or-call')
        need(not self.calls[-1]['transport_failure'], 'actual HDC failure preserved; no false host0 success')
        if actual['exit_code'] == 0:
            if bms:
                role = bundles[argv[3]]
                value = self.c.bms_fields(actual['stdout'], argv[3], self.spec['roles'][role]['bms']['fields'])
                need(type(value['token']) is int and value['token'] > 0, 'actual BMS token required for fixed query')
                self.current_bms[role] = value; self.installed_haps.add(value['installedHapPath'])
            if find is not None:
                self.phase_files[find] = self.c.discovered_files(actual['stdout'], self.spec['runs'][find[0]], find[1])
            if napi_find is not None:
                self.phase_files[(napi_find,'napi-read')] = napi.discovered(actual['stdout'],self.spec['runs'][napi_find])
            if pidof:
                pid = actual['stdout'].decode('ascii').strip()
                need(re.fullmatch('[1-9][0-9]*', pid), 'one real Number role PID required')
                self.actual_pids[bundles[argv[1]]] = pid
        if query is not None:
            self.check_observer_file()
        return actual

    def pull(self, remote):
        self.c.guest_path(remote)
        need(remote in {p for paths in self.phase_files.values() for p in paths}, 'pull only actual unique find observation')
        basename = remote.rsplit('/', 1)[-1]
        import napi_protocol411 as napi
        napi_name = any(basename in napi.names(run) for run in self.spec['runs'].values())
        need(napi_name or any(basename in ('number-local375-' + run + '-' + phase + '.jsonl',
                             'number-token377-' + run + '-' + phase + '.json')
                 for role, run in self.spec['runs'].items() for phase in PHASES[role]),
             'only this actual run/phase caller journal or Token sidecar can be pulled')
        path = self.pulls / ('payload-%04d.raw' % len(self.calls))
        actual = self.leaf([self.owner.hdc, '-t', self.guest.target, 'file', 'recv', remote, str(path)], 'number-pull')
        need(not self.calls[-1]['transport_failure'], 'actual failed pull transport retained')
        return dict(call=actual, file=self.c.record(path) if actual['exit_code'] == 0 else None)

    def ui(self, action):
        need(set(action) == {'kind', 'bundle', 'run', 'phase', 'timeout_seconds'} and
             action['kind'] == 'wait_actual_number_summary' and action['bundle'] in {r[0] for r in self.c.ROLES.values()} and
             action['run'] in self.spec['runs'].values() and re.fullmatch('[a-f0-9]{32}', action['run']) and
             type(action['timeout_seconds']) is int and 1 <= action['timeout_seconds'] <= 300,
             'fixed actual D2 summary wait only')
        need(any(action['bundle'] == row[0] and action['run'] == self.spec['runs'][role] and
                 action['phase'] in (*PHASES[role],'napi-read') for role, row in self.c.ROLES.items()),
             'exact actual role/run/phase summary join required')
        prefix = 'NUMBER_NAPI411 ' if action['phase'] == 'napi-read' else 'NUMBER_LOCAL375 '
        calls = []; deadline = time.monotonic() + action['timeout_seconds']
        while time.monotonic() < deadline:
            actual = self.shell(['hilog', '-x']); calls.append(actual)
            need(actual['exit_code'] == 0, 'summary wait HDC failed')
            matches = []
            for line in actual['stdout'].decode('utf-8', 'strict').splitlines():
                if prefix not in line:
                    continue
                raw = line.split(prefix, 1)[1].encode()
                try:
                    row = self.c.decode(raw)
                except (ValueError, UnicodeError):
                    continue  # No candidate success from malformed/truncated logs.
                if (row.get('run'), row.get('phase'), row.get('event')) == (action['run'], action['phase'], 'summary'):
                    matches.append(row)
            need(len(matches) <= 1, 'duplicate actual run/phase summary')
            if matches:
                role = next(r for r, row in self.c.ROLES.items() if row[0] == action['bundle'])
                if action['phase'] == 'napi-read':
                    import napi_protocol411 as napi
                    self.contexts[(role,action['phase'])] = napi.context(calls,action['run'],self.spec['runs']['system-granted'],self.spec['number'])
                    self.capture_native411(role+'-after')
                else:
                    self.contexts[(role, action['phase'])] = self.c.logged_context(calls, action['run'], action['phase'])
                    if action['phase'] == 'cycle': self.capture_native411('datashare-cycle-after')
                return calls  # Original independent journal/Token pulls still decide every result.
            time.sleep(.5)
        raise ValueError('actual D2 summary not observed within finite wait; raw attempts retained')

    def capture_native411(self, label):
        import native_observation411
        actual = native_observation411.capture(self,label)
        if label.endswith('-after'):
            prior = next((v for v in reversed(self.native_observations) if v['label'] == label[:-5]+'before'),None)
            need(prior is not None and prior['boot_id'] == actual['boot_id'], 'native NAPI observation crossed boot')
            if not prior.get('process_absent') and not actual.get('process_absent'):
                need(prior['process'] == actual['process'], 'provider PID/birth/UID changed across public-call window')
            actual['public_call_window_before'] = prior['evidence']
        actual['evidence'] = write(self.out / ('native411-'+label+'.json'),actual)
        self.native_observations.append(actual)

    def qmp(self, action):
        result = self.leaf([HOST_PYTHON, str(HERE / 'qmp_actor394.py'), '--socket', str(self.guest.qmp_path),
                            '--action', action], 'number-fixed-QMP-' + action, 25, qmp=True)
        need(result['exit_code'] == 0, 'actual QMP actor failed; full raw transcript retained')
        rows = [self.c.decode(line) for line in result['stdout'].splitlines()]
        need(rows and rows[-1].get('outcome') == 'complete' and rows[-1].get('action') == action,
             'complete fixed actor result required')
        return result, rows[-1]['result']

    def capture_vm(self, name):
        self.held(); env = self.guest.report['test_environment']
        pid = env['qemu_pid']
        need(pid == self.guest.process.pid, 'this dedicated entry requires launcher exec into the same retained QEMU PID')
        birth = darwin_birth(pid)
        # Actual QemuGuest already collected its ps command; recheck the live
        # process executable through the same held Owner permitted ps leaf.
        index = len(self.owner.authority.handles)
        argv = ['ps', '-p', str(pid), '-o', 'command=']
        record, _, _ = self.owner.guest_command(self.guest, argv, label='number-own-QEMU-command', timeout=15,
                                               log=self.out / (name + '-qemu-command.log'))
        need(len(self.owner.authority.handles) == index + 1 and record['exit_code'] == 0, 'actual held QEMU command failed')
        command_raw = (self.owner.output / ('leaf-%04d.stdout' % index)).read_bytes()
        stderr_raw = (self.owner.output / ('leaf-%04d.stderr' % index)).read_bytes()
        write(self.out / (name + '-qemu-command.raw.json'), dict(argv=argv, exit_code=record['exit_code'],
              stdout_hex=command_raw.hex(), stderr_hex=stderr_raw.hex(), held_index=index))
        command = shlex.split(command_raw.decode().strip())
        need(not stderr_raw and command == shlex.split(env['qemu_command']) and
             not any(arg.split('=', 1)[0] in {'-no-reboot', '-no-shutdown', '-daemonize', '-snapshot', '-action'} for arg in command) and
             str(self.guest.qmp_path) in ' '.join(command) and str(self.guest.directory / 'images') in ' '.join(command),
             'actual QEMU argv has unsupported exit/disk/daemon semantics')
        _, blocks = self.qmp('query-block')
        disk, all_disks = block_identity(blocks, self.guest.directory)
        value = dict(purpose='number-only', qemu_pid=pid, qemu_start_ticks=birth['incarnation'],
            writable_image=disk['path'], image_dev=disk['dev'], image_inode=disk['inode'], lease_held=True,
            package_sha256=self.owner.config['archive']['sha256'], hdc_target=self.guest.target)
        invariant = dict(vm=value, birth=birth, disks=all_disks, command=command,
                         socket=str(self.guest.qmp_path), held_leader=self.guest.process.pid)
        if self.original is None:
            self.original = invariant
        else:
            need(invariant == self.original, 'held QEMU kernel incarnation/actual disks/argv changed across reset')
        # Extra source/unit information accompanies, rather than rewriting, the
        # legacy numeric collector field. It is explicitly NOT Linux jiffies.
        evidence = write(self.out / (name + '-held-vm.json'), dict(**value, kernel_birth=birth,
            actual_disks=all_disks, actual_qemu_argv=command, socket=str(self.guest.qmp_path),
            observation_name=name, scope='actual fixed Number-only pipeline; no aggregate gate'))
        return dict(record=evidence, fields={key: [key] for key in self.c.VM_FIELDS})

    def controlled_reboot(self, request):
        need(self.reboot_count == 0 and set(request) == {'expected_vm', 'previous_boot_id'} and
             request['expected_vm'] == self.original['vm'], 'one controlled same-held Number reset only')
        self.reboot_count += 1; calls = []
        before = self.shell(['cat', '/proc/sys/kernel/random/boot_id']); calls.append(before)
        need(before['exit_code'] == 0 and before['stdout'].decode().strip() == request['previous_boot_id'],
             'actual pre-reset boot differs')
        self.capture_vm('pre-reset')
        synced = self.shell(['sync']); calls.append(synced); need(synced['exit_code'] == 0, 'actual guest sync failed')
        reset, _ = self.qmp('reset'); calls.append(reset)
        from boot_package import validate_identity, parse_snapshot, check_guest_version
        deadline = time.monotonic() + 300; ready = False
        while time.monotonic() < deadline:
            self.held()
            for argv in ([self.owner.hdc, 'tconn', self.guest.target],
                         [self.owner.hdc, '-t', self.guest.target, 'shell', 'cat', '/proc/sys/kernel/random/boot_id']):
                if argv[1] == 'tconn':
                    index = len(self.owner.authority.handles)
                    result, _, _ = self.owner.guest_command(self.guest, argv, label='number-reboot-tconn', timeout=10,
                                                          log=self.out / ('reboot-connect-%04d.log' % len(calls)))
                    need(len(self.owner.authority.handles) == index + 1, 'one actual reconnect command required')
                    actual = dict(argv=argv, exit_code=result['exit_code'],
                        stdout=(self.owner.output / ('leaf-%04d.stdout' % index)).read_bytes(),
                        stderr=(self.owner.output / ('leaf-%04d.stderr' % index)).read_bytes())
                    write(self.out / ('reboot-connect-%04d.raw.json' % len(calls)),
                          dict(argv=argv, exit_code=actual['exit_code'], stdout_hex=actual['stdout'].hex(), stderr_hex=actual['stderr'].hex()))
                else:
                    actual = self.leaf(argv, 'number-reboot-boot-id', 10)
                calls.append(actual)
            value = actual['stdout'].decode('ascii', 'replace').strip()
            if actual['exit_code'] == 0 and re.fullmatch(UUID, value) and value != request['previous_boot_id']:
                # A new boot_id may appear before account/SceneBoard readiness.
                # Retain every real attempt; only source-backed parsers decide
                # readiness, with the same overall bounded deadline.
                identity = self.shell([IDENTITY_SCRIPT]); calls.append(identity)
                account = self.shell([ACCOUNT_SCRIPT]); calls.append(account)
                version = self.shell([VERSION_SCRIPT]); calls.append(version)
                try:
                    need(all(row['exit_code'] == 0 for row in (identity, account, version)), 'readiness command nonzero')
                    validate_identity(identity['stdout'].decode().replace('\r', ''), self.guest.arch, self.guest.device)
                    need(all(parse_snapshot(account['stdout'].decode().replace('\r', '')).values()) and
                         check_guest_version(version['stdout'].decode().replace('\r', '')) == self.guest.udid,
                         'actual reboot account/API26/UDID not ready')
                    need(time.monotonic() <= deadline, 'reboot readiness exceeded its finite deadline')
                    ready = True; break
                except ValueError:
                    pass
            time.sleep(1)
        need(ready, 'same held QEMU did not publish a different actual boot_id')
        after = self.capture_vm('post-reset')
        # Do not drop nonzero offline attempts or manufacture success. Existing
        #395 collector will fail every such transcript. The raw transition is
        #preserved even if the existing contract cannot yet accept that boot.
        from hdc_transport import failed
        transport = [i for i, row in enumerate(calls) if row['argv'][0] == self.owner.hdc and
                     failed(row['stdout'].decode('utf-8', 'replace'), row['stderr'].decode('utf-8', 'replace'))]
        write(self.out / 'controlled-reset.json', dict(after_vm=after, actual_calls=[dict(argv=r['argv'],
            exit_code=r['exit_code'], stdout_hex=r['stdout'].hex(), stderr_hex=r['stderr'].hex()) for r in calls],
            transport_failure_indices=transport, transition_all_calls_zero_required_by_original_collector=True))
        need(not transport, 'actual reboot transport failures retained; original all-calls0 contract is still unresolved')
        return dict(calls=calls, after_vm=after)


def finish_and_record(owner, collector, output):
    """Retain actual host closure even when a case/start exception propagates."""
    owner.finish()  # unchanged reviewed WNOWAIT/exact-handle/endpoint closure
    need(owner.cleanup_complete is True, 'original Owner did not establish actual host closure')
    return write(output / 'resource-close.json', dict(cleanup_verified=owner.cleanup_complete,
        held_processes=collector.record(output / 'held-processes.json'),
        scope='owned VM/HDC/process closure ONLY; NOT clock-helper or provider persistent-row cleanup'))


def closed_result(owner, collector, output, report):
    """Reference the final original boot bytes, after finish/close/save."""
    need(owner.cleanup_complete is True, 'final result requires completed actual host closure')
    boot = regular(output / 'boot/boot.json')
    original = collector.decode(boot.read_bytes())
    need(original == owner.vm.report, 'final original boot save differs from its actual report')
    clocks = original.get('watchdog_clocks')
    boot_id = original.get('test_environment', {}).get('boot_id')
    need(type(clocks) is dict and clocks.get('cleanup_complete') is True and
         clocks.get('cleanup_errors') == [] and type(boot_id) is str and
         re.fullmatch(UUID, boot_id) is not None and clocks.get('boot_id') == boot_id,
         'original initial-boot clock cleanup incomplete; host VM closure cannot substitute')
    return write(output / 'number-owner-result.json', dict(
        scope='Number-only; not full47/five-capability closure', collector=report,
        original_full_suite_executed=False, first_artifact_behavior_gate_passed=False,
        actual_guest_boot=collector.record(boot), actual_resource_close=collector.record(output / 'resource-close.json'),
        clock_scope='original completed initial-boot foreground samples/cleanup; no post-reset sample or boot rewrite'))


def run(config_path, config_sha256, spec_path, spec_sha256, output, *, observer_proof):
    """Root invokes once with actual data; no execute code/module in JSON."""
    need(sys.platform == 'darwin' and sys.executable == HOST_PYTHON, 'reviewed literal root Python/Darwin required')
    module, collector = source_modules()
    config = module.load_config(config_path, config_sha256)  # current profile393, four real MIC/profile fields included
    module.sources(applied=True)
    admission_module = load(HERE / 'observer_admission396.py', 'fixed_number_admission396')
    profile_path = regular(config['environment']['OHOS_QA_RUNTIME_PROFILE'])
    profile_descriptor = dict(path=str(profile_path), sha256=digest(profile_path), bytes=profile_path.stat().st_size)
    need(profile_descriptor['sha256'] == config['environment']['OHOS_QA_RUNTIME_PROFILE_SHA256'],
         'actual pinned profile changed between config and observer admission')
    admitted = admission_module.admit(observer_proof, profile_descriptor=profile_descriptor,
                                     archive_sha256=config['archive']['sha256'])
    need(digest(regular(spec_path)) == spec_sha256, 'actual Number spec changed')
    spec = collector.decode(Path(spec_path).read_bytes())
    need(spec.get('source_commit') == SOURCE_COMMIT, 'actual Number spec/SDK must bind reviewed new source commit')
    need(spec.get('vm') is None and spec.get('archive_sha256') == config['archive']['sha256'],
         'Number must start with no preexisting VM and the same held new archive')
    # Original actual SDK/signature/source joins remain required. No signer or
    #builder can be launched by this entry. The fixed395 collector must observe
    #real BMS, context/filesystem and independent access data; no supplied path
    #or report boolean substitutes for those observations.
    output = Path(output)
    need(output.is_absolute() and output.parent.resolve() == output.parent and not output.exists(), 'fresh canonical Number-only output required')
    output.mkdir(mode=0o700)
    class NumberChildren(module.FixedSuiteChildren):
        def command(self, **kwargs):
            raise ValueError('dedicated Number entry has no Docker/SDK/fullsuite constructor callback')
        def finalize(self, *, owner):
            need(not owner.authority.unknown, 'unknown Number constructor requires original quarantine')
    need(module.LOCK.resolve() == module.LOCK and not module.LOCK.is_symlink(), 'shared lock alias refused')
    fd = os.open(module.LOCK, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    owner = None; marker = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        st, named = os.fstat(fd), module.LOCK.stat()
        need((st.st_dev, st.st_ino) == (named.st_dev, named.st_ino) and st.st_nlink == 1 and st.st_uid == os.getuid(), 'actual shared lease identity differs')
        need(not module.MARKER.exists() and not module.MARKER.is_symlink() and
             not (module.BASE / '.representative35-unresolved.json').exists(), 'unresolved root resources require recovery')
        prepared = module.Owner(output, config, NumberChildren(), fd)
        marker = (json.dumps(dict(schema='runtime-owner377-active-or-unresolved/v1', pipeline='fixed-Number411-DataShare-and-NAPI-only',
            nonce=secrets.token_hex(32), pid=os.getpid(), case_root=str(output), lease_device=st.st_dev, lease_inode=st.st_ino), sort_keys=True) + '\n').encode()
        marker_fd = os.open(module.MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(marker_fd, 'wb') as stream:
            stream.write(marker); stream.flush(); os.fsync(stream.fileno())
        owner = prepared
        report = None
        try:
            owner.start_hdc()
            args = SimpleNamespace(archive=owner.archive, output=output / 'boot', hdc=owner.hdc,
                hdc_port=owner.guest_port, accel=config['environment'].get('QEMU_TEST_ACCEL', 'hvf'),
                resolution='1280x800', purpose='acceptance', kernel_diagnostic=None, power_diagnostic_wakeup=False,
                hold=False, candidate_kernel=None, candidate_kernel_evidence=None, power_button_after_quiet=False,
                wait_seconds=1800, stable_seconds=60, clock_probe=module.descriptor(config['clock_probe']),
                clock_probe_build=module.descriptor(config['clock_probe_build']))
            guest = owner.guest_factory(args).start()  # exactly one fresh start; original start closes itself on failure
            inputs = json.loads((guest.directory / 'build-inputs.json').read_text())
            need(inputs['source_git_revision'] == SOURCE_COMMIT == spec['source_commit'], 'actual archive source commit differs from SDK/spec')
            bridge = Bridge(owner, collector, spec, admitted); bridge.owner_module = module
            spec['vm'] = bridge.capture_vm('initial')
            bridge.prepare_observer()
            # Install only independently validated signed roles, then the
            #collector re-observes actual BMS-installed HAP identity itself.
            probe = collector.Collector(spec, dict(shell=bridge.shell, pull=bridge.pull, ui=bridge.ui,
                controlled_reboot=bridge.controlled_reboot), output / 'collector', H)
            collector.permission_source(spec.get('target_permission_source'), spec['source_commit'])
            for role in collector.ROLES:
                probe.role_artifacts(role)
            bridge.require_profile_udids()  # actual new BM raw + three profiles, before any install
            for role in collector.ROLES:
                path = str(collector.checked(spec['roles'][role]['signed_hap']))
                actual = bridge.leaf([owner.hdc, '-t', guest.target, 'install', path], 'number-role-install', 90)
                need(actual['exit_code'] == 0 and not bridge.calls[-1]['transport_failure'], 'actual role installation failed')
            report = probe.collect()
            report['native_observations411'] = [v['evidence'] for v in bridge.native_observations]
            report['native_callback_proven'] = False
            write(output/'native-observations411-index.json',dict(observations=report['native_observations411'],
                scope='same held guest raw observations; independent callback proof remains pending'))
        finally:
            finish_and_record(owner, collector, output)
        closed_result(owner, collector, output, report)
        return 0 if report and report['status'] == 'pass_collector_checks_ONLY' else 1
    except BaseException as error:
        if owner is not None and not owner.cleanup_complete:
            module.quarantine(output, error)
        raise
    finally:
        if marker is not None:
            try:
                need(not module.MARKER.is_symlink() and module.MARKER.stat().st_nlink == 1 and
                     module.MARKER.stat().st_uid == os.getuid() and stat.S_IMODE(module.MARKER.stat().st_mode) == 0o600 and
                     module.MARKER.read_bytes() == marker and (owner is None or owner.cleanup_complete),
                     'foreign marker or unsettled resource remains untouched')
                module.MARKER.unlink()
            except BaseException as error:
                module.quarantine(output, error)
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit('Root must call fixed number_owner411.run(...) after input review; no CLI resource fallback.')
