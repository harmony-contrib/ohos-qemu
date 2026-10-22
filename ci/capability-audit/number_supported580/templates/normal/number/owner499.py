"""Dedicated Number-only entry using the reviewed profile393/CID396 Owner.

No signing, SDK build, Docker construction, guest attachment, arbitrary callback
selection or full-suite claim. Root supplies actual immutable input descriptors.
Resource execution is deliberately only run(...), not a CLI --execute shortcut.
"""
import ctypes
import fcntl
import hashlib
import importlib.util
import importlib.machinery
import builtins
import types
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
KIT = None  # Parent supplies the actual future full-suite sourcekit path.
KIT_SHA = None  # Exact future full-suite manifest hash; old494 is not a substitute.
SOURCE_COMMIT = None  # Actual future integrated HEAD, deliberately unresolved.
NUMBER580_DIRECTORY = None  # fixed normal/number directory; SourceGen typed path, never DATA code selection
NUMBER580_PINS = {'corpus580.py': None, 'protocol580.py': None, 'register580.py': None, 'project580.py': None, 'CONTRACT580.json': None}
COLLECTOR = R / 'ci/capability-audit/number_native496/support/number_local_collector411.py'
COLLECTOR_SHA = '6f9a1fff50af9c3111e70a9646fa8d1aab0836c1b7f9668a8eb8cca31feb84de'
HOST_PYTHON = '/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python'
ACTOR_SHA = 'a374f8f7b767203c5cad2d8edbff179fee6e85fd2483e6ae69e5e1dab4bf8b6b'
BOOT = R / 'ci/capability-audit/boot_package.py'
BOOT_SHA = None  # exact canonical boot_package.py SHA from actual normal snapshot, not legacy c4faf147
NUMBER497_ANCESTOR = R / 'ci/capability-audit/number_native497/number-observer-sourcekit497'
HELPER_KIT = NUMBER497_ANCESTOR / 'helper-kit'
ADMISSION_SOURCE = NUMBER497_ANCESTOR / 'observer_admission396.py'
ACTOR_SOURCE = H / 'root-number494-source/kit411/candidate/qmp_actor394.py'
HELPER_KIT_SHA = '0df64c1b16f1a8fc8b21bbab9645b05b5bba7b8c7dfb9c7f6d386f9a922136fa'
ADMISSION_SHA = 'dd902e6adc39c3f4c45fc6ebd15ee9810e7ebf1a3197ad8d85d67e5c14b3133b'
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



# Exact finite canonical vector, including the independently reviewed498
# consumer/adapter successor. Future HEAD/KIT bindings remain pending.
NATIVE496_CANONICAL_PINS = {'ci/capability-audit/fixtures/batch_apps/number_runtime/number_token_query395.cpp': {'sha256': 'b56d895cddd5dcc375b7b871e871b199540b43c0a495d7ec8b31ff1106a4e5ed',
                                                                                      'bytes': 6767},
 'ci/capability-audit/number_native496/__init__.py': {'sha256': 'd47cad434d266fac6ebc5ca5f94aa3375b28cabcbdaaaf18b5a8cbcaf4348cd3',
                                                      'bytes': 73},
 'ci/capability-audit/number_native496/candidate/native_observation411.py': {'sha256': 'e0cc7372d13c71d3d08269d42ea1c71738d9672761ba4cf17a66d47e8c236bb6',
                                                                             'bytes': 15533},
 'ci/capability-audit/number_native496/candidate/number_token_query395.cpp': {'sha256': 'b56d895cddd5dcc375b7b871e871b199540b43c0a495d7ec8b31ff1106a4e5ed',
                                                                              'bytes': 6767},
 'ci/capability-audit/number_native496/consumer496.py': {'sha256': '9c9719c41d50d8348b96e229bbcdc82f857109ff913c1b5704184aa40a0577cc', 'bytes': 19705},
 'ci/capability-audit/number_native496/evidence_join496.py': {'sha256': '021d564c75f95fa1e99f30814819bd7c961c4155e73d2c78886edeb9fc7f0c99', 'bytes': 36667},
 'ci/capability-audit/number_native496/support/guest_ui.py': {'sha256': '8f8fba0256492ff3d9d8bcfa526540954a8cafa42381cc16fd02c7cd48a4147f',
                                                              'bytes': 7723},
 'ci/capability-audit/number_native496/support/napi_protocol411.py': {'sha256': '03ae5a3a5d5cdc4932e6421bc64c39e06880b701326682bb6dfaf0c4d7c5ec49',
                                                                      'bytes': 8398},
 'ci/capability-audit/number_native496/support/number_local_collector411.py': {'sha256': '6f9a1fff50af9c3111e70a9646fa8d1aab0836c1b7f9668a8eb8cca31feb84de',
                                                                               'bytes': 53733}}


