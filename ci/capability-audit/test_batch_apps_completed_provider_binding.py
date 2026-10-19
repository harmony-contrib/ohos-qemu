"""Self-contained provider parser regressions; no process or runtime acceptance.

Files are temporary. Native-tail models exercise the exact production AST after
source admission, not a source/build positive. Export tests stub only the native
identity dependency and prove the finite export parser locally. No positive
model enters verify_completed_provider or native_completion.
"""
import ast
import copy
import inspect
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest import mock

import batch_apps_completed_provider_binding as binding
import batch_apps_production_provider_binding as dispatch


class FileModel(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.rows = []

    def file(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def row(self, argv, *, native=False, code=0, out=b'', err=b'', label='model'):
        index = len(self.rows)
        row = dict(argv=list(argv), exit_code=code, timed_out=False, label=label)
        for stream, raw in (('stdout', out), ('stderr', err)):
            key = stream if native else stream + '_record'
            row[key] = binding.record(self.file(f'raw/{index}.{stream}', raw))
        self.rows.append(row)
        return row

    def absence(self, subject, *, native=False, label='model'):
        return self.row(['docker', 'inspect', subject], native=native, label=label,
                        code=1, out=b'[]', err=('Error: No such object: ' + subject).encode())

    def alter_stdout(self, row, change, *, native=False):
        key = 'stdout' if native else 'stdout_record'
        path = Path(row[key]['path'])
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))
        row[key] = binding.record(path)


class PublicRejectionTests(FileModel):
    def test_unknown_kind_and_incomplete_schema_do_not_fall_back(self):
        cases = [dict(kind='unreviewed'), dict(kind=binding.KIND),
                 dict.fromkeys(binding.FIELDS, None)]
        cases[-1].update(kind=binding.KIND, schema_version=True)
        with mock.patch.object(dispatch, 'verify_historical_provider', side_effect=AssertionError('legacy fallback')):
            for config in cases:
                with self.subTest(config=config), self.assertRaises(ValueError):
                    dispatch.verify_production_provider(config, provider_name='contacts',
                        device='phone', signed_hap='unused', system_image_sha256='a' * 64)

    def test_outer_zero_footer_and_closure_flags_are_not_native_execution(self):
        archive = self.file('model.archive', b'not a package')
        launcher = self.file('launcher.log', (
            'Build args: --product-name arm64_virt --device-type phone --build-target images --build-only-load=false\n'
            '[OHOS INFO] arm64_virt build success\n[OHOS INFO] Cost Time: 1:00:00\n').encode())
        value = dict(schema='F-representative-owner/v17', source_commit='c' * 40, exit_code=0,
            owned_container_absent=True, owned_launcher_group_closed=True, cleanup_verified=True,
            resource_lease_held=False, owned_resources_closed_while_lease_held=True,
            resource_lease_release_authorized=True, resource_lease_released_after_verified_closure=True,
            launcher_log=binding.record(launcher), package=binding.record(archive), tree_sha256='e' * 64,
            adopted_complete_host_environment={'PREPARE_ONLY': '0', 'BUILD_ONLY_LOAD': '0'})
        evidence = self.file('evidence.json', json.dumps(value).encode())
        with self.assertRaises(ValueError):
            binding.native_completion(binding.record(evidence), binding.record(launcher), 'c' * 40, archive, 'e' * 64)


