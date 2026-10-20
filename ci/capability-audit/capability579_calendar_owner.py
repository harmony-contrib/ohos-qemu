"""Calendar second boot on the original Authority, with the real first userdata.

Only the trusted root calls seal_phase1 while its main guest is held, then
run_on_original_owner after canonical suite.run has closed that guest. No new
Owner/Authority/HDC/lease, no parent.vm or children.owner substitution, no raw
process signal, no database/state copy, and no QEMU_EXTRA_ARGS injection.
"""
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import traceback

from run_full_suite_owner376 import Owner as OriginalOwner, LOCK, MARKER, endpoint_closed
from boot_package import QemuGuest
from capability578_owned_io import OwnedIO, reference, require
from capability578_callers import prepare_callers
from capability578_https import OwnedHTTPS
from capability578_stage import read_inputs, UnsettledCapability
from settings_idle579_bindings import load_ref, receipt


def write_new(path, value):
    path = Path(path)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return reference(path)


def document(ref):
    return json.loads(load_ref(ref))


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'canonical original disk path required')
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_uid == os.getuid() and value.st_size > 0,
        'actual owned single-link regular disk required')
    return value


def identity(value):
    return {'device':value.st_dev,'inode':value.st_ino,'bytes':value.st_size,'uid':value.st_uid,'mode':stat.S_IMODE(value.st_mode)}