def integration497_ready():
    need(type(SOURCE_COMMIT) is str and re.fullmatch('[0-9a-f]{40}', SOURCE_COMMIT) and
         SOURCE_COMMIT != '054d684589538d12f6e6c1981ccff80c5137f8a3',
         'actual future Number497 integrated HEAD pending; old494 cannot substitute')
    need(isinstance(KIT, Path) and KIT.is_absolute() and KIT.resolve() == KIT and
         type(KIT_SHA) is str and re.fullmatch('[0-9a-f]{64}', KIT_SHA),
         'actual future full-suite sourcekit path/manifest hash pending')
    for relative, row in NATIVE496_CANONICAL_PINS.items():
        need(type(row) is dict and set(row) == {'sha256', 'bytes'} and
             type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']) and
             type(row['bytes']) is int and row['bytes'] > 0,
             'reviewed canonical successor pin pending: ' + relative)


def _native_source_owner499():
    """Keep source module ownership in this Owner's closure, never in DATA."""
    owned = None
    module_table = sys.modules
    prefix = 'number_native496'
    selected = (
        (prefix, 'ci/capability-audit/number_native496/__init__.py'),
        (prefix + '.consumer496', 'ci/capability-audit/number_native496/consumer496.py'),
        (prefix + '.evidence_join496', 'ci/capability-audit/number_native496/evidence_join496.py'))

    def namespace():
        need(type(module_table) is dict and sys.modules is module_table, 'native module table identity changed')
        names = set()
        for name in module_table:
            if isinstance(name, str) and (str.__eq__(name, prefix) is True or str.startswith(name, prefix + '.')):
                need(type(name) is str, 'nonliteral native namespace key refused')
                names.add(name)
        return names

    def verify(state):
        modules, specs, loaders, paths, environments, imports, package_path, package_keys = state
        need(namespace() == set(modules), 'foreign/new native namespace member refused')
        for name, module in modules.items():
            need(type(module) is types.ModuleType, 'owned native object changed module type: ' + name)
            spec = specs[name]; values = module.__dict__
            need(module_table.get(name) is module and
                 type(values.get('__name__')) is str and values['__name__'] == name and
                 type(values.get('__file__')) is str and values['__file__'] == paths[name] and
                 type(values.get('__package__')) is str and values['__package__'] == prefix and
                 values.get('__loader__') is loaders[name] and values.get('__spec__') is spec and
                 '__cached__' in values and values['__cached__'] is None and
                 values.get('__builtins__') is environments[name] and
                 environments[name].get('__import__') is imports[name],
                 'native module object/file/package/loader/spec ownership changed: ' + name)
            need(type(spec) is importlib.machinery.ModuleSpec and type(spec.name) is str and spec.name == name and
                 type(spec.origin) is str and spec.origin == paths[name] and spec.loader is loaders[name] and
                 spec.loader_state is loaders[name] and spec.parent == prefix and
                 spec.has_location is False and spec.cached is None and
                 getattr(spec, '_initializing', None) is False,
                 'native source ModuleSpec changed: ' + name)
            if name == prefix:
                need(values.get('__path__') is package_path is spec.submodule_search_locations and
                     type(package_path) is tuple and package_path == (str(Path(paths[name]).parent),) and
                     set(module.__dict__) == package_keys,
                     'foreign native package path/children refused')
            else:
                need('__path__' not in module.__dict__ and spec.submodule_search_locations is None,
                     'native source child changed into foreign package')
        package = modules[prefix]
        need(package.__dict__.get('consumer496') is modules[prefix + '.consumer496'] and
             package.__dict__.get('evidence_join496') is modules[prefix + '.evidence_join496'] and
             modules[prefix + '.evidence_join496'].__dict__.get('core') is modules[prefix + '.consumer496'],
             'native parent child/core object differs from owned source modules')

    def native_module496():
        nonlocal owned
        integration497_ready()
        raw_sources = {}
        for relative, row in NATIVE496_CANONICAL_PINS.items():
            path = regular(R / relative)
            before = path.stat(); raw = path.read_bytes(); after = path.stat()
            need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                 (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
                 len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                 'exact reviewed canonical native source changed: ' + relative)
            raw_sources[relative] = raw
        if owned is not None:
            verify(owned)
            return owned[0][prefix + '.evidence_join496']
        need(not namespace(), 'preexisting native namespace refused on first owned source load')
        modules = {}; specs = {}; loaders = {}; paths = {}; environments = {}; imports = {}
        inserted = []
        try:
            for name, relative in selected:
                module = types.ModuleType(name); loader = object(); path = str(R / relative)
                spec = importlib.machinery.ModuleSpec(name, loader, origin=path, is_package=(name == prefix))
                spec.loader_state = loader; spec._initializing = False
                if name == prefix: spec.submodule_search_locations = (str(Path(path).parent),)
                module.__file__ = path; module.__package__ = prefix; module.__loader__ = loader
                module.__spec__ = spec; module.__cached__ = None
                if name == prefix: module.__path__ = spec.submodule_search_locations
                modules[name] = module; specs[name] = spec; loaders[name] = loader; paths[name] = path
                module_table[name] = module; inserted.append((name, module))
            package = modules[prefix]
            package.consumer496 = modules[prefix + '.consumer496']
            package.evidence_join496 = modules[prefix + '.evidence_join496']
            for name, relative in selected:
                module = modules[name]
                def fixed_import(import_name, globals=None, locals=None, fromlist=(), level=0,
                                 module=module, name=name):
                    if level == 1 and import_name == '' and tuple(fromlist) == ('consumer496',) and \
                            name == prefix + '.evidence_join496' and globals is module.__dict__:
                        need(module_table.get(prefix) is package and
                             module_table.get(prefix + '.consumer496') is package.consumer496 is modules[prefix + '.consumer496'],
                             'relative native core import lost owned object')
                        return package
                    need(level == 0 and not (import_name == prefix or import_name.startswith(prefix + '.')) and
                         import_name != 'consumer496', 'unowned native import route refused')
                    return builtins.__import__(import_name, globals, locals, fromlist, level)
                environment = dict(vars(builtins)); environment['__import__'] = fixed_import
                environments[name] = environment; imports[name] = fixed_import
                module.__dict__['__builtins__'] = environment
                exec(compile(raw_sources[relative], paths[name], 'exec', dont_inherit=True, optimize=0), module.__dict__)
            state = (modules, specs, loaders, paths, environments, imports, package.__dict__['__path__'], set(package.__dict__))
            verify(state)
            owned = state  # Publish only after all exact source modules and metadata agree.
            return modules[prefix + '.evidence_join496']
        except BaseException:
            for name, module in reversed(inserted):
                if module_table.get(name) is module: del module_table[name]
            raise  # A foreign replacement/new namespace member is never removed here.
    return native_module496


