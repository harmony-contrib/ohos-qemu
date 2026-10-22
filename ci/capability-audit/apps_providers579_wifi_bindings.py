"""Seven callbacks on the original held IO; real isolated-radio fixture only.

No Owner/Guest/runner/lease/process/listener is constructed here. Original
spawn_guest holds the finite native helper and stock daemons, preserving wire
stdout/stderr/status. The helper creates only the guest's fixture namespace.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

from apps_providers579_bindings import bind as base_bind, raw, objects
from apps_providers579_project import require
from guest_ui import NodeNotReady, LayoutNotReady, bounds, select_node


def bind(root_io):
    io = root_io
    base = base_bind(io)
    run = io.run_id
    require(re.fullmatch('[a-f0-9]{32}', run), 'actual original nonce required')
    output = Path(io.output) / ('apps579_wifi_ip_' + run)
    output.mkdir(exist_ok=False)
    remote = '/data/local/tmp/apps579_wifi_' + run
    executable = remote + '/wifi_peer'
    state = {'serial': 0, 'namespace': None, 'namespace_pid': None, 'phy': None,
        'daemon': None, 'server': None, 'server_pid': None, 'mode': None, 'moved': False, 'mounted': False,
        'created': False, 'closed': False, 'probe_before': None, 'original_radios': None,
        'native_prefix': {}, 'partial_snapshots': [], 'exchange_pids': set()}

    def save(label, data):
        state['serial'] += 1
        path = output / ('%05d_' % state['serial'] + label)
        path.write_bytes(data.encode() if type(data) is str else data)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def shell(script, label, timeout=60, allow_failure=False):
        require(re.fullmatch('[a-zA-Z0-9_-]+', label), 'finite guest shell label')
        return io.shell('set -eu\n' + script, 'apps579_wifi_ip_' + label, timeout=timeout, allow_failure=allow_failure)

    def begin(label):
        mark = len(io.receipts), len(io.qmp_receipts)
        require(shell('cat /proc/sys/kernel/random/boot_id', label + '_boot')['stdout'].strip() == io.boot_id,
                'same original held boot required')
        return mark

    def result(mark, **extra):
        return {'boot_id': io.boot_id, 'archive_sha256': io.archive_sha256,
            'commands': [io.ref_receipt(row) for row in io.receipts[mark[0]:]],
            'qmp_records': io.qmp_receipts[mark[1]:], 'native_partial_snapshots': list(state['partial_snapshots']), **extra}

    def helper(mode, *data):
        row = shell(shlex.join([executable, mode, run, *map(str, data)]), 'helper_' + mode)
        require(row['exit_code'] == 0 and not row['timed_out'], 'actual fixed helper failed')
        return row

    def await_file(leaf):
        require(leaf in ('namespace.txt', 'ap-ready', 'sta-ready', 'dhcp-client.txt'), 'finite actual marker')
        deadline = time.monotonic() + 65
        while True:
            observed = shell('cat ' + shlex.quote(remote + '/' + leaf), 'marker_' + leaf.replace('.', '_'), allow_failure=True)
            if observed['exit_code'] == 0:
                return observed
            require(time.monotonic() < deadline, 'actual namespace/peer marker did not arrive; retain original transport')
            time.sleep(.25)

    def journals():
        listing = shell('ls ' + remote + '/*.jsonl', 'native_journal_list')
        files, events = [], []
        for path in sorted(listing['stdout'].splitlines()):
            require(re.fullmatch(re.escape(remote) + r'/[a-z-]+-[1-9][0-9]*\.jsonl', path), 'fixed own native journal path')
            for attempt in range(8):
                state['serial'] += 1
                local = output / ('native_%05d.jsonl' % state['serial'])
                io.receive(path, local, 'apps579_wifi_ip_journal_' + str(state['serial']))
                body = local.read_bytes()
                ref = {'path': str(local), 'sha256': hashlib.sha256(body).hexdigest()}
                require(body.startswith(state['native_prefix'].get(path, b'')), 'actual native journal truncated or replaced')
                if body.endswith(b'\n'):
                    break
                state['partial_snapshots'].append({'remote': path, 'raw': ref})
                require(attempt < 7, 'native append did not reach a complete source record')
                time.sleep(.05)
            state['native_prefix'][path] = body
            values = [json.loads(line) for line in body.decode().splitlines() if line]
            require(values and all(row['run_id'] == run and row['seq'] == n and type(row['netns']) is int and
                    row['uid'] == 0 and path.endswith('-' + str(row['pid']) + '.jsonl') and
                    re.fullmatch('[a-f0-9]*', row['hex']) for n, row in enumerate(values)), 'real native identity/sequence/wire journal')
            files.append({'remote': path, 'raw': ref}); events.extend(values)
        return files, events

    def control(mode, command):
        row = shell(shlex.join(['/vendor/bin/wpa_cli', '-p', remote + '/control', '-i', 's579peer', 'raw', command]),
                    'stock_control_' + re.sub('[^A-Za-z0-9_-]', '_', command), allow_failure=True)
        return row

    def stop_peer():
        receipts = []
        if state['server'] is not None:
            receipts.append(io.write_stdin(state['server'], ('QUIT ' + run + '\n').encode()))
            finished = io.wait(state['server'], timeout=30)
            require(finished['exit_code'] == 0 and not finished['timed_out'], 'actual namespace server did not close')
            receipts.append(io.ref_receipt(finished)); state['server'] = None;state['server_pid'] = None
        if state['daemon'] is not None:
            if state['mode'] == 'p2p':
                removed = control('p2p', 'P2P_GROUP_REMOVE s579peer')
                require(removed['exit_code'] == 0 and 'OK' in removed['stdout'].splitlines(), 'real peer P2P group removal required')
                receipts.append(io.ref_receipt(removed))
            stopped = control(state['mode'], 'TERMINATE')
            require(stopped['exit_code'] == 0 and 'OK' in stopped['stdout'].splitlines(), 'stock daemon control must terminate its real process')
            finished = io.wait(state['daemon'], timeout=30)
            require(finished['exit_code'] == 0 and not finished['timed_out'], 'actual stock daemon transport did not finish')
            receipts.append(io.ref_receipt(finished)); state['daemon'] = None
        if state['mode']:
            leaves = ['ap-ready'] if state['mode'] in ('ap', 'p2p') else ['sta-ready', 'dhcp-client.txt']
            for leaf in leaves:
                captured = shell('cat ' + shlex.quote(remote + '/' + leaf), 'finished_' + leaf.replace('.', '_'), allow_failure=True)
                if captured['exit_code'] == 0:
                    receipts.append(io.ref_receipt(captured))
                    shell('rm ' + shlex.quote(remote + '/' + leaf), 'retire_' + leaf.replace('.', '_'))
        state['mode'] = None
        return receipts

    def network(action, parameters):
        if action not in ('wifi-radio-prepare', 'wifi-peer-start', 'wifi-peer-collect', 'wifi-peer-stop',
                'wifi-radio-collect', 'wifi-data-exchange', 'wifi-portal-config', 'wifi-ip-collect',
                'wifi-p2p-peer-start', 'wifi-p2p-peer-collect', 'wifi-p2p-arm', 'wifi-p2p-data'):
            return base['network'](action, parameters)
        mark = begin(action)
        require(type(parameters) is dict, 'finite source-defined network data')
        if action == 'wifi-radio-prepare':
            require(parameters == {} and not state['created'], 'one fresh two-radio fixture only')
            spec = io.package_inputs['native_helpers']['apps579_wifi']
            require(set(spec) == {'binary', 'build', 'source', 'abi'} and spec['abi'] in ('arm64', 'arm', 'x86_64'), 'actual platform fixture build schema')
            environment = io.test_environment if hasattr(io, 'test_environment') else io.guest.report['test_environment']
            require(spec['abi'] == environment['guest_arch'], 'actual native helper architecture differs from current package')
            for key in ('binary', 'build', 'source'):
                raw(spec[key])
            source = Path(__file__).with_name('apps_providers579') / 'wifi_peer.c'
            require(hashlib.sha256(source.read_bytes()).hexdigest() == spec['source']['sha256'], 'actual built fixed helper source differs')
            inventory = shell('readlink -f /sys/class/net/wlan0/phy80211\nreadlink -f /sys/class/net/wlan1/phy80211\n'
                'cat /sys/class/net/wlan0/operstate /sys/class/net/wlan1/operstate\n'
                'cat /sys/class/net/wlan0/address /sys/class/net/wlan1/address\n'
                'test -x /vendor/bin/hostapd\ntest -x /vendor/bin/wpa_supplicant\ntest -x /vendor/bin/wpa_cli', 'two_actual_radios')
            lines = inventory['stdout'].splitlines()
            require(len(lines) == 6 and lines[0] != lines[1] and lines[2:4] == ['down', 'down'], 'two distinct idle source-provided hwsim radios required')
            phy = re.search(r'/ieee80211/phy([0-9]+)$', lines[1]);require(phy, 'actual spare wiphy index required')
            state['original_radios'] = inventory['stdout_ref']; state['phy'] = int(phy[1])
            shell('test ! -e ' + remote + '\nmkdir -m 700 ' + remote + '\nmkdir -m 700 ' + remote + '/control', 'fresh_fixture_directory')
            state['created'] = True
            io.send(spec['binary']['path'], executable, 'apps579_wifi_ip_helper_send')
            digest = shell('chmod 700 ' + executable + '\nsha256sum ' + executable, 'actual_helper_bytes')
            require(digest['stdout'].split() == [spec['binary']['sha256'], executable], 'guest helper differs from actual platform build')
            state['namespace'] = io.spawn_guest(shlex.join([executable, 'hold', run]), 'apps579_wifi_namespace')
            marker = await_file('namespace.txt')
            match = re.fullmatch(r'pid=([1-9][0-9]*) original=([1-9][0-9]*) peer=([1-9][0-9]*)', marker['stdout'])
            require(match and match[2] != match[3], 'real independent network namespace identity required')
            state['namespace_pid'] = int(match[1]); state['initial_netns'] = int(match[2]); state['peer_netns'] = int(match[3])
            helper('inspect-initial')
            _, initial_events = journals()
            require(not any(row['netns'] == state['initial_netns'] and row['event'] == 'interface-ipv4' and
                    bytes.fromhex(row['hex']).decode().startswith('wlan1 ') for row in initial_events),
                    'refuse moving a spare radio with an existing IPv4 address')
            helper('move', state['namespace_pid'], state['phy']); state['moved'] = True
            files, events = journals()
            return result(mark, inventory=inventory['stdout_ref'], namespace=marker['stdout_ref'],
                helper=spec, native_journals=files, native_events=events)
        if action == 'wifi-p2p-peer-start':
            require(parameters == {} and state['moved'] and state['daemon'] is None and state['server'] is None,
                'fresh original namespace P2P peer only')
            body = ('ctrl_interface=' + remote + '/control\nupdate_config=0\np2p_no_group_iface=1\n'
                'device_name=whole579_' + run[:12] + '\ndevice_type=1-0050F204-1\nconfig_methods=virtual_push_button\n')
            config = output / 'p2p.conf';require(not config.exists(), 'fresh finite P2P configuration')
            config.write_text(body);io.send(config, remote + '/p2p.conf', 'apps579_wifi_p2p_config')
            state['mode'] = 'p2p'
            state['daemon'] = io.spawn_guest(shlex.join([executable, 'daemon-p2p', run, str(state['namespace_pid'])]), 'apps579_wifi_stock_p2p')
            deadline = time.monotonic() + 30
            while True:
                ping = control('p2p', 'PING')
                if ping['exit_code'] == 0 and 'PONG' in ping['stdout'].splitlines():break
                require(time.monotonic() < deadline, 'real independent P2P supplicant did not start');time.sleep(.1)
            group = control('p2p', 'P2P_GROUP_ADD freq=2412')
            require(group['exit_code'] == 0 and 'OK' in group['stdout'].splitlines(), 'stock P2P_GROUP_ADD rejected')
            while True:
                status = control('p2p', 'STATUS')
                if status['exit_code'] == 0 and 'mode=P2P GO' in status['stdout'].splitlines():break
                require(time.monotonic() < deadline, 'stock independent P2P GO did not become active');time.sleep(.1)
            # Same finite DHCP/DNS/nonce server; only its held P2P radio now
            # carries these real L2/IP bytes. No normal STA config is selected.
            state['server'] = io.spawn_guest(shlex.join([executable, 'server-ap', run, str(state['namespace_pid'])]), 'apps579_wifi_p2p_ip_server')
            marker = await_file('ap-ready');identity = re.fullmatch(r'pid=([1-9][0-9]*) netns=([1-9][0-9]*)', marker['stdout'])
            require(identity and int(identity[2]) == state['peer_netns'], 'P2P server actual netns')
            state['server_pid'] = int(identity[1]);files,events = journals()
            return result(mark, status=status['stdout_ref'], group_create=group['stdout_ref'], configuration={'path': str(config),
                'sha256': hashlib.sha256(config.read_bytes()).hexdigest()}, independent_server=marker['stdout_ref'],
                native_journals=files, native_events=events)
        if action == 'wifi-p2p-arm':
            require(parameters == {} and state['mode'] == 'p2p' and state['daemon'], 'same actual held P2P GO')
            armed = control('p2p', 'WPS_PBC')
            require(armed['exit_code'] == 0 and 'OK' in armed['stdout'].splitlines(), 'stock real WPS PBC authorization failed')
            return result(mark, wps=armed['stdout_ref'])
        if action == 'wifi-p2p-peer-collect':
            require(parameters == {} and state['mode'] == 'p2p', 'same retained independent P2P peer')
            status = control('p2p', 'STATUS');station = control('p2p', 'STA-FIRST');helper('inspect', state['namespace_pid'])
            files,events = journals()
            # Actual P2P device identity, not the ordinary interface MAC.
            addresses = re.findall(r'^p2p_device_address=([0-9a-f:]{17})$', status['stdout'], re.M)
            require(len(addresses) == 1, 'real supplicant P2P device address')
            return result(mark, status=status['stdout_ref'], station=station['stdout_ref'], peer_mac=addresses[0],
                namespace=state['peer_netns'], native_journals=files, native_events=events)
        if action == 'wifi-p2p-data':
            require(state['server'] and state['mode'] == 'p2p' and set(parameters) == {'interface'} and
                re.fullmatch(r'p2p0|p2p-wlan0-[0-9]+', parameters['interface']), 'actual public P2P interface only')
            helper('exchange', parameters['interface'], '192.0.2.1');files,events = journals()
            pids = {r['pid'] for r in events if r['event'] == 'nonce-initial-tx'};fresh = pids - state['exchange_pids']
            require(len(fresh) == 1, 'fresh actual P2P native exchange process');state['exchange_pids'] = pids
            return result(mark, current_exchange_pid=next(iter(fresh)), server_pid=state['server_pid'], side='p2p',
                peer_ip='192.0.2.1', interface=parameters['interface'], initial_netns=state['initial_netns'],
                peer_netns=state['peer_netns'], native_journals=files, native_events=events)
        if action == 'wifi-peer-start':
            require(parameters in ({'mode': 'ap'}, {'mode': 'sta'}) and state['moved'] and state['daemon'] is None and state['server'] is None,
                    'one real peer mode in held independent namespace')
            mode = parameters['mode']
            if mode == 'ap':
                body = ('interface=s579peer\ndriver=nl80211\nctrl_interface=' + remote + '/control\n'
                    'ssid=apps579_' + run[:12] + '\nhw_mode=g\nchannel=1\nwpa=2\nwpa_key_mgmt=WPA-PSK\n'
                    'wpa_passphrase=apps579_' + run[:16] + '\nrsn_pairwise=CCMP\n')
            else:
                body = ('ctrl_interface=' + remote + '/control\nnetwork={\n ssid="apps579_ap_' + run[:12] + '"\n'
                    ' psk="apps579_' + run[:16] + '"\n key_mgmt=WPA-PSK\n}\n')
            config = output / (mode + '.conf')
            require(not config.exists() or config.read_text() == body, 'owned mode configuration changed')
            if not config.exists():
                config.write_text(body)
            io.send(config, remote + '/' + mode + '.conf', 'apps579_wifi_ip_config')
            state['mode'] = mode
            state['daemon'] = io.spawn_guest(shlex.join([executable, 'daemon-' + mode, run, str(state['namespace_pid'])]), 'apps579_wifi_stock_' + mode)
            deadline = time.monotonic() + 30
            while True:
                status = control(mode, 'STATUS')
                if status['exit_code'] == 0 and ('state=ENABLED' if mode == 'ap' else 'wpa_state=COMPLETED') in status['stdout']:
                    break
                require(time.monotonic() < deadline, 'actual private stock radio/WPA not ready')
                time.sleep(.25)
            state['server'] = io.spawn_guest(shlex.join([executable, 'server-' + mode, run, str(state['namespace_pid'])]), 'apps579_wifi_ip_server_' + mode)
            marker = await_file(mode + '-ready')
            identity = re.fullmatch(r'pid=([1-9][0-9]*) netns=([1-9][0-9]*)', marker['stdout'])
            require(identity and int(identity[2]) == state['peer_netns'], 'actual server must run inside the held independent namespace')
            state['server_pid'] = int(identity[1])
            return result(mark, actual_status=status['stdout_ref'], independent_server=marker['stdout_ref'],
                configuration={'path': str(config), 'sha256': hashlib.sha256(config.read_bytes()).hexdigest()})
        if action == 'wifi-peer-stop':
            require(parameters == {}, 'finite retained peer stop')
            receipts = stop_peer();files, events = journals()
            return result(mark, transports=receipts, native_journals=files, native_events=events)
        if action == 'wifi-peer-collect':
            require(parameters == {} and state['daemon'], 'actual retained namespace radio required')
            status = control(state['mode'], 'STATUS')
            station = control(state['mode'], 'STA-FIRST') if state['mode'] == 'ap' else None
            info = helper('inspect', state['namespace_pid'])
            files, events = journals()
            actual_macs = [bytes.fromhex(row['hex']).decode() for row in events if row['netns'] == state['peer_netns'] and row['event'] == 'interface-mac']
            require(actual_macs and len(set(actual_macs)) == 1, 'actual peer-netns ioctl MAC must remain unique')
            mac = save('actual_peer_mac.txt', actual_macs[-1] + '\n')
            return result(mark, mode=state['mode'], status=status['stdout_ref'], station=station['stdout_ref'] if station else None,
                mac=mac, native_journals=files, native_events=events, namespace=state['peer_netns'])
        if action == 'wifi-data-exchange':
            require(state['server'] and set(parameters) == {'side'} and parameters['side'] in ('sta', 'ap'), 'finite actual wireless data direction')
            side = parameters['side']
            if side == 'sta':
                require(state['mode'] == 'ap', 'OS STA must use isolated stock AP peer');peer_ip = '192.0.2.1';iface = 'wlan0'
            else:
                require(state['mode'] == 'sta', 'OS AP must use isolated stock STA peer')
                lease = await_file('dhcp-client.txt');match = re.fullmatch(r'address=([0-9.]+) mask=([0-9.]+) server=([0-9.]+) router=([0-9.]+) dns=([0-9.]+)', lease['stdout'])
                require(match, 'actual native DHCP server ACK must assign peer IPv4');peer_ip = match[1];iface = 'wlan1'
            helper('exchange', iface, peer_ip)
            files, events = journals()
            pids = {row['pid'] for row in events if row['event'] == 'nonce-initial-tx'}
            fresh = pids - state['exchange_pids']
            require(len(fresh) == 1, 'one newly executed actual data client journal required')
            state['exchange_pids'] = pids
            return result(mark, current_exchange_pid=next(iter(fresh)), server_pid=state['server_pid'], side=side, peer_ip=peer_ip, interface=iface, initial_netns=state['initial_netns'],
                peer_netns=state['peer_netns'], native_journals=files, native_events=events)
        if action == 'wifi-portal-config':
            require(parameters == {} and not state['mounted'] and state['mode'] == 'ap', 'one reversible actual OS probe config')
            before = shell('sha256sum /system/etc/netdetectionurl.conf\ncat /system/etc/netdetectionurl.conf\ncat /proc/self/mountinfo', 'original_probe_config')
            require(not any(line.split()[4] == '/system/etc/netdetectionurl.conf' for line in before['stdout'].splitlines() if len(line.split()) > 5 and ' - ' in line),
                    'refuse preexisting foreign detector bind mount')
            state['probe_before'] = before['stdout'].splitlines()[0]
            body = ('HttpProbeUrl:http://wifi.apps579.invalid/probe/' + run + '/primary\n'
                'HttpsProbeUrl:https://wifi.apps579.invalid/probe/' + run + '/tls\n'
                'FallbackHttpProbeUrl:http://wifi-fallback.apps579.invalid/probe/' + run + '/fallback\n'
                'FallbackHttpsProbeUrl:https://wifi-fallback.apps579.invalid/probe/' + run + '/tls-fallback\n')
            config = output / 'probe.conf';config.write_text(body);io.send(config, remote + '/probe.conf', 'apps579_wifi_probe_config')
            helper('config-mount');state['mounted'] = True
            after = shell('sha256sum /system/etc/netdetectionurl.conf\ncat /system/etc/netdetectionurl.conf\ncat /proc/self/mountinfo', 'mounted_probe_config')
            require(after['stdout'].splitlines()[0].split()[0] == hashlib.sha256(config.read_bytes()).hexdigest(), 'actual OS detector config bytes differ')
            return result(mark, before=before['stdout_ref'], after=after['stdout_ref'], config={'path': str(config), 'sha256': hashlib.sha256(config.read_bytes()).hexdigest()},
                scope='real_OS_302_then_dual_HTTP_204_algorithm; HTTPS_failures_retained_not_TLS_acceptance')
        if action in ('wifi-radio-collect', 'wifi-ip-collect'):
            require(parameters == {}, 'actual service/kernel/wire records only')
            records = {}
            for name, script in {'route': 'cat /proc/net/route', 'arp': 'cat /proc/net/arp', 'devices': 'cat /proc/net/dev',
                'wifi': 'hidumper -s 1120', 'netmanager': 'hidumper -s 1151', 'notifications': 'hidumper -s 3203',
                'ams': 'aa dump -a -u 100', 'hilog': 'hilog -x',
                'thermal': 'for zone in /sys/class/thermal/thermal_zone*; do if test -d "$zone"; then cat "$zone/type" "$zone/temp"; fi; done'}.items():
                records[name] = shell(script, 'service_' + name, allow_failure=True)['stdout_ref']
            files, events = journals()
            return result(mark, records=records, native_journals=files, native_events=events)

    def input(action, payload):
        if action not in ('wifi-location-permission', 'wifi-notification-open', 'wifi-hotspot-notification-reenable', 'wifi-portal-authorize'):
            return base['input'](action, payload)
        mark = begin(action);require(payload == {}, 'finite provider UI action has no injected selector')
        if action == 'wifi-location-permission':
            label = 'Apps579 wifi grant ' + run[:8]
            provider = 'com.ohos.permissionmanager'
            titles = ('Allow ' + label + ' to access your location?', '允许“' + label + '”访问你的位置？')
            deadline = time.monotonic() + 30
            trace = []
            while True:
                native = shell('cat /data/app/el2/100/base/org.ohos.qemu.apps579.wifi.grant/files/apps579-' + run + '-*.jsonl',
                               'actual_permission_journal', allow_failure=True)
                if native['exit_code'] == 0:
                    values = [json.loads(line) for line in native['stdout'].splitlines() if line]
                    found = [row for row in values if row['run_id'] == run and row['kind'] == 'wifi' and
                        row['role'] == 'grant' and row['event'] == 'permission-result']
                    if found:
                        return result(mark, permission_journal=native['stdout_ref'], ui_actions=trace)
                try:
                    layout, path = io.ui.layout(label='apps579_wifi_location_permission')
                    title_nodes = []
                    for title in titles:
                        try:
                            title_nodes.append(select_node(layout, provider, text=title))
                        except NodeNotReady:
                            pass
                    if not title_nodes:
                        raise NodeNotReady('actual nonce-named location permission dialog absent')
                    require(len(title_nodes) == 1, 'one exact caller-named native location permission title')
                    off = []
                    for text in ('Precise location: Off', '精确位置：关闭'):
                        try:
                            off.append(select_node(layout, provider, text=text, clickable=True))
                        except NodeNotReady:
                            pass
                    require(len(off) <= 1, 'one actual precise-location control')
                    trace.append({'layout': save('permission_layout.json', json.dumps(layout)), 'original_layout': str(path),
                                  'title': title_nodes[0], 'frame': io.frame('apps579_wifi_location_permission')})
                    if off:
                        x,y,w,h = off[0]['rect']
                        io.ui.shell('uitest uiInput click ' + str(x+w//2) + ' ' + str(y+h//2), 'apps579_wifi_precise_location_on')
                        trace.append({'clicked_precise_off_to_on': off[0]})
                    else:
                        allow = []
                        for text in ('Allow while using the app', '仅使用期间允许'):
                            try:
                                allow.append(io.ui.click(provider, text=text, label='apps579_wifi_location_allow'))
                            except NodeNotReady:
                                pass
                        require(len(allow) == 1, 'one source-defined foreground location grant control')
                        trace.append({'native_grant': allow[0]})
                except (NodeNotReady, LayoutNotReady):
                    pass
                require(time.monotonic() < deadline, 'actual requested location grants did not finish')
                time.sleep(.25)
        if action in ('wifi-notification-open', 'wifi-hotspot-notification-reenable'):
            from PIL import Image
            frame = io.frame('apps579_wifi_before_shade')
            with Image.open(frame['path']) as image:
                width, height = image.size
            io.ui.shell('uitest uiInput swipe ' + ' '.join(map(str, (width//2, 1, width//2, height*3//4))), 'apps579_wifi_notification_shade')
            ssid = 'apps579_' + run[:12]
            texts = (('Turn on hotspot', '开启热点') if action == 'wifi-hotspot-notification-reenable' else
                ('Tap to log in to ' + ssid + '.', '点击进行登录/认证' + ssid, 'Connected to ' + ssid))
            owners = {'com.ohos.sceneboard', 'com.ohos.systemui'}
        else:
            texts = ('Allow WiFi ' + run,); owners = {'com.wifiservice.portallogin'}
        deadline = time.monotonic() + 30
        while True:
            try:
                layout, path = io.ui.layout(label='apps579_wifi_actual_control')
                matches = []
                if action == 'wifi-hotspot-notification-reenable':
                    title_nodes = []
                    for provider in owners:
                        for text in ('Hotspot disabled', '热点已关闭'):
                            try:
                                title_nodes.append(select_node(layout, provider, text=text))
                            except NodeNotReady:
                                pass
                    if not title_nodes:
                        raise NodeNotReady('actual OS hotspot-disabled notification title absent')
                    require(len(title_nodes) == 1, 'one actual source-bound hotspot-disabled notification')
                def visit(node, inherited='', ancestors=()):
                    attrs = node['attributes']; who = attrs.get('bundleName') or inherited;chain = ancestors + ((node, who),)
                    if who in owners and attrs.get('text') in texts and attrs.get('visible') == 'true':
                        targets = [(n, b) for n, b in reversed(chain) if b == who and n['attributes'].get('clickable') == 'true' and n['attributes'].get('enabled') == 'true' and n['attributes'].get('visible') == 'true']
                        require(targets, 'actual source-bound notification/web link clickable ancestor required')
                        chosen = targets[0][0]['attributes'];matches.append({'attributes': chosen, 'bundle': who, 'text': attrs['text'], 'rect': list(bounds(chosen['bounds']))})
                    for child in node.get('children', []):
                        visit(child, who, chain)
                for node in (layout if type(layout) is list else [layout]):
                    visit(node)
                # A card title and body can share the same actual clickable ancestor.
                unique = {tuple(n['rect']): n for n in matches};require(len(unique) <= 1, 'ambiguous actual WiFi provider control')
                if not unique:
                    raise NodeNotReady('real source-defined WiFi notification or nonce web link absent')
                node = next(iter(unique.values()));break
            except (NodeNotReady, LayoutNotReady):
                require(time.monotonic() < deadline, 'actual OS WiFi provider UI not ready')
                time.sleep(.25)
        x,y,w,h = node['rect']
        ams = shell('aa dump -a -u 100', 'actual_provider_before_click')['stdout_ref']
        provider_bms = shell(shlex.join(['bm', 'dump', '-n', node['bundle'], '-u', '100']), 'actual_UI_provider_bms')['stdout_ref']
        io.ui.shell('uitest uiInput click ' + str(x+w//2) + ' ' + str(y+h//2), 'apps579_wifi_actual_provider_click')
        return result(mark, selected_node=node, layout=save('control_layout.json', json.dumps(layout)), original_layout=str(path),
            frame=io.frame('apps579_wifi_after_click'), provider_ams=ams, provider_bms=provider_bms)

    def cleanup():
        if state['closed']:
            return {'already_closed': True, 'boot_id': io.boot_id, 'failures': []}
        mark = begin('cleanup');failures = [];base_result = None
        try:
            # Stops/restores actual OS WiFi/AP before returning the spare phy.
            base_result = base['cleanup']();require(not base_result.get('failures'), 'original public WiFi caller restoration failed')
            stop_peer()
            if state['mounted']:
                helper('config-unmount');state['mounted'] = False
                restored = shell('sha256sum /system/etc/netdetectionurl.conf', 'restored_probe_bytes')
                require(restored['stdout'].strip() == state['probe_before'], 'original OS probe config not restored')
            if state['moved']:
                helper('return', state['namespace_pid'], state['phy']);state['moved'] = False
                helper('restore')
            if state['namespace']:
                io.write_stdin(state['namespace'], ('QUIT ' + run + '\n').encode())
                done = io.wait(state['namespace'], timeout=30);require(done['exit_code'] == 0 and not done['timed_out'], 'actual namespace holder did not finish')
                state['namespace'] = None
            if state['created']:
                files, events = journals()
                listing = shell('find ' + remote + ' -type f', 'owned_fixture_files')
                for filename in listing['stdout'].splitlines():
                    require(re.fullmatch(re.escape(remote) + r'/(?:wifi_peer|[a-z-]+-[1-9][0-9]*\.jsonl|(?:ap|sta|probe)\.conf|namespace\.txt|dhcp-client\.txt|(?:ap|sta)-ready)', filename), 'refuse unrelated fixture file cleanup')
                    shell('rm ' + shlex.quote(filename), 'remove_owned_fixture_file')
                shell('rmdir ' + remote + '/control\nrmdir ' + remote, 'remove_owned_fixture_directory')
            state['closed'] = True
        except Exception as error:
            failures.append({'type': type(error).__name__, 'error': str(error)})
        return result(mark, base_cleanup=base_result, failures=failures, restored=not failures)

    io.register_cleanup(cleanup)
    return dict(base, network=network, input=input, cleanup=cleanup)