def stream_ref(path):
    """Actual disk/archive Ref without loading a multi-GiB artifact into RAM."""
    path=Path(path);first=regular(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        require(identity(first)==identity(os.fstat(fd)), 'actual large-file FD/path differs')
        h=hashlib.sha256();offset=0
        while True:
            part=os.pread(fd,1024*1024,offset)
            if not part:break
            h.update(part);offset+=len(part)
        last=regular(path)
        require(identity(last)==identity(first)==identity(os.fstat(fd)) and offset==first.st_size and
            (last.st_mtime_ns,last.st_ctime_ns)==(first.st_mtime_ns,first.st_ctime_ns), 'large artifact changed during SHA read')
        return {'path':str(path),'sha256':h.hexdigest()}
    finally:os.close(fd)


def qmp_blocks(row, io, expected):
    require(row in io.qmp_receipts and row['boot_id'] == io.boot_id and row['execute'] == 'query-block' and
        row['arguments'] == {} and row['completed'] is True, 'actual original query-block operation required')
    requests = [json.loads(line) for line in load_ref(row['request']).splitlines()]
    responses = [json.loads(line) for line in load_ref(row['response']).splitlines()]
    require(requests == [{'execute':'qmp_capabilities','id':'capabilities'}, {'execute':'query-block','id':'request'}] and
        responses and 'QMP' in responses[0], 'original capabilities/query-block wire sequence differs')
    for name in ('capabilities','request'):
        replies = [r for r in responses if r.get('id') == name]
        require(len(replies) == 1 and 'error' not in replies[0] and 'return' in replies[0], 'actual QMP operation failed/ambiguous')
    result = next(r['return'] for r in responses if r.get('id') == 'request')
    require(result == row['reply'] and type(result) is list, 'actual query-block reply differs')
    rows = [r for r in result if type(r.get('inserted')) is dict and r['inserted'].get('file') == str(expected)]
    require(len(rows) == 1 and rows[0]['inserted'].get('ro') is False and rows[0]['inserted'].get('drv') == 'raw',
        'actual raw writable userdata backing must be this fixed original path')
    return rows[0]


def phase_identity(value, io):
    require(value['schema'] == 'calendar579-phase1/v1' and type(value['run']) is str and value['run'] == io.run_id and
        re.fullmatch('[a-f0-9]{32}',value['run']) and value['archive_sha256'] == io.archive_sha256 and
        value['boot_id'] == io.boot_id and type(value['udid']) is str and re.fullmatch('[a-fA-F0-9]{64}',value['udid']) and
        value['udid'].lower() == io.udid.lower() and type(value['account']) is int and value['account'] == 100,
        'actual original Calendar phase1 identity required')


def seal_phase1(io, phase1_ref):
    """Root calls once after real phase1, before closing its original main IO.

    JSON cannot choose a disk. No live disk SHA is claimed: only actual backing
    and inode are captured here; the content SHA is read after original exit.
    """
    parent,guest = io.owner,io.guest
    require(type(parent) is OriginalOwner and parent.vm is guest and parent.children.owner is parent and
        not io._closed and not hasattr(io,'calendar579_phase1_binding'), 'one live original main IO seal required')
    require(not hasattr(io,'calendar579_phase1_ref') or io.calendar579_phase1_ref == phase1_ref, 'another phase1 Ref was already attached')
    parent.held_binding(guest)
    phase_identity(document(phase1_ref),io)
    path = Path(phase1_ref['path'])
    require(path.is_relative_to(io.output) and not path.is_symlink(), 'actual phase1 report must belong to this original IO')
    disk = guest.directory/'images/userdata.img'
    before = regular(disk)
    require('images/userdata.img' in guest.report['initial_package_file_sha256'], 'first boot did not checksum original package userdata')
    sync = io.shell('sync','calendar579_phase1_final_sync')
    actual_sync = receipt(io,sync,'sync')
    require(sync['exit_code'] == 0, 'actual guest sync failed')
    blocks = io.qmp('query-block'); selected = qmp_blocks(blocks,io,disk)
    after = regular(disk)
    require(identity(before) == identity(after), 'phase1 actual userdata inode/size changed')
    parent.held_binding(guest)
    boot = write_new(io.output/'calendar579-first-boot-snapshot.json',guest.report)
    value = {'schema':'calendar579-original-phase1-resource-binding/v1','phase1':dict(phase1_ref),
        'run':io.run_id,'archive_sha256':io.archive_sha256,'boot_id':io.boot_id,'udid':io.udid,'account':100,
        'first_boot':boot,'userdata':{'path':str(disk),**identity(after)},'query_block':blocks,
        'actual_userdata_block':selected,'sync':actual_sync,
        'original_qemu_handle':{'pid':guest.process.pid,'argv':list(guest.process.argv)},
        'scope':'actual live main-guest backing/inode binding; content SHA deferred until original group closure'}
    ref = write_new(io.output/'calendar579-phase1-resource-binding.json',value)
    io.calendar579_phase1_ref = dict(phase1_ref)
    io.calendar579_phase1_binding = ref
    return ref


def rename_exclusive(src_fd, src_name, dst_fd, dst_name):
    """Atomic same-filesystem rename that refuses ANY occupied destination.

    No unsafe os.rename/os.replace fallback, file copy, link, unlink or chmod.
    These fixed platform primitives are called only during root's real scope.
    """
    require(all(type(v) is str and re.fullmatch('[A-Za-z0-9_.-]+',v) for v in (src_name,dst_name)), 'fixed disk slot names required')
    libc = ctypes.CDLL(None,use_errno=True)
    system = platform.system()
    name,flag = ('renameat2',1) if system == 'Linux' else ('renameatx_np',4) if system == 'Darwin' else ('',0)
    require(name and hasattr(libc,name), 'atomic no-replace rename is mandatory; unsupported host must fail untouched')
    function = getattr(libc,name)
    function.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(src_fd,os.fsencode(src_name),dst_fd,os.fsencode(dst_name),flag) != 0:
        number = ctypes.get_errno()
        raise OSError(number,os.strerror(number),src_name+' -> '+dst_name)


class UserdataTransfer:
    """Two fixed disk slots and one owned parking slot, never a disk provider."""
    def __init__(self, scope, main_disk, live_identity):
        self.scope,self.main,self.live_identity = scope,main_disk,live_identity
        self.fresh = self.park = None
        self.directories = {}; self.disk_fds = {}; self.rows = []; self.before = {}
        self.fresh_parked = self.main_moved = False
        self.restored = False

    def directory(self,path):
        require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), 'actual owned disk directory required')
        value = path.stat(); require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid(), 'disk directory owner differs')
        fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.directories[str(path)] = (fd,value.st_dev,value.st_ino)  # track before any later check can fail
        require((os.fstat(fd).st_dev,os.fstat(fd).st_ino) == (value.st_dev,value.st_ino), 'disk directory changed during open')
        return fd

    def dirfd(self,path):
        fd,dev,ino = self.directories[str(path)]
        value = path.lstat(); actual = os.fstat(fd)
        require(stat.S_ISDIR(value.st_mode) and not path.is_symlink() and
            (value.st_dev,value.st_ino) == (actual.st_dev,actual.st_ino) == (dev,ino), 'owned disk directory replaced')
        return fd

    def disk(self,key,path,fd=None):
        first = regular(path)
        if fd is None:
            fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW); self.disk_fds[key] = fd
        require(identity(os.fstat(fd)) == identity(first), 'actual disk FD/path identity differs')
        h = hashlib.sha256(); offset = 0
        while True:
            part = os.pread(fd,1024*1024,offset)
            if not part:break
            offset += len(part);h.update(part)
        last = regular(path)
        require(identity(last) == identity(first) == identity(os.fstat(fd)) and
            (last.st_mtime_ns,last.st_ctime_ns,last.st_size) == (first.st_mtime_ns,first.st_ctime_ns,first.st_size) and offset == first.st_size,
            'closed userdata changed while actual SHA was read')
        return {'path':str(path),**identity(last),'sha256':h.hexdigest()}

    def move(self,source,destination,label):
        self.scope.guard(); self.scope.no_concurrent_guest()
        src = regular(source)
        require(not destination.exists() and not destination.is_symlink(), 'unknown occupied disk slot must be preserved')
        srcfd,dstfd = self.dirfd(source.parent),self.dirfd(destination.parent)
        require(src.st_dev == os.fstat(dstfd).st_dev, 'userdata rename must remain on one actual filesystem')
        row = {'step':label,'source':str(source),'destination':str(destination),'before':identity(src),'state':'pending'}
        self.rows.append(row);self.scope.save()
        rename_exclusive(srcfd,source.name,dstfd,destination.name)
        # Set in-memory disposition immediately, before evidence/fsync can fail.
        if label == 'park_fresh': self.fresh_parked = True
        elif label == 'reuse_main': self.main_moved = True
        elif label == 'restore_main': self.main_moved = False
        elif label == 'restore_fresh': self.fresh_parked = False
        row.update(state='renamed',after=identity(regular(destination)))
        require(row['after'] == row['before'] and not source.exists() and not source.is_symlink(), 'atomic rename changed disk identity')
        self.scope.save();os.fsync(srcfd)
        if srcfd != dstfd:os.fsync(dstfd)

    def activate(self,fresh,initial):
        require(self.fresh is None and not self.before, 'one actual userdata transfer only')
        self.fresh = fresh; self.park = self.scope.output/'disk-slots/fresh-userdata.img'
        self.park.parent.mkdir(mode=0o700,exist_ok=False)
        for path in (self.main.parent,self.fresh.parent,self.park.parent):self.directory(path)
        main = self.disk('main',self.main); fresh_row = self.disk('fresh',self.fresh)
        require({k:main[k] for k in self.live_identity} == self.live_identity and
            main['device'] == fresh_row['device'] and main['inode'] != fresh_row['inode'] and
            fresh_row['sha256'] == initial['images/userdata.img'], 'same original inode and genuinely new checksummed userdata required')
        self.before = {'main_closed':main,'fresh_package':fresh_row};self.scope.save()
        self.move(self.fresh,self.park,'park_fresh')
        self.move(self.main,self.fresh,'reuse_main')
        moved = self.disk('main',self.fresh,self.disk_fds['main'])
        require({k:moved[k] for k in ('device','inode','bytes','sha256')} ==
            {k:main[k] for k in ('device','inode','bytes','sha256')}, 'actual launched userdata differs from closed first-boot disk')
        return moved

    def restore(self):
        if self.restored:return
        self.scope.no_concurrent_guest()
        # Unknown replacements are never overwritten, even during cleanup.
        if self.main_moved:
            actual = self.disk('main',self.fresh,self.disk_fds['main'])
            require(identity(regular(self.fresh)) == {k:self.before['main_closed'][k] for k in self.live_identity}, 'second boot replaced the original userdata inode')
            self.scope.report['userdata_after_second_close'] = actual
            self.move(self.fresh,self.main,'restore_main')
        if self.fresh_parked:
            actual = self.disk('fresh',self.park,self.disk_fds['fresh'])
            require({k:actual[k] for k in ('device','inode','bytes','sha256')} ==
                {k:self.before['fresh_package'][k] for k in ('device','inode','bytes','sha256')}, 'parked untouched fresh image changed')
            self.move(self.park,self.fresh,'restore_fresh')
        if self.before:
            self.scope.report['restored_disk_slots'] = {
                'main':self.disk('main',self.main,self.disk_fds['main']),
                'fresh':self.disk('fresh',self.fresh,self.disk_fds['fresh'])}
        for fd in self.disk_fds.values():os.close(fd)
        self.disk_fds.clear()
        for fd,_,_ in self.directories.values():os.close(fd)
        self.directories.clear();self.restored = True;self.scope.save()