native_module496 = _native_source_owner499()

def number580_modules():
    need(isinstance(NUMBER580_DIRECTORY, Path) and NUMBER580_DIRECTORY.is_absolute() and
         NUMBER580_DIRECTORY.resolve() == NUMBER580_DIRECTORY, 'normal Number580 source directory binding pending')
    need(set(NUMBER580_PINS) == {'corpus580.py','protocol580.py','register580.py','project580.py','CONTRACT580.json'}, 'fixed leaf vector')
    for name, expected in NUMBER580_PINS.items():
        need(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected) and
             digest(regular(NUMBER580_DIRECTORY/name)) == expected, 'fixed leaf source pending/changed: '+name)
    protocol = load(NUMBER580_DIRECTORY/'protocol580.py', 'fixed_number580_protocol')
    need(protocol.CONTRACT_SHA == NUMBER580_PINS['CONTRACT580.json'], 'same immutable contract binding required')
    corpus = load(NUMBER580_DIRECTORY/'corpus580.py', 'fixed_number580_corpus')
    registration = load(NUMBER580_DIRECTORY/'register580.py', 'fixed_number580_registration')
    project = load(NUMBER580_DIRECTORY/'project580.py', 'fixed_number580_project')
    return corpus, protocol, registration, project


def source_modules():
    need(sys.dont_write_bytecode, 'root must use Python -B/PYTHONDONTWRITEBYTECODE; frozen kits are read-only')
    integration497_ready()
    native_module496()  # Pin the complete canonical source vector before resource admission.
    verify_frozen_kit(KIT_SHA, KIT, docker_alias=True)
    verify_frozen_kit(HELPER_KIT_SHA, HELPER_KIT)
    need(digest(regular(COLLECTOR)) == COLLECTOR_SHA and digest(regular(BOOT)) == BOOT_SHA and
         digest(regular(ACTOR_SOURCE)) == ACTOR_SHA and
         digest(regular(ADMISSION_SOURCE)) == ADMISSION_SHA,
         'fixed collector/boot/QMP/admission source changed')
    for name,path,pin in ((
        'napi_protocol411', R/'ci/capability-audit/number_native496/support/napi_protocol411.py', '03ae5a3a5d5cdc4932e6421bc64c39e06880b701326682bb6dfaf0c4d7c5ec49'),
        ('native_observation411', R/'ci/capability-audit/number_native496/candidate/native_observation411.py', 'e0cc7372d13c71d3d08269d42ea1c71738d9672761ba4cf17a66d47e8c236bb6')):
        need(digest(regular(path)) == pin,'fixed Number411 supplement changed')
        if name in sys.modules: need(Path(sys.modules[name].__file__).resolve() == path,'foreign Number411 supplement')
    sys.path.insert(0,str(R/'ci/capability-audit/number_native496/candidate'))
    sys.path.insert(0,str(R/'ci/capability-audit/number_native496/support'))
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
        self.number580_sends = set()  # only exact signed local HAP/nonce remote pairs from fixed account_window
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
            product = self.observer.product
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
                expected = [HOST_PYTHON, str(ACTOR_SOURCE), '--socket', str(self.guest.qmp_path),
                            '--action', argv[-1]]
                need(argv == expected and argv[-1] in ('query-block', 'reset') and
                     digest(ACTOR_SOURCE) == ACTOR_SHA, 'unknown host constructor')
                actual, _, _ = self.owner.direct(argv, label=label, timeout=timeout, log=log)
            else:
                need(argv[:4] == [self.owner.hdc, '-t', self.guest.target, 'shell'] or
                     argv[:5] == [self.owner.hdc, '-t', self.guest.target, 'file', 'recv'] or
                     argv == [self.owner.hdc, '-t', self.guest.target, 'file', 'send', str(self.observer.binary), self.c.TOKEN_QUERY] or
                     (len(argv) == 7 and argv[:5] == [self.owner.hdc, '-t', self.guest.target, 'file', 'send'] and (argv[5],argv[6]) in self.number580_sends) or
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
        result = self.leaf([HOST_PYTHON, str(ACTOR_SOURCE), '--socket', str(self.guest.qmp_path),
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
        corpus580, _, _, _ = number580_modules()
        self.number580_generation_before = corpus580.capture_generation_before(
            self, self.out / 'number580-generation-before.json', original=native_module496())
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


def account_window(*, bridge, controller, owner_run, owned_number, generation_captures):
    """Original499 Bridge only; public accounts and real per-user caller reads.

    No new Owner/IO/transport. Controller is already normally built/signed DATA;
    no SDK or signer runs here. Every new operation remains in the original
    held table and every cleanup failure stops guest reuse.
    """
    corpus, protocol, registration, project = number580_modules()
    need(type(controller) is dict and set(controller)=={'run','unsigned_hap','signed_hap','signing_receipt','sdk_evidence'},
         'exact normally generated/signed account role DATA')
    run=controller['run'];need(re.fullmatch('[a-f0-9]{32}',run or '') and run!=owner_run,'independent normally compiled account nonce')
    out=bridge.out/'account580';out.mkdir(mode=0o700,exist_ok=False)
    name='org.ohos.qemu.networkwhole579.account';number_bundle=bridge.c.ROLES['system-granted'][0]
    report=dict(schema='number-account580-raw/v1',source_commit=bridge.spec['source_commit'],
        archive_sha256=bridge.spec['archive_sha256'],owner_run=owner_run,number=owned_number,
        hdc=bridge.owner.hdc,target=bridge.guest.target,boot_id=None,controller=dict(controller),
        number_role=bridge.spec['roles']['system-granted'],package_inputs=bridge.spec['native_consumer_inputs496'],
        seeds=corpus.seed_inputs(bridge.spec['number580']['sources'],system_image_sha256=bridge.observer.profile['system_image']['sha256'],protocol=protocol),
        generation_captures=list(generation_captures),steps=[],foreign_case=None,restored_case=None,finally_cleanup=dict(calls=[],failures=[],
            controller_uninstalled=False,foreign_number_uninstalled=False,absence=[]),failures=[],bridge_calls=[])
    at=len(bridge.calls);created=None;controller_installed=False;foreign_installed=False;active=False;serial=0
    root_exception=None;cleanup_exception=None
    def leaf(argv,label,timeout=90):
        value=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,*argv],label,timeout)
        need(value['exit_code']==0 and not bridge.calls[-1]['transport_failure'],'actual account operation failed: '+label)
        return value,bridge.c.record(bridge.out/('call-%04d.json'%(len(bridge.calls)-1)))
    def signed():
        sign=protocol.decode(protocol.checked(controller['signing_receipt']).read_bytes());p=sign['verified_profile']
        permissions=['ohos.permission.MANAGE_LOCAL_ACCOUNTS','ohos.permission.GET_LOCAL_ACCOUNTS',
            'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']
        need(sign['status']=='pass' and sign['scope']=='actual_signature_profile_and_codesign_NOT_guest' and
             sign['unsigned_sha256']==controller['unsigned_hap']['sha256'] and sign['signed_sha256']==controller['signed_hap']['sha256'] and
             p['bundle-info']['bundle-name']==name and p['bundle-info']['apl']=='system_core' and
             p['bundle-info']['app-feature']=='hos_system_app' and p['debug-info']['device-ids']==[bridge.guest.udid] and
             p['acls']['allowed-acls']==permissions and p['permissions']['restricted-permissions']==permissions,
             'real same-UDID account system role signature/permissions')
        for key in ('unsigned_hap','signed_hap','signing_receipt','sdk_evidence'):protocol.checked(controller[key])
    def install(local,bundle,user,label):
        nonlocal controller_installed,foreign_installed
        remote='/data/local/tmp/number580_'+owner_run+'_'+label+'.hap'
        bridge.number580_sends.add((str(protocol.checked(local)),remote))
        _,send=leaf(['file','send',local['path'],remote],'number580-account-send-'+label)
        result,installed=leaf(['shell','bm','install','-p',remote,'-u',str(user)],'number580-account-install-'+label,600)
        need(b'install bundle successfully.' in result['stdout'],'actual per-user install acknowledgement')
        if bundle==name:controller_installed=True
        else:foreign_installed=True
        result,bmsref=leaf(['shell','bm','dump','-n',bundle,'-u',str(user)],'number580-account-bms-'+label)
        bms=bridge.c.bms_fields(result['stdout'],bundle,bridge.spec['roles']['system-granted']['bms']['fields'])
        need(bms['uid']//200000==user and bms['systemApp'] is True,'actual system BMS user/UID')
        result,hashref=leaf(['shell','sha256sum',bms['installedHapPath']],'number580-account-hap-'+label)
        need(result['stdout'].decode().split()==[local['sha256'],bms['installedHapPath']],'actual installed signed HAP bytes')
        return dict(uid=bms['uid'],token=bms['token'],user=user,install=installed,send=send,bms=bmsref,hash=hashref,
                    signed_hap=local,remote=remote,guest_hap=bms['installedHapPath'])
    def absence(bundle,uid,label):
        scanner=protocol.account_scanner(bridge.spec['number580']['sources']['normal_source'],source_commit=bridge.spec['source_commit'])
        series=[]
        for ordinal in range(2):
            nonce=secrets.token_hex(16)
            script=scanner.snapshot_script(nonce,report['boot_id'],mode='uid',uid=uid,bundle=bundle)
            result,ref=leaf(['shell',script],'number580-account-absence-'+label)
            view=scanner.parse_snapshot(result['stdout'].decode(),nonce,report['boot_id'],mode='uid',uid=uid,bundle=bundle)
            need(not any(v['uid']==uid for v in view['processes'].values()),'uninstalled account UID still has processes')
            if bundle==name:need(not view['processes'],'controller process remains after uninstall')
            result,bmsref=leaf(['shell','bm','dump','-a'],'number580-account-absence-bms-'+label)
            result2,amsref=leaf(['shell','aa','dump','-a'],'number580-account-absence-ams-'+label)
            for raw in (result['stdout'],result2['stdout']):
                need(raw.strip() and not re.search(rb'(?<![0-9])'+str(uid).encode()+rb'(?![0-9])',raw),
                     'actual BMS/AMS still contains uninstalled UID or incomplete raw')
                if bundle==name:need(bundle.encode() not in raw,'actual controller BMS/AMS still exists')
            series.append(dict(nonce=nonce,scan=ref,bms=bmsref,ams=amsref))
            if ordinal==0:time.sleep(.25)
        report['finally_cleanup']['absence'].append(dict(bundle=bundle,uid=uid,series=series))
    def action(kind):
        nonlocal serial
        serial+=1;rid='number580_'+str(serial)+'_'+kind.replace('-','_')
        request=dict(run_id=run,request_id=rid,action=kind,payload={})
        argv=['shell','aa','start','-b',name,'-a','EntryAbility','-m','entry','-u','100']
        for key in ('run_id','request_id','action'):argv+=['--ps',key,request[key]]
        argv+=['--ps','payload','{}'];_,start=leaf(argv,'number580-account-'+kind)
        deadline=time.monotonic()+35;directory='/data/app/el2/100/base/'+name+'/files';values=[];journals=[];poll=0
        while time.monotonic()<deadline:
            poll+=1
            found,fref=leaf(['shell','find',directory,'-maxdepth','1','-type','f','-name','apps579-'+run+'-*.jsonl','-print'],
                'number580-account-journals')
            names=found['stdout'].decode().splitlines();values=[];journals=[]
            for n,remote in enumerate(sorted(names)):
                need(re.fullmatch(re.escape(directory+'/apps579-'+run+'-')+'[1-9][0-9]*\\.jsonl',remote),
                     'only the fixed compiled controller nonce journal')
                local=out/('journal-%d-%d-%d.jsonl'%(serial,poll,n));_,received=leaf(['file','recv',remote,str(local)],'number580-account-journal-pull')
                raw=local.read_bytes();need(raw.endswith(b'\n'),'complete account journal')
                rows=[protocol.decode(line) for line in raw.splitlines()]
                need(all(v['run_id']==run and v['role']=='account' and v['bundle']==name and v['uid']==report['controller']['uid']
                     and v['seq']==i for i,v in enumerate(rows)),'actual account journal UID/nonce/sequence')
                values.extend(v for v in rows if v['request_id']==rid)
                journals.append(dict(remote=remote,raw=bridge.c.record(local),receive=received,find=fref))
            if any(v['event'] in ('done','error','request-error','page-error') for v in values):break
            time.sleep(.2)
        step=dict(action=kind,request=request,start=start,journals=journals)
        report['steps'].append(step)
        need(sum(v['event']=='done' for v in values)==1 and not any(v['event'] in ('error','request-error','page-error') for v in values),
             'actual public account action incomplete/failed')
        return values
    try:
        signed();boot,_=leaf(['shell','cat','/proc/sys/kernel/random/boot_id'],'number580-account-current-boot')
        report['boot_id']=boot['stdout'].decode().strip()
        before,before_ref=leaf(['shell','bm','dump','-a'],'number580-account-refuse-existing')
        need(not re.search(rb'(?<![A-Za-z0-9_.])'+name.encode()+rb'(?![A-Za-z0-9_.])',before['stdout']),
             'refuse foreign preexisting account controller')
        report['controller'].update(install(controller['signed_hap'],name,100,'controller'),baseline=before_ref)
        action('accounts');rows=action('account-create')
        created_rows=[protocol.decode(v['value']) for v in rows if v['event']=='account-created'];need(len(created_rows)==1,'one created local account')
        created=created_rows[0];need(type(created['localId']) is int and created['localId']>100 and created['localName']=='whole579_'+run,
             'actual fresh nonce-owned Guest account')
        report['foreign_install']=install(bridge.spec['roles']['system-granted']['signed_hap'],number_bundle,created['localId'],'foreign')
        active=True;action('account-activate');action('accounts')
        report['foreign_case']=corpus.account_case(bridge,user=created['localId'],case_id='account-foreign-read',
            owner_run=owner_run,owned_number=owned_number,output=out/'foreign',protocol=protocol,original=native_module496())
        action('account-restore');active=False;action('accounts')
        report['restored_case']=corpus.account_case(bridge,user=100,case_id='account-restored-read',
            owner_run=owner_run,owned_number=owned_number,output=out/'restored',protocol=protocol,original=native_module496())
    except BaseException as error:
        root_exception=error;report['failures'].append(type(error).__name__+': '+str(error))
    finally:
        try:
            if active:
                action('account-restore');active=False;action('accounts')
            if foreign_installed:
                _,ref=leaf(['shell','bm','uninstall','-n',number_bundle,'-u',str(created['localId'])],'number580-account-uninstall-foreign')
                report['finally_cleanup']['calls'].append(ref)
                absence(number_bundle,report['foreign_install']['uid'],'foreign')
                report['finally_cleanup']['foreign_number_uninstalled']=True
            if created is not None:
                action('account-remove');action('accounts')
            if controller_installed:
                _,ref=leaf(['shell','bm','uninstall','-n',name,'-u','100'],'number580-account-uninstall-controller')
                report['finally_cleanup']['calls'].append(ref)
                absence(name,report['controller']['uid'],'controller')
                report['finally_cleanup']['controller_uninstalled']=True
            # Remove only exact temporary HAPs created by this window.
            for item in (report['controller'].get('remote'),report.get('foreign_install',{}).get('remote')):
                if item:
                    _,ref=leaf(['shell','rm',item],'number580-account-remove-owned-temp')
                    report['finally_cleanup']['calls'].append(ref)
                    _,ref=leaf(['shell','test ! -e '+item+' && test ! -L '+item],'number580-account-owned-temp-absent')
                    report['finally_cleanup']['calls'].append(ref)
        except BaseException as error:
            cleanup_exception=error;report['finally_cleanup']['failures'].append(type(error).__name__+': '+str(error))
        report['bridge_calls']=[bridge.c.record(bridge.out/('call-%04d.json'%i)) for i in range(len(bridge.calls))
                               if bridge.calls[i]['argv'][:3]==[bridge.owner.hdc,'-t',bridge.guest.target]]
        result=write(out/'account.json',report)
    if cleanup_exception is not None:raise cleanup_exception
    if root_exception is not None:raise root_exception
    return result


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


def run(config_path, config_sha256, spec_path, spec_sha256, output, *, observer_proof,
        number580_account_window=None, number580_complete=None):
    """Root invokes once with actual data; no execute code/module in JSON."""
    need(sys.platform == 'darwin' and sys.executable == HOST_PYTHON, 'reviewed literal root Python/Darwin required')
    corpus580, protocol580, registration580, project580 = number580_modules()
    need(callable(number580_account_window) and callable(number580_complete),
         'two fixed Root source account/final replay callables required; never DATA code selectors')
    need(number580_account_window.__name__=='account_window' and
         Path(number580_account_window.__code__.co_filename).resolve()==NUMBER580_DIRECTORY/'owner499.py' and
         number580_complete.__name__=='number580_complete' and
         Path(number580_complete.__code__.co_filename).resolve()==NUMBER580_DIRECTORY/'register580.py',
         'only fixed admitted original499 account and pure complete functions')
    module, collector = source_modules()
    class Collector580(collector.Collector):
        def role_artifacts(self, role):
            item = self.spec['roles'][role]; bundle, system, get, set_ = collector.ROLES[role]
            paths = {k: collector.checked(item[k]) for k in ('unsigned_hap', 'signed_hap', 'signing_receipt', 'sdk_evidence')}
            self.materials.extend(collector.record(p) for p in paths.values())
            sign = collector.decode(paths['signing_receipt'].read_bytes()); profile = sign['verified_profile']
            permissions = [name for name, result in [(collector.GET, get), (collector.SET, set_)] if result == 0]
            need(sign['status'] == 'pass' and sign['scope'] == 'actual_signature_profile_and_codesign_NOT_guest' and
                 sign['role'] == role and sign['signed_sha256'] == item['signed_hap']['sha256'] and
                 sign['unsigned_sha256'] == item['unsigned_hap']['sha256'], 'actual role signed/unsigned receipt mismatch')
            need(profile['bundle-info']['bundle-name'] == bundle and
                 profile['bundle-info']['apl'] == ('system_core' if system else 'normal') and
                 profile['bundle-info']['app-feature'] == ('hos_system_app' if system else 'hos_normal_app') and
                 profile['acls']['allowed-acls'] == permissions and
                 profile['permissions']['restricted-permissions'] == permissions, 'exact role signing/ACL policy mismatch')
            proof = project580.sdk_role_artifacts(item, role, self.spec['source_commit'], original_collector=collector)
            self.materials.extend(proof['materials'])
            self.save(role + '-sdk-source-binding.json', proof)
    config = module.load_config(config_path, config_sha256)  # current profile393, four real MIC/profile fields included
    module.sources(applied=True)
    admission_module = load(ADMISSION_SOURCE, 'fixed_number_admission396')
    profile_path = regular(config['environment']['OHOS_QA_RUNTIME_PROFILE'])
    profile_descriptor = dict(path=str(profile_path), sha256=digest(profile_path), bytes=profile_path.stat().st_size)
    need(profile_descriptor['sha256'] == config['environment']['OHOS_QA_RUNTIME_PROFILE_SHA256'],
         'actual pinned profile changed between config and observer admission')
    # Old396 source remains immutable ancestry, not an admission for new Builder.
    # All new normal source modules are selected by literal code and snapshot.
    need(digest(regular(spec_path)) == spec_sha256, 'actual Number spec changed before native admission')
    early_spec = collector.decode(Path(spec_path).read_bytes())
    normal_source580 = early_spec['number580']['sources']['normal_source']
    product580, context580, elf580 = protocol580.normal_modules(normal_source580, source_commit=SOURCE_COMMIT)
    admitted = protocol580.admit_normal_observer(observer_proof, profile_descriptor=profile_descriptor,
        archive_sha256=config['archive']['sha256'], product=product580,context=context580,elf_reader=elf580,
        normal_source=normal_source580)
    need(digest(regular(spec_path)) == spec_sha256, 'actual Number spec changed')
    spec = collector.decode(Path(spec_path).read_bytes())
    need(spec.get('source_commit') == SOURCE_COMMIT, 'actual Number spec/SDK must bind reviewed new source commit')
    need(re.fullmatch(r'\+861810256[0-9]{4}', spec.get('number') or '') and
         type(spec.get('number580')) is dict and set(spec['number580']) == {'sources','account_controller','observer_owners'},
         'fresh-owned known-prefix mark number and exact local DATA required')
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
        report = None; corpus_result580 = None
        observer_input580 = write(output / 'number580-observer-input.json', observer_proof)
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
            probe = Collector580(spec, dict(shell=bridge.shell, pull=bridge.pull, ui=bridge.ui,
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
            native_index496 = corpus580.collect_original_bridge496(
                bridge=bridge, probe=probe, admitted=admitted,
                package_inputs=spec.get('native_consumer_inputs496'),
                output=bridge.out / 'native-chain496', original=native_module496(), protocol=protocol580)
            report['native_chain496_reviews'] = write(
                bridge.out / 'native-chain496-index.json', native_index496)
            report['native_observations411'] = [v['evidence'] for v in bridge.native_observations]
            report['native_callback_proven'] = False
            write(output/'native-observations411-index.json',dict(observations=report['native_observations411'],
                scope='same held guest raw observations; independent callback proof remains pending'))
            # Seal a separate complete old report before any new raw. Do not
            # rewrite Collector pending/failure, old journal or original496 Ref.
            write(output / 'number580-original-sealed.json', report)
            need(report['cleanup_pending'] is False and not owner.authority.unknown,
                 'unsettled original mutation/authority stops guest reuse')
            corpus_result580 = corpus580.collect(bridge, probe, admitted, original=native_module496(),
                protocol=protocol580, output=output / 'corpus580', account_window=number580_account_window)
        finally:
            finish_and_record(owner, collector, output)
        original_result580 = closed_result(owner, collector, output, report)
        need(corpus_result580 is not None, 'actual independent corpus report absent')
        completed580 = dict(owner_report=original_result580, corpus=corpus_result580,
            owner_closure=collector.record(output / 'resource-close.json'),
            config=dict(path=str(config_path),sha256=config_sha256,bytes=Path(config_path).stat().st_size),
            spec=dict(path=str(spec_path),sha256=spec_sha256,bytes=Path(spec_path).stat().st_size),
            observer_proof=observer_input580)
        # The outer actual command-attempt receipt can only be attached after
        # this process exits; the fixed Root completion callable receives this
        # staged DATA and must preserve that distinction in its pure replay.
        write(output / 'number580-completed-input.json', completed580)
        local580 = number580_complete(completed580, original=native_module496(), admitted=admitted,
                                     protocol=protocol580, registration=registration580, project=project580)
        need(type(local580) is dict and local580.get('schema') == 'number580-local-owner-completion/v1' and
             type(local580.get('exit_code')) is int and local580['exit_code'] in (0,1) and
             local580.get('original_pending_retained') == report['pending'] and
             local580.get('original_failures_retained') == report['failures'] and
             local580.get('whole_id_registered') is False, 'fixed complete raw replay receipt required')
        write(output / 'number580-local-result.json', local580)
        return local580['exit_code']
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
