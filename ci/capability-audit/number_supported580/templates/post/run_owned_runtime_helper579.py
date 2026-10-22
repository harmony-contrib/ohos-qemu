"""Canonical owned helper successor; explicit QA/new profile producer; Owner35 preserved."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import tarfile
import runtime_source377_common as context

SPECS = {'netlink': ('build_network_kernel_snapshot.py', ['--execute-build']),
         'core': ('batch_system_build_runtime_helpers.py', ['--product', 'arm64_virt']),
         'audio': ('batch_media_audio_haptic_build_sampler.py', []),
         'calendar': ('batch_system_calendar_runtime_helper.py', []),
         'gnss': ('batch_system_gnss_trace_helper.py', []),
         'mic': ('build_audio_capture_tools.py', ['--arch', 'arm64']),
         'number': ('batch_system_build_runtime_helpers.py', []),
         'number-recheck': ('batch_system_build_runtime_helpers.py', [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=sorted(SPECS)); parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True); parser.add_argument('--here', type=Path, required=True)
    parser.add_argument('--qa-root', type=Path, required=True)
    parser.add_argument('--profile-producer', type=Path, required=True)
    parser.add_argument('--profile-producer-sha256', required=True)
    parser.add_argument('--commit', help='If supplied, must equal the explicit pinned intent product/tools commit')
    args = parser.parse_args(argv)
    globals().update(context.bind_support(args.here, args.qa_root))
    dependency_before = context.verify_dependencies(args.here)
    config_row = dict(path=str(regular(args.config)), sha256=args.config_sha256)
    intent = load(checked(config_row))
    require(intent['schema_version'] == 'helper-build-intent579-target/v2' and set(intent['outputs']) == set(SPECS),
            'complete actual helper-build intent15 required')
    commit = intent['product_commit']
    require(commit == intent['tools_commit'] and (args.commit is None or args.commit == commit),
            'explicit final F product/tools/optional CLI commit differs')
    require(intent['qa_root'] == str(args.qa_root), 'explicit QA root differs from helper intent')
    here, root = configure(args.here, args.qa_root)
    profile_file = checked(intent['runtime_profile']); require(profile_file.name == 'runtime-profile.json', 'canonical profile name required')
    profile_root = profile_file.parent; profile_before = record(profile_file)
    dependency = directory(intent['python_dependency_root'])
    require(checked(intent['python_dependency_receipt']) == dependency / 'receipt.json' and
            load(dependency / 'receipt.json')['Pillow'] == '12.3.0', 'actual pinned diagnostic Pillow input required')
    dep_before = record(dependency / 'receipt.json')
    wrapper = regular(here / 'build_helpers_with_installed_dso_export16.py'); wrapper_before = record(wrapper)
    require(wrapper_before['sha256'] == '4ccceb66e7e10f51d6f6cb6222a6caa963d2ae446c11f272ca87ee38e69892bf',
            'root-frozen wrapper16 source changed; review new successor before execution')
    profile_producer, producer_before = context.admit_producer(args.profile_producer, args.profile_producer_sha256)
    out = Path(intent['outputs'][args.kind])
    require(out.parent == BASE, 'explicit new BASE child helper output required')
    owner = Owner(out)
    with owner:
        report = dict(source_commit=commit, package_commit=commit, native_product_source_commit=commit,
                      exit_code=1, commands=owner.commands, scope='actual new F CFI/ABI diagnostic helper build ONLY',
                      runtime_profile=intent['runtime_profile'], first_artifact_behavior_gate_passed=False,
                      source_out_written=False, here=str(here), qa_root=str(root), dependency_sources=dependency_before,
                      assembly_intent=record(checked(config_row)),
                      private_source=record(Path(__file__).resolve()), wrapper_source=wrapper_before,
                      profile_producer_source=producer_before)
        path = out / 'evidence.json'; owner.callbacks.append(lambda: write_json(path, report)); write_json(path, report)
        try:
            receipt_file, product, package, inputs = package_inputs(owner, root, commit, intent['package_receipt'], intent['archive'])
            report['package'] = dict(path=str(package), sha256=sha(package))
            report['new_package_inputs'] = dict(source_git_revision=commit, tree_sha256=inputs['tree_sha256'], archive_sha256=sha(package))
            from batch_system_build_runtime_helpers import validate_installed_profile
            profile = load(profile_file); validate_installed_profile(profile, archive_sha256=sha(package))
            profile_receipt = load(regular(profile_root / 'receipt.json'))
            require(type(profile_receipt.get('exit_code')) is int and profile_receipt['exit_code'] == 0 and
                    profile_receipt['source_commit'] == commit and profile_receipt['package']['sha256'] == sha(package) and
                    checked(profile_receipt['profile']) == profile_file, 'actual newly generated profile receipt differs')
            context.producer_receipt(profile_receipt, producer_before, root)
            report['profile_preparation_receipt'] = record(profile_root / 'receipt.json')
            require(profile['source_root'] == '/ohos' and profile['archive']['bytes'] == package.stat().st_size,
                    'actual new-package runtime profile required')
            mounted = Path(profile['archive']['path']); require(mounted.parent == Path('/runtime-profile'), 'fixed profile archive mount required')
            require(sha(regular(profile_root / mounted.name)) == sha(package), 'profile archive bytes differ')
            archive = owner.command(['git', '-C', root, 'archive', commit], 'git-archive-final-F', timeout=120, check=True)
            archive_path = out / 'inputs.tar'; archive_path.write_bytes(archive.stdout)
            report['archive_sha256'] = sha(archive_path)
            frozen = out / 'frozen'; frozen.mkdir()
            with tarfile.open(archive_path) as stream: stream.extractall(frozen, filter='data')
            runner = out / 'runner'; runner.mkdir(); shutil.copyfile(wrapper, runner / 'build.py')
            require(sha(runner / 'build.py') == wrapper_before['sha256'], 'actual wrapper copy differs')
            report['runner_sha256'] = sha(runner / 'build.py')
            mounts = {'/ohos': volume_mount(SOURCE_VOLUME), '/ohos/out': volume_mount(OUT_VOLUME),
                      '/work': bind_mount(frozen), '/evidence': bind_mount(out, True),
                      '/runner': bind_mount(runner), '/runtime-profile': bind_mount(profile_root),
                      '/python-deps': bind_mount(directory(dependency / 'python'))}
            script, extra = SPECS[args.kind]
            extra = (['--product', profile['product']] if args.kind in ('core', 'number', 'number-recheck') else
                ['--arch', profile['arch']] if args.kind == 'mic' else list(extra))
            number_prior = None
            if args.kind in ('number', 'number-recheck'):
                extra += ['--helper', 'number_token_query395']
            if args.kind == 'number-recheck':
                previous = Path(intent['outputs']['number'])
                require(previous.parent == BASE and previous != out,
                        'separate original Number helper output required')
                prior_receipt = regular(previous / 'evidence.json')
                prior = load(prior_receipt)
                require(prior.get('exit_code') == 0 and prior.get('source_commit') == commit and
                        prior.get('cleanup_verified') is True and prior.get('owned_container_absent') is True and
                        not prior.get('must_resolve_owned_resources_before_next_stage') and
                        prior.get('assembly_intent') == record(checked(config_row)),
                        'closed same-intent actual Number build required before independent recheck')
                prior_ledger = load(checked(prior['resource_ledger']))
                require(prior_ledger.get('schema') == 'owned-resource35/v1' and
                        prior_ledger.get('phase') == 'closed' and prior_ledger.get('cleanup_verified') is True and
                        prior_ledger.get('failed') is False and prior_ledger.get('errors') == [],
                        'original Number Owner ledger must be closed without resource uncertainty')
                prior_build = regular(previous / 'helpers/build.json')
                require(load(prior_build).get('status') == 'pass_compile_link_ONLY' and
                        set(load(prior_build).get('helpers', {})) == {'number_token_query395'},
                        'exact original Number helper result required')
                number_prior = dict(receipt=record(prior_receipt), build=record(prior_build))
                mounts['/number-previous'] = bind_mount(previous)
                extra += ['--verify-existing', '/number-previous/helpers/build.json',
                          '--existing-report-sha256', number_prior['build']['sha256']]
            elif intent['normal_link_target'] is not None:
                extra += ['--normal-link-target', intent['normal_link_target']]
            runtime_args = ([] if args.kind == 'number-recheck' else
                ['--runtime-profile', '/runtime-profile/runtime-profile.json',
                 '--runtime-profile-sha256', profile_before['sha256']])
            command = ['python3', '/runner/build.py', '--script', '/work/ci/capability-audit/' + script,
                       '--expected-runtime-profile', '/runtime-profile/runtime-profile.json',
                       '--expected-runtime-profile-sha256', profile_before['sha256'],
                       '--source-root', '/ohos', *extra, *runtime_args, '--output', '/evidence/helpers']
            entry = owner.plan(name='ohos-F-helper35-' + args.kind + '-' + owner.owner, commit=commit,
                               image=IMAGE, mounts=mounts, command=command)
            entry['cidfile'] = str(out / 'container.cid'); owner.save()
            options = mount_options(mounts, cpus='2', memory='5g', pids='512', tmpfs='1g',
                                    extra=['-e', 'PYTHONPATH=/python-deps', '-e', 'PYTHONDONTWRITEBYTECODE=1'])
            owner.create(entry, options); report['owned_container_id'] = entry['id']; report['run_id'] = owner.owner
            report['argv'] = next(row['argv'] for row in owner.commands if row['label'] == 'create-owned')
            result = owner.start(entry, timeout=1800, combined=True)
            (out / 'container.log').write_bytes(result.stdout); report['container_log_sha256'] = sha(out / 'container.log')
            build = regular(out / 'helpers/build.json'); data = load(build)
            if 'helpers' in data: actual = data
            else:
                actual_file = regular(out / 'helpers/product-build/build.json'); actual = load(actual_file)
                require(data['product_build']['sha256'] == sha(actual_file), 'outer/product helper build differs')
            require(actual['status'] == 'pass_compile_link_ONLY' and actual.get('plan_only') is False and
                    actual.get('changed_inputs') == [], 'actual all-new complete helper build required')
            expected_profile_source = None
            require(actual['helpers'], 'nonempty actual helper set required')
            for row in actual['helpers'].values():
                installed = row['installed_runtime_profile']
                require(installed['profile'] == profile and installed['source']['sha256'] == profile_before['sha256'] and
                        installed['source']['bytes'] == profile_before['bytes'], 'actual helper row differs from intent profile')
                if expected_profile_source is None: expected_profile_source = installed
                require(installed == expected_profile_source, 'all actual helpers must share full installed source/profile identity')
            if args.kind in ('number', 'number-recheck'):
                require(set(actual['helpers']) == {'number_token_query395'},
                        'Number production must contain exactly its original token observer')
                if number_prior is not None:
                    require(actual.get('verify_existing') is True and
                            actual['original_report']['sha256'] == number_prior['build']['sha256'],
                            'actual independent recheck must bind the original completed build')
                    for item in number_prior.values(): checked(item)
                report['number580_prior_build'] = number_prior
            report.update(build_report=str(build), build_report_sha256=sha(build),
                          helpers={key: {k: value.get(k) for k in ('status', 'error', 'binary', 'binary_sha256', 'CFI_preserved', 'DT_NEEDED')}
                                   for key, value in actual['helpers'].items()})
            manifest = regular(out / 'product-dsos/manifest.json'); report['product_dso_manifest'] = record(manifest)
            require(all(record(p) == before for p, before in ((profile_file, profile_before),
                    (dependency / 'receipt.json', dep_before), (wrapper, wrapper_before), (profile_producer, producer_before))), 'helper fixed inputs changed')
            require(sha(runner / 'build.py') == wrapper_before['sha256'], 'helper runtime wrapper changed')
            checked(config_row); checked(intent['package_receipt']); checked(intent['archive']); clean(owner, root, commit)
            report['diagnostic_python_dependencies'] = dict(path=str(dependency / 'receipt.json'),
                sha256=dep_before['sha256'], source_out_or_product_changed=False)
            require(context.verify_dependencies(here) == dependency_before, 'immutable runtime helper dependencies changed')
            report['exit_code'] = 0
        except BaseException as error:
            report.update(exit_code=1, error=type(error).__name__ + ': ' + str(error)); owner.note_failure(error)
        finally:
            finish_report(owner, report, path)
    print(json.dumps({k: report.get(k) for k in ('exit_code', 'helpers', 'error', 'cleanup_verified')}))
    return report['exit_code']


if __name__ == '__main__': raise SystemExit(main())