class CalendarGuestScope:
    """One finite same-archive reboot context on the original retained Authority."""
    def __init__(self,parent,output,proof,report,save):
        self.parent,self.output,self.proof,self.report,self.save = parent,output,proof,report,save
        for name in ('archive','config','children','authority','server','lease_fd','private_tmp','hdc','port','guest_port'):
            setattr(self,name,getattr(parent,name))
        self.original_vm = parent.vm;self.original_children_owner = parent.children.owner
        self.env = dict(parent.env);self.vm = None;self._closed = False;self.override = False;self.policy = {}
        self.launch_records = [];self.closed_records = [];self.socket_identity = None;self.socket_fd = None
        self.qmp_node = None;self.quiet_census = []
        self.transfer = UserdataTransfer(self,self.original_vm.directory/'images/userdata.img',proof['live_disk_identity'])

    def guard(self):
        parent=self.parent;held=os.fstat(self.lease_fd);named=LOCK.stat()
        require(parent.vm is self.original_vm and parent.children.owner is self.original_children_owner is parent and
            parent.authority is self.authority and parent.server is self.server and parent.config is self.config,
            'Calendar scope cannot replace original VM/Owner/Authority/config')
        require(parent.lease_fd == self.lease_fd and not LOCK.is_symlink() and held.st_nlink == named.st_nlink == 1 and
            held.st_uid == os.getuid() and (held.st_dev,held.st_ino) == (named.st_dev,named.st_ino) == tuple(self.proof['lease_identity']),
            'original open lease/named inode changed')
        value=MARKER.stat()
        require(not MARKER.is_symlink() and value.st_nlink == 1 and value.st_uid == os.getuid() and stat.S_IMODE(value.st_mode) == 0o600 and
            (value.st_dev,value.st_ino) == tuple(self.proof['marker_identity']) and reference(MARKER) == self.proof['marker'], 'original marker changed')
        require(parent.env == self.env == self.proof['environment'] and parent.private_tmp == self.private_tmp and
            self.private_tmp.resolve() == self.private_tmp and not self.private_tmp.is_symlink() and
            (self.private_tmp.stat().st_dev,self.private_tmp.stat().st_ino) == tuple(self.proof['private_tmp_identity']) and
            stat.S_IMODE(self.private_tmp.stat().st_mode) == 0o700, 'original HDC environment/private directory changed')
        require(not self.env.get('QEMU_EXTRA_ARGS') and self.env.get('QEMU_PEER_MODE','off') == 'off',
            'Calendar reboot does not admit QEMU argument injection or a peer network')
        require(not self.authority.unknown and self.server in self.authority.handles and not self.server.reaped,
            'unknown constructor or lost original HDC handle')
        self.server.assert_held();require(self.server.poll() is None, 'original foreground HDC exited')
        lock=Path(self.proof['hdc_lock']['path'])
        require(reference(lock) == self.proof['hdc_lock'] and lock.read_text().strip() == str(self.server.pid), 'original HDC singleton changed')
        value=self.archive.stat()
        require(parent.archive is self.archive and not self.archive.is_symlink() and
            [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns] == self.proof['archive_stat'], 'actual source archive replaced')

    def no_concurrent_guest(self):
        self.guard()
        # Only this new QEMU may be live after launch; every other direct and
        # nested original group must have completed original final closure.
        allowed = {self.server}
        if self.vm is not None and self.vm.process is not None and not self.vm.process.reaped:
            # Disk mutation is forbidden until this new actual handle is reaped.
            raise ValueError('cannot move userdata while second QEMU handle is still held')
        require(all(child in allowed or child.reaped for child in self.authority.handles), 'another original group is unsettled')
        # Read-only actual original Authority census also refuses a foreign
        # live QEMU. No process name is ever used as signal authority.
        index=len(self.authority.handles);rows=self.authority.census()
        others=[row for row in rows if not row['stat'].startswith('Z') and
            re.match(r'^(?:[^ \t]*/)?qemu-system-[A-Za-z0-9_-]+(?:[ \t]|$)',row['command'])]
        actual=self.authority.handles[index]
        self.quiet_census.append({'pid':actual.pid,'argv':list(actual.argv),'reaped':actual.reaped,
            'stdout':reference(self.parent.output/('leaf-%04d.stdout'%index)),
            'stderr':reference(self.parent.output/('leaf-%04d.stderr'%index)),'other_QEMU_rows':others})
        self.save();require(not others,'another actual QEMU prevents userdata transfer; leave its files/process untouched')

    def capture_socket_directory(self):
        guest=self.vm
        if guest is None or guest.socket_directory is None or self.socket_fd is not None:return
        path=guest.socket_directory.resolve();value=path.lstat()
        require(path.parent==Path('/tmp').resolve() and path.name.startswith('oq-b-') and not path.is_symlink() and
            stat.S_ISDIR(value.st_mode) and stat.S_IMODE(value.st_mode)==0o700 and value.st_uid==os.getuid(),
            'normal QemuGuest must own its private QMP directory')
        self.socket_fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.socket_identity={'path':str(path),'device':value.st_dev,'inode':value.st_ino}
        require((os.fstat(self.socket_fd).st_dev,os.fstat(self.socket_fd).st_ino)==(value.st_dev,value.st_ino),
            'QMP directory replaced during open')
        self.save()

    def close_socket_directory(self):
        if self.socket_fd is None:return
        self.no_concurrent_guest()
        path=Path(self.socket_identity['path']);value=path.lstat();held=os.fstat(self.socket_fd)
        require((value.st_dev,value.st_ino)==(held.st_dev,held.st_ino)==
            (self.socket_identity['device'],self.socket_identity['inode']) and not path.is_symlink(), 'private QMP directory changed')
        entries=os.listdir(self.socket_fd)
        require(set(entries)<= {'qmp.sock'}, 'unknown QMP directory entry preserved')
        if entries:
            node=os.stat('qmp.sock',dir_fd=self.socket_fd,follow_symlinks=False)
            require(stat.S_ISSOCK(node.st_mode) and node.st_uid==os.getuid() and node.st_nlink==1, 'unknown non-socket QMP path preserved')
            current={'device':node.st_dev,'inode':node.st_ino}
            require(self.qmp_node is None or self.qmp_node==current, 'known QMP socket replaced')
            self.qmp_node=current
            os.unlink('qmp.sock',dir_fd=self.socket_fd)
        os.close(self.socket_fd);self.socket_fd=None
        require((path.lstat().st_dev,path.lstat().st_ino)==(value.st_dev,value.st_ino) and not list(path.iterdir()), 'private QMP directory changed before removal')
        os.rmdir(path);self.report['private_qmp_cleanup']={'directory':self.socket_identity,'socket':self.qmp_node,'removed':True}
        self.save()

    def direct(self,argv,*,label,timeout,log,env=None,cwd=None):
        self.guard()
        return self.parent.direct(argv,label=label,timeout=timeout,log=log,env=self.env if env is None else env,cwd=cwd)

    def guest_command(self,guest,argv,*,label,timeout,log):
        self.guard();return OriginalOwner.guest_command(self,guest,argv,label=label,timeout=timeout,log=log)

    def held_binding(self,guest):
        self.guard();OriginalOwner.held_binding(self,guest)

    def configure(self):
        self.guard();self.no_concurrent_guest()
        args=copy.copy(self.original_vm.args)
        args.archive=self.archive;args.output=self.output/'boot';args.hdc=self.hdc;args.hdc_port=self.guest_port
        args.purpose='acceptance';args.hold=False;args.kernel_diagnostic=None;args.power_diagnostic_wakeup=False
        require(args.resolution == '1280x800' and not getattr(args,'candidate_kernel',None), 'unchanged real acceptance launch required')
        self.vm=QemuGuest(args,owned_command=self.guest_command,owned_launcher=self.launcher)
        self.vm.close=self.close  # start failure also uses original Authority closure and disk restoration

    def launcher(self,guest,argv,**kwargs):
        self.guard();self.no_concurrent_guest()
        require(guest is self.vm and not self.launch_records and guest.arch == 'arm64' and guest.device == 'phone' and
            kwargs.get('env') == dict(self.env,LC_ALL='C',LANG='C') and guest.report['archive_sha256'] == self.proof['archive']['sha256'],
            'one exact same-archive launch with original environment required')
        self.capture_socket_directory()
        require(stream_ref(self.archive) == self.proof['archive'], 'archive bytes changed before fresh extraction launch')
        initial=guest.report['initial_package_file_sha256']; images=guest.directory/'images'
        fresh=[]
        for path in sorted(images.iterdir()):
            if path.is_file():
                row=regular(path); actual=stream_ref(path); rel=path.relative_to(guest.directory).as_posix()
                require(initial.get(rel) == actual['sha256'], 'normal fresh package image checksum failed before userdata override')
                fresh.append({'relative':rel,**actual,**identity(row)})
        require(fresh and any(r['relative']=='images/userdata.img' for r in fresh), 'actual checksummed package userdata missing')
        moved=self.transfer.activate(images/'userdata.img',initial)
        row={'argv':list(argv),'environment':dict(kwargs['env']),'cwd':str(kwargs['cwd']),
            'fresh_package_images':fresh,'launched_userdata':moved,'state':'handle_pending'}
        self.launch_records.append(row);self.save()
        guest.report.update(scope='same_archive_calendar579_reboot_reused_userdata_NOT_fresh_userdata_or_full_gate',
            calendar579_userdata_reuse={'fresh_extraction_checksum_vector':dict(initial),'actual_launched_userdata':moved})
        guest.save()
        # The original launcher verifies the entire original argv, cwd, stdio,
        # environment and archive, then constructs only through its Authority.
        child=OriginalOwner.launcher(self,guest,argv,**kwargs)
        row.update(state='actual_handle_retained',pid=child.pid,pgid=os.getpgid(child.pid),sid=os.getsid(child.pid));self.save()
        return child

    def start(self):
        self.guard();require(self.vm is not None and not self._closed, 'configured Calendar scope required')
        self.vm.start();self.held_binding(self.vm)
        require(self.vm.report['test_environment']['boot_id'] != self.proof['first_boot_id'] and
            self.vm.udid.lower() == self.proof['first_udid'].lower(), 'actual reboot must change kernel boot ID and retain device identity')
        from run_packaged_qemu_suite import power_timeout
        self.vm.wake_for_interaction('calendar579_second_boot_business_setup')
        self.policy['before']=power_timeout(self.vm.shell('hidumper -s 3301 -a "-a"','calendar579_power_before'))
        require(self.policy['before']['override_ms'] is None, 'another PowerMgr override must not be overwritten')
        self.override=True;self.save()
        actual=self.vm.shell('power-shell timeout -o 86400000','calendar579_finite_business_timeout')
        require(actual.strip() == 'Override screen off time to 86400000', 'actual finite PowerMgr setup failed')
        self.policy['setup']=power_timeout(self.vm.shell('hidumper -s 3301 -a "-a"','calendar579_power_setup'))
        require(self.policy['setup'] == dict(self.policy['before'],override_ms=86400000), 'actual PowerMgr override/backup differs')
        self.save()

    def close(self):
        if self._closed:return
        self.guard();errors=[];guest=self.vm
        if guest is not None:
            try:
                self.capture_socket_directory()
                if self.socket_fd is not None and 'qmp.sock' in os.listdir(self.socket_fd):
                    node=os.stat('qmp.sock',dir_fd=self.socket_fd,follow_symlinks=False)
                    require(stat.S_ISSOCK(node.st_mode) and node.st_uid==os.getuid() and node.st_nlink==1,'unknown QMP socket entry preserved')
                    current={'device':node.st_dev,'inode':node.st_ino}
                    require(self.qmp_node is None or self.qmp_node==current,'actual QMP socket replaced')
                    self.qmp_node=current
            except BaseException as error:errors.append('QMP identity: '+repr(error))
            if self.override and guest.process is not None and not guest.process.reaped and guest.process.poll() is None:
                try:
                    from run_packaged_qemu_suite import power_timeout,verify_restoration
                    guest.wake_for_interaction('calendar579_restore_timeout')
                    actual=guest.shell('power-shell timeout -r','calendar579_restore_timeout')
                    restored=power_timeout(guest.shell('hidumper -s 3301 -a "-a"','calendar579_power_restored'))
                    self.policy.update(restored=restored,restoration_method=verify_restoration(actual,self.policy['before'],self.policy.get('setup'),restored))
                    self.override=False
                except BaseException as error:errors.append('PowerMgr: '+repr(error))
            if guest.clock_observer is not None:
                try:guest.clock_observer.cleanup();guest.save()
                except BaseException as error:errors.append('original clock observer: '+repr(error))
            if guest.diagnostic_process is not None:errors.append('unexpected acceptance diagnostic process')
            if guest.process is not None and not guest.process.reaped:
                try:
                    require(guest.process in self.authority.handles, 'actual second QEMU handle missing')
                    self.authority.close_group(guest.process)
                except BaseException as error:errors.append('original QEMU group: '+repr(error))
            if guest.qemu_log is not None:
                try:guest.qemu_log.close()
                except BaseException as error:errors.append('QEMU log: '+repr(error))
        try:
            # Settle any already-exited finite command leaves before the disk
            # no-concurrency guard. Never stop a live unrelated child here.
            settle_exited(self.parent,self.server)
            self.transfer.restore()
        except BaseException as error:errors.append('userdata restoration: '+repr(error))
        try:self.close_socket_directory()
        except BaseException as error:errors.append('QMP directory cleanup: '+repr(error))
        try:
            require(endpoint_closed(self.guest_port), 'second guest HDC forward remains listening')
            if self.proof['vnc_port'] is not None:require(endpoint_closed(self.proof['vnc_port']), 'same original VNC endpoint remains listening')
        except BaseException as error:errors.append('ports: '+repr(error))
        self.closed_records.append({'errors':errors,'qemu':None if guest is None or guest.process is None else
            {'pid':guest.process.pid,'reaped':guest.process.reaped,'returncode':guest.process.returncode},
            'power_policy':dict(self.policy),'userdata_restored':self.transfer.restored})
        self._closed=not errors;self.save()
        require(not errors, 'Calendar original resource cleanup unsettled: '+repr(errors))