class NativeTailParserTests(FileModel):
    """Exact local parser statements; pinned source/CLI admission is out of scope."""
    @classmethod
    def setUpClass(cls):
        function = ast.parse(textwrap.dedent(inspect.getsource(binding.native376_resources))).body[0]
        start = next(i for i, node in enumerate(function.body) if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'rows' for t in node.targets))
        function.name = 'native_tail_model'
        function.args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in
            ('value', 'cid', 'cfg', 'host', 'mounts', 'endpoint_env')], kwonlyargs=[], kw_defaults=[], defaults=[])
        function.body = function.body[start:]
        namespace = dict(binding.__dict__)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                     '<production-native-tail>', 'exec'), namespace)
        cls.tail = staticmethod(namespace['native_tail_model'])

    def setUp(self):
        super().setUp()
        self.cid, self.pid = 'd' * 64, 600
        self.cfg = dict(Cmd=['model-observer'], Env=['MODEL=1'], User='root', Entrypoint=None,
                        WorkingDir='/work', Labels={}, Image=binding.NATIVE376_IMAGE)
        self.host = dict(ReadonlyRootfs=False, NetworkMode='bridge', Privileged=False)
        self.mounts = {path: dict(Type='volume', Name=name, Source='/model/' + name, Driver='local', RW=True)
                       for path, name in ((binding.SOURCE, 'source'), (binding.SOURCE + '/out', 'out'))}
        observation = dict(Id=self.cid, Name='/' + binding.NATIVE376_NAME, Image=binding.NATIVE376_IMAGE,
            Config=self.cfg, HostConfig=self.host,
            Mounts=[dict(row, Destination=dest) for dest, row in self.mounts.items()],
            State=dict(Status='running', Running=True, Paused=False, Restarting=False,
                       OOMKilled=False, Dead=False, Error='', ExitCode=0))
        self.row(['docker', 'context', 'show'], native=True, out=b'model')
        self.row(['docker', 'context', 'inspect', 'model', '--format', '{{json .Endpoints.docker.Host}}'],
                 native=True, out=b'"unix:///model.sock"')
        self.absence(binding.NATIVE376_NAME, native=True, label='before-build-name')
        self.adoption = self.row(['docker', 'inspect', binding.NATIVE376_NAME], native=True,
                                label='discover-build-4', out=json.dumps([observation]).encode())
        self.ps = self.row(['ps', '-axo', 'pid=,pgid=,stat='], native=True,
                           label='owned-group-members', out=b'600 600 Z\n')
        self.absence(self.cid, native=True, label='cleanup-discover')
        for index in (1, 2):
            self.absence(binding.NATIVE376_NAME, native=True, label=f'cleanup-name-absence-{index}')
        self.value = dict(commands=self.rows, actual_local_docker_endpoint='unix:///model.sock',
            launcher_pid=self.pid, owned_launcher_pgid=self.pid, launcher_start_new_session=True,
            spawn_mask_restored_in_child=True, foreground_creator_completed_normally_before_forced_stop=True,
            launcher_wnowait_exit=dict(pid=self.pid, si_code=1, si_status=0, exit_code=0, reaped=False,
                                      observed_monotonic_ns=110),
            leader_final_wait_completed=True, owned_launcher_leader_reaped=True,
            actual_launcher_exit_code_after_cleanup=0, cleanup_started_monotonic_ns=100,
            registered_group_cuts=[dict(monotonic_ns=120, members=[dict(pid=600, pgid=600, state='Z')])],
            last_group_signal_boundary_monotonic_ns=130)

    def parse(self):
        return self.tail(self.value, self.cid, self.cfg, self.host, self.mounts, {})

    def test_latest_wnowait_is_inside_cleanup_before_ps_and_boundary(self):
        self.assertEqual(self.cid, self.parse()['container_id'])
        for field in ('cleanup_started_monotonic_ns', 'last_group_signal_boundary_monotonic_ns'):
            self.value[field] = 110
        self.value['registered_group_cuts'][0]['monotonic_ns'] = 110
        self.assertEqual(self.cid, self.parse()['container_id'])  # equal clock resolution remains legal

    def test_old_reversed_clock_and_every_missing_or_noninteger_clock_reject(self):
        baseline = copy.deepcopy(self.value)
        targets = [(self.value, 'cleanup_started_monotonic_ns'),
                   (self.value['launcher_wnowait_exit'], 'observed_monotonic_ns'),
                   (self.value['registered_group_cuts'][0], 'monotonic_ns'),
                   (self.value, 'last_group_signal_boundary_monotonic_ns')]
        invalids = [(111, True, '100', None), (99, 121, True, '110', None),
                    (109, 131, True, '120', None), (119, True, '130', None)]
        for (container, key), values in zip(targets, invalids):
            original = container[key]
            for invalid in values:
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    container[key] = invalid
                    self.parse()
            container.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): self.parse()
            container[key] = original
        self.assertEqual(baseline, self.value)

    def test_intermediate_ps_order_and_first_ps_join_cannot_be_hidden_by_final_cut(self):
        members = copy.deepcopy(self.value['registered_group_cuts'][0]['members'])
        row = self.row(['ps', '-axo', 'pid=,pgid=,stat='], native=True,
                       label='owned-group-members', out=b'600 600 Z\n')
        self.rows.pop(); self.rows.insert(5, row)
        self.value['registered_group_cuts'].append(dict(monotonic_ns=125, members=members))
        self.assertEqual(self.cid, self.parse()['container_id'])
        self.value['registered_group_cuts'][1]['monotonic_ns'] = 119
        with self.assertRaises(ValueError): self.parse()
        self.value['registered_group_cuts'][1]['monotonic_ns'] = 125
        self.value['launcher_wnowait_exit']['observed_monotonic_ns'] = 121
        with self.assertRaises(ValueError): self.parse()

    def test_unknown_foreign_commands_and_missing_closure_cuts_reject(self):
        baseline = list(self.rows)
        for index in range(len(baseline) + 1):
            row = self.row(['docker', 'run', '-d', 'foreign', 'sleep', '3600'], native=True)
            self.rows.pop(); self.rows.insert(index, row)
            with self.subTest(index=index), self.assertRaises((ValueError, IndexError)): self.parse()
            self.rows[:] = baseline
        self.rows.pop()
        with self.assertRaises((ValueError, IndexError)): self.parse()

    def test_raw_ps_members_and_held_wnowait_are_required(self):
        self.value['launcher_wnowait_exit']['reaped'] = True
        with self.assertRaises(ValueError): self.parse()
        self.value['launcher_wnowait_exit']['reaped'] = False
        self.value['registered_group_cuts'][0]['members'] = []
        with self.assertRaises(ValueError): self.parse()
        self.value['registered_group_cuts'][0]['members'] = [dict(pid=600, pgid=600, state='Z'), dict(pid=601, pgid=600, state='S')]
        path = Path(self.ps['stdout']['path']); path.write_bytes(b'600 600 Z\n601 600 S\n')
        self.ps['stdout'] = binding.record(path)
        with self.assertRaises(ValueError): self.parse()

    def test_complete_actual_config_hostconfig_and_mounts_must_match(self):
        original = Path(self.adoption['stdout']['path']).read_bytes()
        changes = [lambda o: o['Config'].update(Cmd=['unrelated']),
                   lambda o: o['Config'].update(Entrypoint=['sh']),
                   lambda o: o['HostConfig'].update(ReadonlyRootfs=True),
                   lambda o: o['HostConfig'].update(NetworkMode='none'),
                   lambda o: o['HostConfig'].update(Privileged=True),
                   lambda o: o['HostConfig'].update(UnknownField=True),
                   lambda o: o['Mounts'][0].update(Source='/other-volume'),
                   lambda o: o['Mounts'].append(dict(Type='volume', Name='source', Source='/model/source', Driver='local', Destination='/rw-alias', RW=True))]
        for index, change in enumerate(changes):
            self.alter_stdout(self.adoption, lambda values: change(values[0]), native=True)
            with self.subTest(index=index), self.assertRaises(ValueError): self.parse()
            path = Path(self.adoption['stdout']['path']); path.write_bytes(original)
            self.adoption['stdout'] = binding.record(path)


