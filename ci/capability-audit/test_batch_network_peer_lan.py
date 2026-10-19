"""Light host candidate tests. QEMU argv doubles are never guest evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from batch_network375_root_entry import RootExecutor, AdmissionError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('peer_lan', Path(__file__).with_name('batch_network_peer_lan.py'))
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)


def unit_owner(qemu):
    """Explicit host double; never production owner/VM/HDC evidence."""
    owner = Mock(spec=RootExecutor)
    def run(argv, *, timeout, label, start_new_session=True):
        if Path(argv[0]).resolve() != Path(qemu).resolve() or Path(qemu).name != 'fixture-qemu':
            raise AssertionError('unit owner refuses every real resource executable')
        return subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    owner.run.side_effect = run
    return owner


def prepare_unit(args):
    # Port availability, like the root resource admission, is a host mock here.
    # No actual listener or unreserved application port is touched by a test.
    with patch.object(peer.socket, 'socket'):
        return peer.prepare(args, owner=unit_owner(args.qemu))


def fixture(root, product='arm64_virt', binary='qemu-system-aarch64', *, stream=True, mac='52:54:00:11:22:33'):
    package = root / 'package'
    (package / 'launch').mkdir(parents=True)
    (package / 'images').mkdir()
    (package / 'manifest.json').write_text(json.dumps(dict(product=product, guest_arch='arm64',
        device_type_profile='qemu_phone_full_source', capabilities=dict(absolute_pointer_sync=True))))
    launcher = package / 'launch/qemu_run.sh'
    base = ('#!/bin/bash\nOHOS_IMG="out/' + product + '/packages/phone/images"\n'
        'DISPLAY_TYPE="${QEMU_DISPLAY:-none}"\nHDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"\n'
        'NET_ARGS=(-netdev user,id=net0,hostfwd=tcp::${HDC_HOST_PORT}-:5555 '
        '-device virtio-net-pci,netdev=net0,mac=' + mac + ')\n'
        'case "${DISPLAY_TYPE}" in\nnone) DISPLAY_ARGS="-device virtio-gpu-pci -display none -monitor none" ;;\n'
        'vnc) DISPLAY_ARGS="-device virtio-gpu-pci -vnc :21" ;;\nesac\n')
    suffix = ' -cpu max -smp 4 -m 4096 -device virtio-mouse-pci ${DISPLAY_ARGS} '
    append = 'oemmode=rd sn=0023456789 init=/init ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev@wait'
    if product == 'x86_64_virt':
        base += 'exec ' + binary + suffix + '"${NET_ARGS[@]}" -append "' + append + '"\n'
    else:
        base += 'QEMU_CMD="' + binary + suffix + '${NET_ARGS[*]} -append \\"' + append + '\\""\neval "$QEMU_CMD"\n'
    launcher.write_text(base);launcher.chmod(0o700)
    for name in ('userdata.img', 'system.img', 'vendor.img', 'ramdisk.img'):
        (package / 'images' / name).write_bytes(('private-host-fixture-' + name).encode())
    rewrite = ['bash', str(ROOT / 'scripts/package_standard_qemu.sh'), '--rewrite-package', str(package)]
    result = subprocess.run(rewrite, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    normalized = launcher.read_bytes()
    subprocess.run(rewrite, check=True, capture_output=True)
    if launcher.read_bytes() != normalized:
        raise AssertionError('peer launcher rewrite is not idempotent')
    qemu = root / 'fixture-qemu'
    qemu.write_text('#!' + sys.executable + '\nimport json,sys\n'
        'if "-netdev" in sys.argv and sys.argv[-1]=="help":\n'
        ' print("Available netdev backend types:\\nuser' + ('\\nstream' if stream else '') + '")\n'
        'elif "--version" in sys.argv: print("HOST ARGUMENT DOUBLE, NO VM")\n'
        'else: print(json.dumps(sys.argv[1:]))\n')
    qemu.chmod(0o700)
    return package, qemu


def environment(qemu, **extra):
    value = {key: item for key, item in os.environ.items() if not key.startswith('QEMU_')}
    value.update(QEMU_BIN=str(qemu), QEMU_ACCEL='tcg', QEMU_DISPLAY='none', **extra)
    return value


def peer_environment():
    return dict(QEMU_PEER_MODE='listen', QEMU_PEER_PORT='24680', QEMU_PEER_MAC='02:00:00:00:10:02',
        QEMU_MGMT_MAC='02:00:00:00:10:01', QEMU_INSTANCE_UUID='11111111-2222-4333-8444-555555555555',
        QEMU_GUEST_SERIAL='unique-boot-serial')


class PeerLanTests(unittest.TestCase):
    def test_three_product_real_generated_arguments_default_and_two_stream_endpoints(self):
        for product, binary in [('arm64_virt', 'qemu-system-aarch64'), ('armv7a_virt', 'qemu-system-arm'),
                                ('x86_64_virt', 'qemu-system-x86_64')]:
            with self.subTest(product=product), tempfile.TemporaryDirectory() as temporary:
                package, qemu = fixture(Path(temporary), product, binary)
                command = ['bash', str(package / 'launch/linux.sh')]
                result = subprocess.run(command, env=environment(qemu), capture_output=True, text=True, check=True)
                arguments = json.loads(result.stdout.splitlines()[-1])
                self.assertEqual(sum(value.startswith('user,id=') for value in arguments), 1)
                self.assertFalse(any(value.startswith('stream,') for value in arguments))
                self.assertIn('virtio-net-pci,netdev=net0,mac=52:54:00:11:22:33', arguments)
                self.assertIn('sn=0023456789', arguments[arguments.index('-append') + 1])
                for role, mode, port in [('listener', 'listen', '5558'), ('connector', 'connect', '5559')]:
                    current = peer_environment();current.update(QEMU_PEER_MODE=mode, QEMU_HDC_HOST_PORT=port)
                    result = subprocess.run(command, env=environment(qemu, **current), capture_output=True, text=True, check=True)
                    arguments = json.loads(result.stdout.splitlines()[-1])
                    data = [value for value in arguments if value.startswith('stream,')]
                    self.assertEqual(len(data), 1)
                    self.assertIn('addr.host=127.0.0.1,addr.port=24680', data[0])
                    self.assertIn('server=on' if mode == 'listen' else 'server=off,reconnect-ms=250', data[0])
                    self.assertIn('virtio-net-pci,id=peer_lan_nic,netdev=peer_lan,mac=' + current['QEMU_PEER_MAC'], arguments)
                    self.assertIn('virtio-net-pci,netdev=net0,mac=' + current['QEMU_MGMT_MAC'], arguments)
                    self.assertIn('hostfwd=tcp::' + port + '-:5555', next(v for v in arguments if v.startswith('user,')))
                    self.assertIn('sn=unique-boot-serial', arguments[arguments.index('-append') + 1])
                    self.assertEqual(arguments[arguments.index('-uuid') + 1], current['QEMU_INSTANCE_UUID'])
                # Direct qemu_run users need the resource default initialized
                # before the peer backend help query, without wrapper exports.
                (Path(temporary) / binary).symlink_to(qemu)
                direct = environment(qemu, **peer_environment())
                del direct['QEMU_BIN']
                direct['PATH'] = temporary + os.pathsep + direct['PATH']
                result = subprocess.run(['bash', str(package / 'launch/qemu_run.sh')],
                    env=direct, capture_output=True, text=True, check=True)
                self.assertTrue(any(item.startswith('stream,') for item in json.loads(result.stdout.splitlines()[-1])))

    def test_default_without_peer_preserves_existing_global_management_mac(self):
        with tempfile.TemporaryDirectory() as temporary:
            mac = '00:11:22:33:44:55'
            package, qemu = fixture(Path(temporary), mac=mac)
            result = subprocess.run(['bash', str(package / 'launch/linux.sh')],
                env=environment(qemu), capture_output=True, text=True, check=True)
            arguments = json.loads(result.stdout.splitlines()[-1])
            self.assertIn('virtio-net-pci,netdev=net0,mac=' + mac, arguments)
            self.assertFalse(any(item.startswith('stream,') for item in arguments))

    def test_bad_peer_configuration_refuses_before_qemu_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, qemu = fixture(Path(temporary))
            base = peer_environment()
            dangling = Path(temporary) / 'dangling.pcap'
            dangling.symlink_to(Path(temporary) / 'not-created-target')
            invalid = [('QEMU_PEER_MODE', 'tap'), ('QEMU_PEER_PORT', '0'), ('QEMU_PEER_PORT', '65536'),
                ('QEMU_PEER_PORT', '5555'), ('QEMU_PEER_PORT', '42;exit 0'), ('QEMU_PEER_MAC', '03:00:00:00:10:02'),
                ('QEMU_PEER_MAC', base['QEMU_MGMT_MAC']), ('QEMU_MGMT_MAC', '00:00:00:00:10:01'),
                ('QEMU_INSTANCE_UUID', 'bogus'), ('QEMU_GUEST_SERIAL', 'sn$(touch /tmp/never)'),
                ('QEMU_PEER_CAPTURE_FILE', '/tmp/capture;exit'), ('QEMU_PEER_CAPTURE_FILE', str(dangling)),
                ('QEMU_EXTRA_ARGS', '-uuid other')]
            for key, item in invalid:
                with self.subTest(key=key, item=item):
                    result = subprocess.run(['bash', str(package / 'launch/linux.sh')],
                        env=environment(qemu, **dict(base, **{key: item})), capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(result.stdout, '')

    def test_missing_stream_backend_is_explicit_failure_not_nat_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            package, qemu = fixture(Path(temporary), stream=False)
            result = subprocess.run(['bash', str(package / 'launch/linux.sh')],
                env=environment(qemu, **peer_environment()), capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('does not advertise the stream', result.stderr)

    def test_plan_unique_ports_macs_qmp_serial_uuid_and_private_subnet(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);package, qemu = fixture(root)
            value = peer.make_plan(package, root / 'independent', qemu=qemu)
            actors = list(value['instances'].values())
            for key in ('target', 'qmp_socket', 'management_mac', 'peer_mac'):
                self.assertNotEqual(actors[0][key], actors[1][key])
            for key in ('QEMU_INSTANCE_UUID', 'QEMU_GUEST_SERIAL'):
                self.assertNotEqual(actors[0]['environment'][key], actors[1]['environment'][key])
            self.assertEqual({actor['address'] for actor in actors}, {'172.27.77.1', '172.27.77.2'})
            self.assertFalse(value['first_artifact_behavior_gate_passed'])
            for kwargs in [dict(peer_port=5558), dict(hdc_port=65535), dict(vnc_display=59635),
                           dict(vnc_display=-1), dict(network='192.0.0.0/30'), dict(network='10.0.2.0/30'),
                           dict(network='172.27.77.0/24'), dict(network='8.8.8.0/30')]:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    peer.make_plan(package, root / 'other', qemu=qemu, **kwargs)

    def test_prepare_clones_real_independent_inodes_and_never_boots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);package, qemu = fixture(root)
            archive = root / 'candidate.tar.gz'
            with tarfile.open(archive, 'w:gz') as target:
                target.add(package, arcname=package.name)
            args = SimpleNamespace(package=package, qemu=qemu, output=root / 'private', archive=archive,
                hdc_port=47580, vnc_display=4021, peer_port=47590, subnet='172.27.77.0/30')
            result = prepare_unit(args)
            self.addCleanup(shutil.rmtree, result['control_directory'])
            self.assertEqual(result['status'], 'prepared_candidate_not_booted')
            listener = Path(result['instances']['listener']['path']) / 'images/userdata.img'
            connector = Path(result['instances']['connector']['path']) / 'images/userdata.img'
            original = package / 'images/userdata.img'
            self.assertFalse(os.path.samefile(listener, connector))
            self.assertFalse(os.path.samefile(listener, original))
            before = original.read_bytes()
            listener.write_bytes(b'one actual private host fixture disk mutation')
            self.assertEqual(connector.read_bytes(), before)
            self.assertEqual(original.read_bytes(), before)
            self.assertFalse(any(Path(actor['qmp_socket']).exists() for actor in result['instances'].values()))
            self.assertEqual(result['commands'], [])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])
            self.assertIn('open:', result['service_validation'])
            peer.validate_staging(result)
            connector.unlink()
            os.link(listener, connector)
            with self.assertRaisesRegex(ValueError, 'disk identity changed or became shared'):
                peer.validate_staging(result)

    def test_archive_binding_rejects_mutation_and_linked_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);package, _ = fixture(root)
            files, _ = peer.inventory(package)
            sources = {str(p.relative_to(package)): dict(bytes=p.stat().st_size, sha256=peer.sha(p)) for p in files}
            archive = root / 'candidate.tar'
            with tarfile.open(archive, 'w') as target:
                target.add(package, arcname=package.name)
            peer.bind_archive(archive, sources)
            sources['images/userdata.img']['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                peer.bind_archive(archive, sources)
            (package / 'images/shared.img').symlink_to(package / 'images/userdata.img')
            with self.assertRaisesRegex(ValueError, 'linked or special'):
                peer.inventory(package)

    def test_observation_timeout_preserves_actual_partial_transport_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);package, qemu = fixture(root)
            archive = root / 'candidate.tar.gz'
            with tarfile.open(archive, 'w:gz') as target:
                target.add(package, arcname=package.name)
            args = SimpleNamespace(package=package, qemu=qemu, output=root / 'private', archive=archive,
                hdc_port=47580, vnc_display=4021, peer_port=47590, subnet='172.27.77.0/30')
            plan = prepare_unit(args)
            self.addCleanup(shutil.rmtree, plan['control_directory'])
            observe = SimpleNamespace(plan=args.output / 'peer-lan.json', output=root / 'observation',
                                      hdc=Path('/unexecuted-host-double-hdc'), configure=True)
            error = subprocess.TimeoutExpired(['host-double'], 30, output=b'actual partial byte fixture', stderr=b'partial stderr')
            owner = unit_owner(qemu)
            owner.run.side_effect = error
            evidence = peer.observe(observe, owner=owner)
            self.assertEqual(evidence['status'], 'fail')
            self.assertFalse(evidence['first_artifact_behavior_gate_passed'])
            self.assertTrue(evidence['commands'][0]['timed_out'])
            self.assertEqual(Path(evidence['commands'][0]['stdout_path']).read_bytes(), b'actual partial byte fixture')
            self.assertEqual(Path(evidence['commands'][0]['stderr_path']).read_bytes(), b'partial stderr')
            owner.run.assert_called_once()
            self.assertIn('ip -o link show', owner.run.call_args.args[0][-1])

    def test_actual_identity_requires_both_nics_and_two_different_udids_and_boots(self):
        actor = dict(peer_mac='02:00:00:00:01:02', management_mac='02:00:00:00:01:01')
        links = '2: eth0: <UP> mtu 1500 link/ether 02:00:00:00:01:01 brd ff:ff:ff:ff:ff:ff\n' + \
                '3: eth1: <UP> mtu 1500 link/ether 02:00:00:00:01:02 brd ff:ff:ff:ff:ff:ff'
        first = peer.identity('udid of current device is :\n' + 'a' * 64,
            '11111111-2222-4333-8444-555555555555', links, actor)
        second = dict(first, udid='b' * 64, boot_id='22222222-2222-4333-8444-555555555555')
        peer.validate_pair(dict(listener=first, connector=second))
        for key in ('udid', 'boot_id'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                peer.validate_pair(dict(listener=first, connector=dict(second, **{key: first[key]})))
        for udid, boot, actual_links in [('configured-uuid-is-not-UDID', first['boot_id'], links),
                                        ('udid of current device is :\n' + 'a' * 64, first['boot_id'], links.splitlines()[0])]:
            with self.assertRaises(ValueError):
                peer.identity(udid, boot, actual_links, actor)

    def test_static_config_is_peer_only_and_routes_reject_management_nat(self):
        actor = dict(address='172.27.77.1', peer_address='172.27.77.2', peer_mac='02:00:00:00:01:02')
        script = peer.configure_script(actor, 'eth1')
        self.assertIn('ip addr add 172.27.77.1/30 dev eth1', script)
        self.assertNotIn('flush', script)
        self.assertNotIn('default', script)
        self.assertNotIn('eth0', script)
        peer.route_check('172.27.77.2 dev eth1 src 172.27.77.1 uid 0\n cache', actor, 'eth1')
        for route in ('', '172.27.77.2 via 10.0.2.2 dev eth0 src 10.0.2.15',
                      '172.27.77.2 dev eth0 src 172.27.77.1', '172.27.77.2 dev eth1 src 10.0.2.15',
                      '172.27.77.2 dev eth1 src'):
            with self.subTest(route=route), self.assertRaises(ValueError):
                peer.route_check(route, actor, 'eth1')
        with self.assertRaises(ValueError):
            peer.configure_script(actor, 'eth1;exit 0')


if __name__ == '__main__':
    unittest.main()