def settle_exited(parent,server):
    require(not parent.authority.unknown, 'unknown constructor retains the original lease')
    for child in list(parent.authority.handles):
        if child is server or child.reaped:continue
        require(child.poll() is not None, 'unrelated live original group prevents Calendar reboot/move')
        parent.authority.close_group(child)
    require(all(child is server or child.reaped for child in parent.authority.handles), 'all original non-HDC groups must be fully reaped')


def original_vnc_port(guest):
    text=guest.report['test_environment']['qemu_command']
    matches=re.findall(r'(?:^|\s)-vnc\s+(?:127\.0\.0\.1:|:)([0-9]+)(?=\s|$)',text)
    require(len(matches) <= 1 and ('-vnc' not in text or len(matches)==1), 'unknown original actual VNC command')
    if not matches:return None
    value=5900+int(matches[0]);require(5900 <= value <= 65535, 'original actual VNC port out of range')
    return value


def run_on_original_owner(owner,resources,inputs_ref,*,phase1_ref,phase2):
    """After real canonical main exit; before the original unchanged finish."""
    require(type(owner) is OriginalOwner and type(resources) is list and callable(phase2) and owner.children.owner is owner,
        'one original Owner/table and fixed root Calendar phase2 callable required')
    old=owner.vm
    require(old is not None and old.process in owner.authority.handles and
        (old.process.reaped or old.process.poll() is not None), 'canonical main guest must actually exit first')
    require(all(getattr(r,'_closed',False) is True for r in resources), 'all prior actual IO/scopes must settle before reboot')
    matching=[r for r in resources if type(r) is OwnedIO and r.owner is owner and r.guest is old and
        getattr(r,'calendar579_phase1_ref',None) == phase1_ref]
    require(len(matching)==1, 'unique actual sealed main-guest phase1 IO required')
    first=matching[0];phase=document(phase1_ref);phase_identity(phase,first)
    binding=document(first.calendar579_phase1_binding)
    require(binding['phase1'] == phase1_ref and binding['boot_id'] == old.report['test_environment']['boot_id'] == phase['boot_id'] and
        binding['udid'].lower() == old.udid.lower() == phase['udid'].lower() and
        binding['original_qemu_handle'] == {'pid':old.process.pid,'argv':list(old.process.argv)}, 'phase1 belongs to another original boot/handle')
    disk=old.directory/'images/userdata.img'
    require(binding['userdata']['path'] == str(disk) and identity(regular(disk)) ==
        {k:binding['userdata'][k] for k in ('device','inode','bytes','uid','mode')}, 'closed main disk is not the actual phase1 inode')
    qmp_blocks(binding['query_block'],first,disk)
    inputs=read_inputs(inputs_ref,owner)
    lease=os.fstat(owner.lease_fd);named=LOCK.stat();active=document(reference(MARKER))
    require(not LOCK.is_symlink() and (lease.st_dev,lease.st_ino)==(named.st_dev,named.st_ino) and
        active['pid']==os.getpid() and Path(active['case_root'])==owner.output and
        active['lease_device']==lease.st_dev and active['lease_inode']==lease.st_ino, 'actual original lease marker required')
    locks=list(owner.private_tmp.glob('.*.pid'));require(len(locks)==1, 'one original foreground HDC singleton required')
    archive=owner.archive.stat()
    proof={'archive':stream_ref(owner.archive),'archive_stat':[archive.st_dev,archive.st_ino,archive.st_size,archive.st_mtime_ns],
        'lease_identity':[lease.st_dev,lease.st_ino],'marker':reference(MARKER),'marker_identity':[MARKER.stat().st_dev,MARKER.stat().st_ino],
        'private_tmp_identity':[owner.private_tmp.stat().st_dev,owner.private_tmp.stat().st_ino],'hdc_lock':reference(locks[0]),
        'environment':dict(owner.env),'live_disk_identity':{k:binding['userdata'][k] for k in ('device','inode','bytes','uid','mode')},
        'first_boot_id':phase['boot_id'],'first_udid':phase['udid'],'vnc_port':original_vnc_port(old)}
    root=owner.output/('calendar579-reboot-'+secrets.token_hex(8));root.mkdir(mode=0o700,exist_ok=False)
    report={'schema':'actual-original-owner-calendar579-reboot/v1','archive':proof['archive'],'inputs':inputs_ref,
        'phase1':phase1_ref,'phase1_resource_binding':first.calendar579_phase1_binding,'original_binding':proof,
        'scope':'second actual same-archive boot reuses first guest userdata inode; original Authority/lease/HDC only',
        'failures':[],'cleanup_complete':False,'resource_transition_observed':False,'runtime_pass':False,
        'first_artifact_behavior_gate_passed':False,'closed_requirement_ids':[]}
    scope=None;io=None
    def save():
        if scope is not None:
            report.update(launch=scope.launch_records,disk_moves=scope.transfer.rows,closed=scope.closed_records,
                disk_before=scope.transfer.before,scope_closed=scope._closed,actual_quiet_census=scope.quiet_census)
        target=root/'evidence.json';temporary=root/('evidence-'+secrets.token_hex(8)+'.tmp')
        with temporary.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)  # report only, never an image/disk slot
    scope=CalendarGuestScope(owner,root,proof,report,save);resources.append(scope)
    start=len(resources)-1;save()
    try:
        scope.guard()
        # Finalize only groups already proved exited. No live process is
        # stopped to make the precondition look satisfied.
        settle_exited(owner,owner.server)
        require(not getattr(owner.children,'docker',None) or all(op['closed'] for op in owner.children.docker.operations),
            'prior Docker transaction is still unsettled')
        require(all(row.get('settled') is True for row in owner.children.handles.values()), 'prior nested constructor command not settled')
        report['original_group_closure']=write_new(root/'original-group-closure.json',{
            'actual_main_handle':{'pid':old.process.pid,'argv':list(old.process.argv),'returncode':old.process.returncode,
                'reaped':old.process.reaped,'last_signal_boundary':old.process.last_signal_boundary},
            'authority':document(reference(owner.output/'held-processes.json')),
            'actual_group_census_raw':[{'pid':p.pid,'argv':list(p.argv),'reaped':p.reaped,'returncode':p.returncode,
                'stdout':reference(owner.output/('leaf-%04d.stdout'%i)),
                'stderr':reference(owner.output/('leaf-%04d.stderr'%i))}
                for i,p in enumerate(owner.authority.handles) if p.label=='owner-group-census'],
            'all_prior_non_HDC_handles_reaped':all(p is owner.server or p.reaped for p in owner.authority.handles)})
        require(old.process.reaped and old.process.last_signal_boundary, 'original main group lacks final actual Authority closure')
        require(endpoint_closed(owner.guest_port) and (proof['vnc_port'] is None or endpoint_closed(proof['vnc_port'])), 'original guest endpoint still listening')
        report['first_closed_boot']=write_new(root/'first-closed-boot.json',old.report)
        scope.configure();scope.start()
        io=OwnedIO(scope,scope.vm,root/'business-io',run_id=phase['run'],package_inputs={},prepare_callers=prepare_callers,https_factory=OwnedHTTPS)
        resources.append(io)  # before ANY new business command/QMP/caller action
        block=io.qmp('query-block');actual=qmp_blocks(block,io,scope.vm.directory/'images/userdata.img')
        current=identity(regular(scope.vm.directory/'images/userdata.img'))
        require(current == proof['live_disk_identity'], 'actual second boot no longer uses first userdata inode')
        boot=write_new(root/'second-boot-before-business.json',scope.vm.report)
        transfer=write_new(root/'disk-transfer-before-business.json',{
            'schema':'calendar579-actual-disk-transfer/v1','first_boot':binding['first_boot'],'first_closed_boot':report['first_closed_boot'],
            'original_group_closure':report['original_group_closure'],'before':scope.transfer.before,'atomic_moves':copy.deepcopy(scope.transfer.rows),
            'launched_userdata':scope.launch_records[0]['launched_userdata'],'actual_userdata_block':actual,'query_block':block,
            'second_boot':boot,'boot_id':io.boot_id,'udid':io.udid,'same_original_inode':current,
            'note':'fresh package checksums precede the explicit userdata override; no DB or fixture bytes were copied'})
        io.package_inputs={'calendar579':{'phase1':phase1_ref,'first_boot':binding['first_boot'],'disk_transfer':transfer},
            'native_helpers':inputs['native_helpers'],'native_addons':inputs['native_addons'],'providers':inputs['providers']}
        io.environment['permission_allow_text']=inputs['permission_allow_text']
        result=phase2(io,phase1_ref)
        require(type(result) is dict and set(result)=={'path','sha256'} and Path(result['path']).is_relative_to(io.output), 'actual phase2 report Ref required')
        load_ref(result);report['phase2']=result;report['resource_transition_observed']=True
        read_inputs(inputs_ref,owner)
    except Exception as error:
        report['failures'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
    finally:
        errors=[]
        for resource in reversed(resources[start:]):
            if not resource._closed:
                try:resource.close()
                except BaseException as error:errors.append({'resource':str(resource.output),'type':type(error).__name__,'message':str(error)})
        report['cleanup_errors']=errors;report['cleanup_complete']=not errors and all(r._closed for r in resources[start:])
        if owner.vm is not old or owner.children.owner is not owner:
            errors.append({'resource':'original parent identity','type':'ownership_mismatch','message':'parent VM/children Owner changed'})
            report['cleanup_complete']=False
        report['status']='resource_transition_observed_NOT_business_acceptance' if report['resource_transition_observed'] and report['cleanup_complete'] and not report['failures'] else 'fail'
        save()
        if not report['cleanup_complete']:raise UnsettledCapability('Calendar original resources/disk slots unsettled: '+repr(errors))
    # Safe semantic/callback failures are returned for the root's source-defined
    # after_suite combiner to collect alongside paired failures. This helper
    # never rewrites canonical suite status or its earlier closure decision.
    return {'report':reference(root/'evidence.json'),'phase2':report.get('phase2'),'cleanup_complete':True,
        'status':report['status'],'failures':report['failures'],'resource_transition_observed':report['resource_transition_observed'],
        'runtime_pass':False,'first_artifact_behavior_gate_passed':False,'closed_requirement_ids':[]}
