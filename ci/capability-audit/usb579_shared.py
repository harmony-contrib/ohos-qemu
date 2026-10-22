"""Real same-guest USB/MIDI/MTP work on two original already-held stage IOs.

Only Root constructs/closes the original IOs and Owner. The permanent unbound
qemu_shared gadget/mounts belong to normal product init. This code temporarily
owns its links/UDC/serial, two ordinary callers and independent real C peers.
"""
from pathlib import Path
import hashlib
import json
import re
import secrets
import shlex
import time
from usb579_contract import guard, need, doc, checked, ref, loads, dependency, GADGET, BULK_MOUNT, MTP_MOUNT
from usb579_project import ROLES, bundle

CASE = 'shared-device'


class SharedDevice:
    def __init__(self, io, audio_io):
        context = guard(io); guard(audio_io)
        need(io is not audio_io and io.owner is audio_io.owner and io.guest is audio_io.guest and
             io.archive_sha256 == audio_io.archive_sha256 and io.boot_id == audio_io.boot_id,
             'two original IOs on exactly one original held guest/package')
        self.io, self.audio_io = io, audio_io
        self.report = dict(schema='usb579-real-shared-device/v1', source_commit=context['source_commit'],
            run=io.run_id, audio_run=audio_io.run_id, archive_sha256=io.archive_sha256, boot_id=io.boot_id, hdc=io.hdc, target=io.target,
            observations=[], requests=[], peers=[], identities={}, kernel_edges=[], midi=[], files=[],
            failures=[], cleanup_errors=[], cleanup=None, runtime_pass=False, closed_ids=[],
            first_artifact_behavior_gate_passed=False)
        self.path = io.output / 'usb579-shared-device.json'
        self.remote = '/data/local/tmp/usb579-' + io.run_id
        self.installed = []; self.active = []; self.links = []; self.bound = False
        self.prepared = None; self.udc = None; self.baseline = None; self.finished = False
        self.card_id = 'UH579' + io.run_id[:8]
        io.register_cleanup(self.cleanup)  # Original IO/Owner retains every cleanup intent.
        self.persist()

    def persist(self):
        self.path.write_text(json.dumps(self.report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

    def shell(self, script, label, *, failure=False, io=None):
        transport = io or self.io
        row = transport.shell(script, 'usb579_' + label, allow_failure=failure)
        self.report['observations'].append(dict(label=label, script=script, io=str(transport.output),
            receipt=transport.ref_receipt(row)))
        self.persist(); return row['stdout']

    def poll(self, callback, label, seconds=30):
        deadline = time.monotonic() + seconds
        while True:
            result = callback()
            if result: return result
            need(time.monotonic() < deadline, 'actual device transition absent: ' + label)
            time.sleep(.2)

    def snapshot(self, label):
        # Only fixed existing product paths. Include HDC/g1 and current shell
        # security identity; root UID alone does not establish mount authority.
        script = '''set -e
id
cat /proc/self/attr/current
cat /proc/sys/kernel/random/boot_id
param get sys.usb.config
param get sys.usb.controller
param get persist.edm.mtp_server_disable
for f in /config/usb_gadget/g1/UDC /config/usb_gadget/g1/idVendor /config/usb_gadget/g1/idProduct; do printf '%s=' "$f"; cat "$f"; done
for f in /config/usb_gadget/g1/configs/*/*; do if test -L "$f"; then printf '%s=' "$f"; readlink "$f"; fi; done
'''
        return self.shell(script, label)

    def begin(self):
        self.baseline = self.snapshot('unrelated_gadget_baseline')
        self.report['baseline'] = self.baseline
        self.report['shell_security_context'] = self.shell('cat /proc/self/attr/current', 'actual_shell_security_context').strip('\x00\r\n ')
        need(self.report['shell_security_context'] == 'u:r:sh:s0', 'actual HDC shell must match the existing developer_only hdcd-to-sh source transition')
        text = self.shell('''set -e
G=/config/usb_gadget/qemu_shared
test -d "$G" && test ! -L "$G"
test "$(cat "$G/UDC")" = ''
test "$(cat "$G/strings/0x409/serialnumber")" = QEMU_SHARED_UNBOUND
for f in "$G"/configs/c.1/*; do test ! -L "$f"; done
for f in ffs.usb579 ffs.mtp midi.usb579; do test -d "$G/functions/$f"; done
awk '$3 == "functionfs" && ($2 == "/dev/usb-ffs/usb579" || $2 == "/dev/usb-ffs/mtp") {print $0}' /proc/mounts
for d in /sys/class/udc/dummy_udc.*; do
 test -e "$d" || continue
 driver=$(readlink -f "$d/device/driver")
 test "${driver##*/}" = dummy_udc || continue
 used=0
 for g in /config/usb_gadget/*/UDC; do test "$(cat "$g")" != "${d##*/}" || used=1; done
 if test "$used" = 0; then printf 'FREE_DUMMY_UDC=%s\n' "${d##*/}"; fi
done
''', 'normal_product_unbound_device')
        available = re.findall(r'^FREE_DUMMY_UDC=(dummy_udc\.[0-9]+)$', text, re.M)
        need(len(available) == 1 and text.count(' functionfs ') == 2, 'normal init mounts and one actually free dummy UDC')
        self.udc = available[0]; self.report['udc'] = self.udc
        self.shell('printf %s ' + self.io.run_id + ' > ' + GADGET + '/strings/0x409/serialnumber && printf %s ' +
            self.card_id + ' > ' + GADGET + '/functions/midi.usb579/id', 'owned_nonce_identity')
        self.report['kernel_product'] = self.shell('zcat /proc/config.gz', 'actual_running_kernel_config')
        flags = dict(re.findall(r'^(CONFIG_[A-Z0-9_]+)=(\S+)$', self.report['kernel_product'], re.M))
        for name in ('USB', 'USB_GADGET', 'USB_DUMMY_HCD', 'USB_LIBCOMPOSITE', 'USB_CONFIGFS',
                     'USB_CONFIGFS_F_FS', 'USB_CONFIGFS_F_MIDI', 'SND_USB_AUDIO', 'SND_RAWMIDI', 'CONFIGFS_FS'):
            need(flags.get('CONFIG_' + name) == 'y', 'actual boot must contain ordinary built-in ' + name)
        inputs = self.io.package_inputs['usb579']
        product = doc(inputs['product_export']); self.report['product_export'] = inputs['product_export']
        need(product['source_commit'] == self.report['source_commit'] and product['archive']['sha256'] == self.io.archive_sha256,
             'same newly packaged actual USB product')
        need(hashlib.sha256(self.report['kernel_product'].encode()).hexdigest() == product['kernel']['config']['sha256'],
             'actual running full kernel config must match normal packaged build')
        init = self.shell('sha256sum /vendor/etc/init.virt.usb.cfg', 'actual_installed_init')
        need(init.split() == [product['init']['image_file']['sha256'], '/vendor/etc/init.virt.usb.cfg'], 'actual normal installed gadget init bytes')
        ui = product['permission_ui']; provider_bms = self.shell('bm dump -n com.usb.right', 'actual_right_provider_BMS')
        provider = dependency('hap_identity_binding').bms_application_identity(provider_bms, 'com.usb.right')
        parsed = loads(provider_bms[provider_bms.index('{'):])
        paths = {row['hapPath'] for row in parsed['hapModuleInfos'] if row.get('hapPath')}
        need(len(paths) == 1 and parsed['applicationInfo']['isSystemApp'] is True, 'normal installed USB grant dialog provider')
        path = paths.pop(); need(self.shell('sha256sum ' + shlex.quote(path), 'actual_right_provider_HAP').split() ==
             [ui['provider_hap']['sha256'], path], 'actual user decision goes to the real product USB provider')
        self.report['permission_provider'] = dict(bms=provider_bms, identity=provider, hap=ui['provider_hap'])
        helper = inputs['native_peer']
        from usb579_native import prepared_input
        verified = prepared_input(helper['build'], archive={'sha256':self.io.archive_sha256}, product=self.io.guest.report['test_environment']['product'])
        need(verified == helper, 'exact explicit selected actual normal helper descriptor')
        self.report['native_peer'] = helper
        self.shell('test ! -e ' + self.remote + ' && mkdir -m 0700 ' + self.remote, 'peer_directory')
        self.io.send(checked(helper['binary']), self.remote + '/usb579_device_peer', 'usb579_native_peer')
        actual = self.shell('chmod 0700 ' + self.remote + '/usb579_device_peer && sha256sum ' + self.remote + '/usb579_device_peer', 'actual_peer_binary')
        need(actual.split() == [helper['binary']['sha256'], self.remote + '/usb579_device_peer'], 'actual peer ELF bytes')
        self.prepared = self.io.prepare_callers('usb579', CASE, self.io.run_id, ROLES, {})
        self.report['prepared'] = self.prepared; self.persist()
        for role in ROLES:
            self.installed.append(role)
            result = self.io.command([self.io.hdc, '-t', self.io.target, 'install', self.prepared['callers'][role]['signed']['path']], 'usb579_install_' + role)
            need('success' in result['stdout'].lower(), 'ordinary actual signed USB caller installation')
            self.launch(role, 'identity'); self.launch(role, 'observe')

    def identity(self, role):
        name = bundle(CASE, role)
        bms = self.shell('bm dump -n ' + name, 'BMS_' + role)
        identity = dependency('hap_identity_binding').bms_application_identity(bms, name)
        value = loads(bms[bms.index('{'):])
        need(value['applicationInfo']['isSystemApp'] is False and value['applicationInfo']['appPrivilegeLevel'] == 'normal' and
             value.get('reqPermissions', []) == [] and value['hapModuleInfos'][0].get('extensionAbilities', []) == [],
             'ordinary HAP: real native USB right boundary, no system/API permission substitute')
        raw = self.shell(dependency('guest_process_identity').identity_shell(name), 'process_' + role)
        need(re.fullmatch('[1-9][0-9]*(?: [0-9]+){5}\n?', raw), 'actual live caller PID/birth/four UIDs')
        pid, birth, *uids = map(int, raw.split()); need(uids == [identity['uid']] * 4 and birth > 0, 'kernel caller identity')
        identity.update(pid=pid, birth_ticks=birth)
        paths = {v['hapPath'] for v in value['hapModuleInfos'] if v.get('hapPath')}
        need(len(paths) == 1, 'one actually installed source HAP')
        path = paths.pop()
        need(self.shell('sha256sum ' + shlex.quote(path), 'installed_HAP_' + role).split() ==
             [self.prepared['callers'][role]['signed']['sha256'], path], 'normal source/signer/installed HAP bytes')
        self.report['identities'].setdefault(role, []).append(identity); self.persist(); return identity

    def launch(self, role, action, decision=None):
        request = dict(run=self.io.run_id, boot=self.io.boot_id, operation=secrets.token_hex(16), action=action)
        row = dict(role=role, request=request)
        self.report['requests'].append(row); self.persist()
        name = bundle(CASE, role)
        reply = self.shell(shlex.join(['aa','start','-b',name,'-a','EntryAbility','--ps','request',json.dumps(request,separators=(',',':'))]), role + '_' + action)
        need('start ability successfully' in reply, 'actual existing UIAbility command')
        if decision is not None:
            need(action == 'permission' and decision in ('Allow', 'Deny'), 'fixed source-backed native USB dialog choice')
            # Actual normal USB permission UI, source bundle com.usb.right;
            # its button calls UsbService with the original caller token.
            tree, layout = self.io.ui.layout(bundle='com.usb.right', label='usb579_real_right_dialog')
            row['dialog_before'] = dict(layout=ref(layout), frame=self.io.frame('usb579_right_before'))
            row['decision'] = self.io.ui.click('com.usb.right', text=decision, label='usb579_actual_user_' + decision)
            row['dialog_after'] = self.io.frame('usb579_right_after')
        remote = '/data/app/el2/100/base/' + name + '/haps/entry/files/usb579-' + self.io.run_id + '.jsonl'
        def complete():
            raw = self.shell('if test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) + '; fi', role + '_journal')
            if not raw or not raw.endswith('\n'): return None
            records = [loads(line) for line in raw.splitlines()]
            return records if any(v.get('operation') == request['operation'] and v.get('event') == 'end' for v in records) else None
        records = self.poll(complete, action, 110)
        own = [v for v in records if v.get('operation') == request['operation'] and not v['event'].startswith('native-device-event') and v['event']!='actual-mtp-interrupt-callback']
        row['identity'] = self.identity(role)
        need(own[0]['event'] == 'begin' and own[-1]['event'] == 'end' and
             all(v['pid'] == row['identity']['pid'] and v['uid'] == row['identity']['uid'] for v in own), 'actual raw UID/PID operation')
        path = self.io.output / ('usb-' + request['operation'] + '.jsonl'); self.io.receive(remote, path, 'usb579_journal')
        row['journal'] = ref(path)
        descriptors=[loads(v['value']) for v in own if v['event']=='actual-usb-file-descriptor']
        if descriptors:
            need(len(descriptors)==1 and type(descriptors[0]) is int and descriptors[0]>=0, 'actual kernel USB FD')
            proc='/proc/'+str(row['identity']['pid'])+'/fd/'+str(descriptors[0])
            row['kernel_fd']=self.shell('readlink '+proc+'; stat -L -c "%F %u %i %t %T" '+proc+'; cat /proc/'+str(row['identity']['pid'])+'/fdinfo/'+str(descriptors[0]), 'actual_caller_kernel_USB_fd')
        stat = self.shell('stat -c "%u %i %s" ' + shlex.quote(remote), 'caller_journal_inode')
        row['journal_stat'] = stat
        need(int(stat.split()[0]) == row['identity']['uid'], 'actual own HAP raw file owner')
        tree, layout = self.io.ui.layout(bundle=name, label='usb579_actual_caller')
        row['visible'] = dict(layout=ref(layout), selected=dependency('guest_ui').select_node(tree,name,identifier='usb579-visible-caller'),
                              frame=self.io.frame('usb579_caller'))
        row['end_observed'] = True; self.persist()
        need(not any(v['event'] == 'throw' for v in own), 'actual original USB/MTP API failed')
        return row, own

    def link(self, *names):
        need(not self.bound and not self.links and names and set(names) <= set(('ffs.usb579','midi.usb579','ffs.mtp')), 'owned unbound fixed gadget functions')
        for name in names:
            self.links.append(name)  # Retain cleanup intent before mutation.
            self.shell('test ! -e ' + GADGET + '/configs/c.1/' + name + ' && ln -s ' + GADGET + '/functions/' + name + ' ' + GADGET + '/configs/c.1/' + name, 'link_' + name.replace('.','_'))

    def unlink(self):
        need(not self.bound, 'unbind actual UDC before unlink')
        for name in reversed(self.links):
            self.shell('test -L ' + GADGET + '/configs/c.1/' + name + ' && rm ' + GADGET + '/configs/c.1/' + name, 'unlink_' + name.replace('.','_'))
        self.links.clear()

    def edge(self, bound):
        need(bool(self.links) and self.bound is not bound, 'one real device binding transition')
        if bound:
            self.bound = True  # Intent precedes native kernel action.
            self.shell('test "$(cat ' + GADGET + '/UDC)" = "" && printf %s ' + self.udc + ' > ' + GADGET + '/UDC', 'actual_UDC_attach')
        else:
            self.shell('test "$(cat ' + GADGET + '/UDC)" = ' + self.udc + ' && printf "\\n" > ' + GADGET + '/UDC', 'actual_UDC_detach')
            self.bound = False
        def actual():
            text = self.shell('''for d in /sys/bus/usb/devices/*; do
 test -f "$d/idVendor" && test -f "$d/idProduct" && test -f "$d/serial" || continue
 if test "$(cat "$d/idVendor")" = 1d6b && test "$(cat "$d/idProduct")" = 0104 && test "$(cat "$d/serial")" = ''' + self.io.run_id + '''; then
  printf 'DEVICE=%s\n' "$d"; for f in busnum devnum idVendor idProduct serial product manufacturer; do printf '%s=' "$f"; cat "$d/$f"; done
  readlink -f "$d"; readlink -f "$d/driver"; sha256sum "$d/descriptors"
 fi
done
''', 'actual_host_device_transition')
            return (text if text else None) if bound else ('ABSENT' if not text else None)
        text = self.poll(actual, 'host USB attach/detach')
        self.report['kernel_edges'].append(dict(bound=bound, links=list(self.links), udc=self.udc, actual_host=text)); self.persist()

    def peer(self, mode, nonce, argument):
        script = 'exec ' + self.remote + '/usb579_device_peer ' + shlex.join([mode,nonce,argument])
        key = self.io.spawn_guest(script, 'usb579_independent_' + mode)
        row = dict(mode=mode, run=nonce, argument=argument, key=key, argv=self.io._long[key]['argv'])
        self.report['peers'].append(row); self.active.append(row); self.persist()
        def identity():
            body = self.io._long[key]['out'].read_text()
            rows = [loads(v) for v in body.splitlines() if v.startswith('{') and v.endswith('}')]
            return rows if any(v['event'] == 'identity' for v in rows) else None
        rows = self.poll(identity, 'actual separate native peer')
        native = rows[0]; need(native['uid'] == native['euid'] == 0 and native['boot'] == self.io.boot_id and native['run'] == nonce, 'native root peer same boot')
        pid = native['pid']; row['pid'] = pid
        row['kernel_identity'] = self.shell('cat /proc/' + str(pid) + '/stat /proc/' + str(pid) + '/status; cat /proc/' + str(pid) + '/attr/current | tr -d \'\\000\'; printf \'\\n\'; readlink /proc/' + str(pid) + '/exe; sha256sum /proc/' + str(pid) + '/exe; ls -l /proc/' + str(pid) + '/fd', 'peer_kernel_identity')
        self.persist(); return row

    def stop_peer(self, row):
        key = row['key']; child = self.io._long[key]['child']
        if child.poll() is None:
            row['stop_input'] = self.io.write_stdin(key, b'x\n')
        done = self.io.wait(key, timeout=40)
        row['completion'] = self.io.ref_receipt(done)
        row['stdout'] = done['stdout_ref']; row['stderr'] = done['stderr_ref']
        row['pid_absence'] = self.shell('if test -d /proc/' + str(row['pid']) + '; then exit 1; else echo ABSENT; fi', 'peer_process_absent')
        self.active.remove(row); self.persist()
        need(done['exit_code'] == done['transport_exit_code'] == 0, 'independent peer transport/native exit must both close normally')

    def bulk(self):
        self.link('ffs.usb579', 'midi.usb579')
        peer = self.peer('bulk', self.io.run_id, BULK_MOUNT)
        self.poll(lambda: 'descriptors-and-strings-written' in self.io._long[peer['key']]['out'].read_text(), 'actual FunctionFS descriptor write')
        self.edge(True)
        self.launch('a','enumerate'); self.launch('b','enumerate')
        denied,_ = self.launch('a','permission','Deny')
        self.report['denied'] = denied['request']['operation']; self.launch('a','boundary')
        self.launch('a','permission','Allow'); self.launch('a','open'); self.launch('a','bulk')
        self.launch('b','boundary')
        self.launch('a','revoke'); self.launch('a','release'); self.launch('a','boundary')
        self.launch('a','permission','Allow'); self.launch('a','open'); self.launch('a','bulk')
        before = self.identity('a'); self.report['killed_generation'] = before
        # Native process death while a real UsbService pipe/interface is live.
        self.shell('test "$(awk \'{print $22}\' /proc/' + str(before['pid']) + '/stat)" = ' + str(before['birth_ticks']) + ' && kill -9 ' + str(before['pid']), 'real_claiming_caller_death')
        self.poll(lambda: self.shell('if test -d /proc/' + str(before['pid']) + '; then echo PRESENT; else echo ABSENT; fi','dead_caller_absence').strip() == 'ABSENT', 'actual caller death')
        self.launch('b','permission','Allow'); self.launch('b','open'); self.launch('b','bulk')
        self.edge(False); self.launch('b','stale'); self.launch('b','release')
        self.edge(True); self.launch('b','permission','Allow'); self.launch('b','open'); self.launch('b','bulk'); self.launch('b','release')
        self.launch('a','identity'); after = self.identity('a'); self.report['recreated_generation'] = after
        need(after['uid'] == before['uid'] and after['pid'] != before['pid'] and after['birth_ticks'] > before['birth_ticks'], 'real caller recreation preserves UID and changes generation')
        self.launch('a','observe'); self.launch('a','permission','Allow'); self.launch('a','open'); self.launch('a','bulk'); self.launch('a','release')
        self.edge(False); self.stop_peer(peer); self.unlink()
        for role in ROLES: self.launch(role,'cleanup')

    def collect(self, audio_io, request, native_remote):
        """Fixed successor of Audio10's original MIDI wait, no new HAP/IO."""
        need(audio_io is self.audio_io and request['run'] == audio_io.run_id and request['action'] == 'midi' and
             not self.bound and not self.links, 'original launched actual MIDI caller and idle owned device')
        def journal(event, value=None):
            raw = self.shell('if test -f ' + shlex.quote(native_remote) + '; then cat ' + shlex.quote(native_remote) + '; fi', 'actual_MIDI_native_progress', io=audio_io)
            if not raw or not raw.endswith('\n'): return None
            rows = [loads(v) for v in raw.splitlines()]
            return rows if any(v.get('event') == event and (value is None or v.get('value') == value) for v in rows) else None
        self.poll(lambda: journal('actual-client-before-usb-attach',1), 'real MIDI client before attach')
        self.link('midi.usb579')
        for cycle in (1,2):
            self.edge(True)
            def raw_device():
                text = self.shell('''for f in /proc/asound/card*/id; do
 test -f "$f" || continue
 if test "$(cat "$f")" = ''' + self.card_id + '''; then
  card=${f%/id}; card=${card##*/card}
  for d in /dev/snd/midiC${card}D*; do if test -c "$d"; then printf '%s\n' "$d"; fi; done
 fi
done''', 'actual_gadget_raw_midi')
                paths=text.splitlines(); return paths[0] if len(paths)==1 and re.fullmatch('/dev/snd/midiC[0-9]+D[0-9]+',paths[0]) else None
            path = self.poll(raw_device, 'actual f_midi gadget ALSA card')
            self.report['midi'].append(dict(cycle=cycle, raw_device=path,
                source=self.shell('readlink -f /sys/class/sound/' + path.rsplit('/',1)[1] + '/device; stat -c "%u %i %t %T" ' + path + '; cat /proc/asound/cards', 'actual_MIDI_kernel_device')))
            peer = self.peer('midi', audio_io.run_id, path)
            self.poll(lambda: journal('actual-independent-midi-round',cycle), 'genuine bidirectional public MIDI round',45)
            self.edge(False); self.stop_peer(peer)
            if cycle==1: self.poll(lambda: journal('actual-waiting-for-usb-rebind',1), 'real MIDI detach callback/stale handle')
        self.unlink()
        rows = self.poll(lambda: journal('end'), 'actual MIDI destroy/quiet lifecycle',20)
        need(rows[-1]['event']=='end' and rows[-1]['value']==1, 'native MIDI session incomplete')
        output = dict(usb_output=str(self.io.output), run=self.io.run_id, audio_run=audio_io.run_id,
            operation=request['operation'], archive_sha256=audio_io.archive_sha256, boot_id=audio_io.boot_id,
            peer_indices=[i for i,v in enumerate(self.report['peers']) if v['mode']=='midi'])
        self.report['midi_operation'] = request['operation']; self.persist(); return output

    def provider(self, label):
        # This discovers actual loaded original MediaLibrary/MTP and HDI DSOs,
        # not a guessed HAP declaration or a test extension/returned marker.
        script='''set -e
for p in /proc/[0-9]*; do
 test -r "$p/maps" || continue
 if grep -q '/libmedia_mtp.z.so' "$p/maps"; then
  printf 'MEDIA_PID=%s\n' "${p##*/}"; cat "$p/stat" "$p/status" "$p/attr/current"; tr '\\000' ' ' < "$p/cmdline"; echo
  cat "$p/maps"; ls -l "$p/fd"
 fi
 if grep -q '/libusbfn_mtp_interface_service_1.0.z.so' "$p/maps"; then
  printf 'HDI_PID=%s\n' "${p##*/}"; cat "$p/stat" "$p/status" "$p/attr/current"; cat "$p/maps"; ls -l "$p/fd"
 fi
done'''
        raw=self.shell(script,label); media=re.findall(r'^MEDIA_PID=([1-9][0-9]*)$',raw,re.M); hdi=re.findall(r'^HDI_PID=([1-9][0-9]*)$',raw,re.M)
        if not media or not hdi: return None
        need(len(media)==len(hdi)==1 and '/dev/usb-ffs/mtp/ep0' in raw and '/dev/usb-ffs/mtp/ep3' in raw,
             'normal DataShare MediaLibrary service and genuine HDI FunctionFS endpoint ownership')
        value=dict(media_pid=int(media[0]),hdi_pid=int(hdi[0]),actual=raw)
        self.report.setdefault('providers',[]).append(value);self.persist();return value

    def backing(self, provider, operation, partial=False, absent=False):
        filename='usb579-'+self.io.run_id+'-'+operation+('-cancel' if partial else '')+'.bin'
        path='/proc/'+str(provider['media_pid'])+'/root/storage/media/local/files/Docs/'+filename
        # Read through the real provider mount namespace. The HAP supplies no
        # path/handle/blob to this observer; the filename is fixed source nonce.
        if absent:
            raw=self.shell('test ! -e '+path+' && echo ABSENT','actual_MTP_backing_deleted')
            need(raw.strip()=='ABSENT','original provider retained owned object')
            self.report['files'].append(dict(operation=operation,partial=partial,absent=True,path=path,actual=raw));self.persist();return
        def actual():
            raw=self.shell('if test -f '+path+' && test ! -L '+path+'; then stat -c "%u %g %i %s" '+path+'; sha256sum '+path+'; fi','actual_MTP_backing_inode')
            return raw if len(raw.splitlines())==2 and int(raw.splitlines()[0].split()[-1])>0 else None
        raw=self.poll(actual,'real media-library created file')
        local=self.io.output/('mtp-backing-'+operation+'.bin');self.io.receive(path,local,'usb579_actual_provider_file')
        self.report['files'].append(dict(operation=operation,partial=partial,absent=False,path=path,actual=raw,bytes=ref(local),provider_pid=provider['media_pid']))
        self.persist()

    def mtp(self):
        # Existing whole PhotoAccessHelper/MediaLibrary producer must already
        # activate its genuine DataShare entry through normal public business.
        provider=self.poll(lambda: self.provider('actual_normal_MTP_provider'), 'normal existing MediaLibrary entry',30)
        self.report['provider_baseline']=provider
        self.link('ffs.mtp');self.edge(True)
        self.launch('a','permission','Allow');self.launch('a','mtp-open')
        for action in ('mtp-small','mtp-object'):
            row,_=self.launch('a',action);op=row['request']['operation'];self.backing(provider,op)
            self.launch('a','mtp-delete');self.backing(provider,op,absent=True)
        row,_=self.launch('a','mtp-cancel');op=row['request']['operation'];self.backing(provider,op,partial=True)
        self.launch('a','mtp-cancel-finish');self.backing(provider,op,partial=True,absent=True)
        self.launch('a','mtp-close');self.edge(False);self.unlink()
        self.report['provider_after']=self.provider('actual_normal_MTP_provider_after')

    def cleanup(self):
        if self.finished:return
        errors=[]
        def attempt(name, callback):
            try:callback()
            except Exception as error:errors.append(dict(resource=name,error=type(error).__name__+': '+str(error)))
        if self.bound:attempt('UDC',lambda:self.edge(False))
        for peer in tuple(reversed(self.active)):attempt('peer',lambda p=peer:self.stop_peer(p))
        if not self.bound and self.links:attempt('links',self.unlink)
        for role in reversed(self.installed):
            def remove(r=role):
                name=bundle(CASE,r)
                self.shell('aa force-stop '+name,'cleanup_stop_'+r,failure=True)
                need(self.shell('if pidof '+name+'; then exit 1; else echo ABSENT; fi','cleanup_pid_'+r).strip()=='ABSENT','real caller still running')
                row=self.io.command([self.io.hdc,'-t',self.io.target,'uninstall',name],'usb579_uninstall_'+r)
                need('success' in row['stdout'].lower(),'actual caller uninstall')
                listing=self.shell('bm dump -a','cleanup_BMS_'+r)
                need('com.ohos.' in listing and not re.search(r'(?<![\w.])'+re.escape(name)+r'(?![\w.])',listing),'BMS caller cleanup')
            attempt(role,remove)
        if self.baseline is not None:
            def restore():
                self.shell('test "$(cat '+GADGET+'/UDC)" = "" && printf %s QEMU_SHARED_UNBOUND > '+GADGET+'/strings/0x409/serialnumber && printf %s QEMU_MIDI > '+GADGET+'/functions/midi.usb579/id','restore_normal_unbound_device')
                self.shell('test ! -e '+self.remote+' || { rm -f '+self.remote+'/usb579_device_peer && rmdir '+self.remote+'; }','cleanup_owned_peer_files')
                after=self.snapshot('unrelated_gadget_after');self.report['restored']=after
                need(after==self.baseline,'unrelated g1/HDC/function/EDM/security baseline changed')
            attempt('normal product baseline',restore)
        self.report['cleanup_errors'].extend(errors)
        self.report['cleanup']=dict(errors=errors,original_Owner_finish_still_required=True,
            all_gadget_peers_reaped=not self.active,unbound=not self.bound,links_removed=not self.links,
            permanent_init_gadget_and_mounts_preserved=True)
        self.persist();self.finished=not errors
        need(not errors,'shared device cleanup uncertain; stop guest reuse')


def run(usb_io,audio_io):
    """Root passes the two original IOs, closes them after this fixed sequence."""
    session=SharedDevice(usb_io,audio_io)
    audio_result=None;ready=False
    try:
        try:
            session.begin();session.bulk();ready=True
        except Exception as error:
            session.report['failures'].append('USB: '+type(error).__name__+': '+str(error));session.persist()
            # Settle owned USB resources before reusing this guest. A cleanup
            # uncertainty raises and stops reuse under the original Owner.
            session.cleanup()
        from audio579_runtime import run as run_audio
        # Preserve the original full Audio10 invocation even when USB failed.
        # Missing real MIDI raw remains an actual unresolved Audio sub-scope.
        audio_result=run_audio(audio_io,shared_midi=session if ready else None)
        session.report['audio_evidence']=audio_result;session.persist()
        if ready:session.mtp()
    except Exception as error:
        session.report['failures'].append(type(error).__name__+': '+str(error));session.persist()
    finally:
        session.cleanup()
    return dict(usb_evidence=ref(session.path),audio_evidence=audio_result,
        archive_sha256=usb_io.archive_sha256,boot_id=usb_io.boot_id,
        runtime_pass=False,closed_ids=[],first_artifact_behavior_gate_passed=False)