class ExportJournalParserTests(FileModel):
    """Local export parser only: native identity is an explicit bounded stub."""
    def setUp(self):
        super().setUp()
        self.output = self.root / 'export'; self.output.mkdir()
        self.owner, self.cid, self.commit = 'a' * 32, 'd' * 64, 'c' * 40
        self.name = 'ohos-F-provider-export46-' + self.owner
        exporter = self.file('source/exporter.py', b'inert model source')
        native = self.file('native/evidence.json', b'{}')
        launcher = self.file('native/launcher.log', b'not a native build')
        exports = self.file('export/public-source/exports.json', b'{"files":[]}')
        receipt = self.file('export/receipt.json', b'{}')
        self.config = dict(qa_root=str(self.root), expected_source_commit=self.commit,
            producer_sources={'exporter': binding.record(exporter)}, native_launcher_log=binding.record(launcher),
            export_receipt=binding.record(receipt))
        self.paths = dict(native_evidence=native, exports=exports)
        self.identity = dict(endpoint='unix:///model.sock', volumes={dest: dict(Type='volume', Name=name,
            Source='/model/' + name, Driver='local', RW=True) for dest, name in
            ((binding.SOURCE, 'source'), (binding.SOURCE + '/out', 'out'))})
        self.mounts = {dest: dict(Type='volume', Name=m['Name'], RW=False) for dest, m in self.identity['volumes'].items()}
        self.mounts.update({'/work': dict(Type='bind', Source=str(self.root), RW=False),
            str(self.output): dict(Type='bind', Source=str(self.output), RW=True),
            str(exporter.parent): dict(Type='bind', Source=str(exporter.parent), RW=False),
            str(native): dict(Type='bind', Source=str(native), RW=False)})
        cidfile = self.file('export/container.cid', self.cid.encode())
        self.command = ['python3', str(exporter), '--source-root', binding.SOURCE, '--native-evidence', str(native),
                        '--output', str(exports.parent), '--public-input', 'vendor/ohemu/virt/virt_phone_full.meta.json']
        self.entry = dict(name=self.name, id=self.cid, owner=self.owner, commit=self.commit, image=binding.NATIVE376_IMAGE,
            mounts=self.mounts, command=self.command, cidfile=str(cidfile), absent=True, create_attempted=True, create_outcome='known_created')
        self.create = ['docker', 'create', '--name', self.name, '--cidfile', str(cidfile), '--label', 'ohos-qemu.root-run=' + self.owner,
            '--label', 'ohos-qemu.source-commit=' + self.commit, '--platform', 'linux/amd64', '--read-only', '--cpus', '1',
            '--memory', '512m', '--pids-limit', '64', '--network', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=512m']
        for dest, m in self.mounts.items():
            self.create += ['--mount', 'type=' + m['Type'] + ',src=' + m.get('Name', m.get('Source')) + ',dst=' + dest + (',readonly' if not m['RW'] else '')]
        self.create += [binding.NATIVE376_IMAGE, *self.command]
        cfg = dict(binding.ENGINE376['config'], Hostname=self.cid[:12], Cmd=self.command, Env=['MODEL=1'], WorkingDir='',
                   Labels={'ohos-qemu.root-run': self.owner, 'ohos-qemu.source-commit': self.commit})
        host = dict(binding.ENGINE376['host'], AutoRemove=False, ContainerIDFile=str(cidfile), ReadonlyRootfs=True, NetworkMode='none',
            CapDrop=['ALL'], SecurityOpt=['no-new-privileges'], PidsLimit=64, Memory=512 * 1024**2, MemorySwap=1024**3,
            NanoCpus=10**9, Tmpfs={'/tmp': 'rw,exec,nosuid,nodev,size=512m'}, Binds=None, Mounts=binding.host_mount_options(self.mounts))
        observed_mounts = [dict(m, Destination=dest, **({k: self.identity['volumes'][dest][k] for k in ('Source', 'Driver')}
                           if dest in self.identity['volumes'] else {})) for dest, m in self.mounts.items()]
        observation = dict(Id=self.cid, Name='/' + self.name, Image=binding.NATIVE376_IMAGE, Config=cfg, HostConfig=host,
            Mounts=observed_mounts, State=dict(Status='created', Running=False, Paused=False, Restarting=False, OOMKilled=False, Dead=False, Error='', ExitCode=0))
        self.row(['docker', 'context', 'show'], out=b'model')
        self.row(['docker', 'context', 'inspect', 'model', '--format', '{{json .Endpoints.docker.Host}}'], out=b'"unix:///model.sock"')
        self.row(['docker', 'image', 'inspect', binding.NATIVE376_IMAGE], out=json.dumps([dict(Id=binding.NATIVE376_IMAGE,
            Config=dict(Env=['MODEL=1'], Labels={}, User='root', WorkingDir='', Entrypoint=None))]).encode())
        def git():
            self.row(['git', '-C', str(self.root), 'rev-parse', 'HEAD'], out=self.commit.encode())
            self.row(['git', '-C', str(self.root), 'status', '--short'])
        def inspect_cut(status):
            value = copy.deepcopy(observation); value['State']['Status'] = status
            self.row(['docker', 'inspect', self.cid], out=json.dumps([value]).encode())
        git(); self.absence(self.name); self.row(self.create, out=self.cid.encode())
        inspect_cut('created'); inspect_cut('created')
        self.row(['docker', 'start', '-a', self.cid], out=json.dumps(dict(exit_code=0, private_key_bytes_read=False, compiler_executed=False)).encode())
        inspect_cut('exited'); git(); inspect_cut('exited'); inspect_cut('exited')
        self.row(['docker', 'rm', self.cid], out=self.cid.encode()); self.absence(self.cid); self.absence(self.name)
        self.row(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'label=ohos-qemu.root-run=' + self.owner])
        self.ledger = dict(schema='owned-resource35/v1', owner_uuid=self.owner, phase='closed', failed=False, cleanup_verified=True,
            errors=[], signals=[], quarantine_attempts=[], commands=self.rows, containers=[self.entry], output=str(self.output))
        self.receipt = dict(commands=self.rows, container_id=self.cid, run_id=self.owner,
                            docker_endpoint_environment={}, actual_local_docker_endpoint=self.identity['endpoint'])

    def parse(self):
        path = self.file('export/resources.json', json.dumps(self.ledger).encode())
        self.receipt['resource_ledger'] = binding.record(path)
        with mock.patch.object(binding, 'native376_resources', return_value=self.identity):
            return binding.export379_resources(self.config, self.paths, {'tree_sha256': 'e' * 64}, self.receipt)

    def test_only_local_export_model_is_valid_and_unknown_resource_commands_reject(self):
        self.assertFalse(self.parse()['compiler_executed'])
        baseline = list(self.rows)
        for index in range(len(baseline) + 1):
            row = self.row(['docker', 'run', '-d', '--name', 'foreign', 'model', 'sleep', '3600'])
            self.rows.pop(); self.rows.insert(index, row)
            with self.subTest(index=index), self.assertRaises((ValueError, IndexError)): self.parse()
            self.rows[:] = baseline

    def test_create_without_mounts_and_missing_post_start_inspection_reject(self):
        create = next(r for r in self.rows if r['argv'][1] == 'create')
        original = list(create['argv']); index = create['argv'].index('--mount'); del create['argv'][index:index + 2]
        with self.assertRaises(ValueError): self.parse()
        create['argv'] = original
        index = next(i for i, r in enumerate(self.rows) if r['argv'] == ['docker', 'start', '-a', self.cid])
        self.rows.pop(index + 1)
        with self.assertRaises(ValueError): self.parse()

    def test_same_volume_name_with_foreign_source_or_endpoint_is_not_native_join(self):
        row = next(r for r in self.rows if r['argv'] == ['docker', 'inspect', self.cid])
        self.alter_stdout(row, lambda values: values[0]['Mounts'][0].update(Source='/foreign-volume'))
        with self.assertRaises(ValueError): self.parse()
        self.identity['endpoint'] = 'unix:///other.sock'
        with self.assertRaises(ValueError): self.parse()

    def test_plan_argv_and_actual_mount_cannot_all_switch_to_an_unrelated_volume(self):
        self.entry['mounts'][binding.SOURCE]['Name'] = 'unrelated-source'
        create = next(r for r in self.rows if r['argv'][1] == 'create')
        create['argv'] = [v.replace('src=source,', 'src=unrelated-source,') for v in create['argv']]
        for row in self.rows:
            if row['argv'] == ['docker', 'inspect', self.cid] and row['exit_code'] == 0:
                def change(values):
                    values[0]['Mounts'][0].update(Name='unrelated-source', Source='/model/unrelated-source')
                    values[0]['HostConfig']['Mounts'][0]['Source'] = 'unrelated-source'
                self.alter_stdout(row, change)
        with self.assertRaisesRegex(ValueError, 'join actual native source/out'):
            self.parse()

    def test_writable_rootfs_bridge_network_cmd_substitution_and_alias_reject(self):
        row = next(r for r in self.rows if r['argv'] == ['docker', 'inspect', self.cid])
        original = Path(row['stdout_record']['path']).read_bytes()
        changes = [lambda o: o['HostConfig'].update(ReadonlyRootfs=False),
                   lambda o: o['HostConfig'].update(NetworkMode='bridge'),
                   lambda o: o['Config'].update(Cmd=['sh', '-c', 'unrelated']),
                   lambda o: o['Mounts'].append(dict(Type='volume', Name='source', Source='/model/source', Driver='local', Destination='/rw-alias', RW=True))]
        for index, change in enumerate(changes):
            self.alter_stdout(row, lambda values: change(values[0]))
            with self.subTest(index=index), self.assertRaises(ValueError): self.parse()
            path = Path(row['stdout_record']['path']); path.write_bytes(original); row['stdout_record'] = binding.record(path)


if __name__ == '__main__':
    unittest.main()
