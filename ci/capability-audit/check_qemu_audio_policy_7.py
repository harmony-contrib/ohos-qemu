#!/usr/bin/env python3
"""Pristine fixed-source patch and actual ext4 readback; no guest PCM claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/vendor/ohemu/audio_policy_7'
FRAMEWORK_INPUTS = (
    'services/audio_policy/server/infra/config/parser/src/audio_policy_config_parser.cpp',
    'services/audio_policy/server/domain/pipe/src/audio_definition_adapter_info.cpp',
    'services/audio_policy/server/domain/pipe/src/audio_definition_policy_utils.cpp',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_project(source, target, paths=()):
    target.mkdir(parents=True)
    process = subprocess.Popen(['git', '-C', str(source), 'archive', 'HEAD', *paths], stdout=subprocess.PIPE)
    subprocess.run(['tar', '-xf', '-', '-C', str(target)], stdin=process.stdout, check=True)
    process.stdout.close()
    if process.wait() != 0:
        raise ValueError('fixed git archive failed')
    gitdir = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--absolute-git-dir'], text=True).strip()
    (target / '.git').write_text('gitdir: ' + gitdir + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    if any(not os.statvfs(source / relative).f_flag & os.ST_RDONLY for relative in
           ('vendor/ohemu', 'foundation/multimedia/audio_framework')):
        raise ValueError('production source must be read-only')
    work = args.work.absolute()
    if work.is_symlink() or work.parent != Path('/tmp') or not work.name.startswith('audio-policy-7-validation-'):
        raise ValueError('exclusive /tmp/audio-policy-7-validation-* work required')
    work.mkdir(exist_ok=True)
    if any(work.iterdir()):
        raise ValueError('work must be empty; preserve prior evidence')
    evidence = {'scope': 'pristine patch and actual ext4 XML readback only', 'passed': False,
                'production_source_readonly': True, 'commands': [], 'pcm_behavior_validated': False,
                'first_artifact_behavior_gate_passed': False}

    def run(command, name, required=True):
        log = work / (name + '.log')
        start = time.monotonic()
        with log.open('w') as stream:
            stream.write(json.dumps({'argv': list(map(str, command)), 'cwd': str(work)}) + '\n')
            stream.flush()
            result = subprocess.run(list(map(str, command)), cwd=work, stdout=stream, stderr=subprocess.STDOUT)
        record = {'argv': list(map(str, command)), 'returncode': result.returncode,
                  'seconds': round(time.monotonic() - start, 3), 'log': str(log), 'log_sha256': digest(log)}
        evidence['commands'].append(record)
        (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        if required and result.returncode != 0:
            raise ValueError('actual AudioPolicy validation command failed: ' + str(record))
        return result.returncode

    staged = work / 'source'
    archive_project(source / 'vendor/ohemu', staged / 'vendor/ohemu',
                    ('virt/hals/audio/config/audio_policy_config_new.xml',))
    archive_project(source / 'foundation/multimedia/audio_framework',
                    staged / 'foundation/multimedia/audio_framework', FRAMEWORK_INPUTS)
    original_xml = source / 'vendor/ohemu/virt/hals/audio/config/audio_policy_config_new.xml'
    original_sha = digest(original_xml)
    for iteration in (1, 2):
        run(['bash', COMPONENT / 'apply.sh', '--source-root', staged], f'apply-{iteration}')
    repaired = staged / 'vendor/ohemu/virt/hals/audio/config/audio_policy_config_new.xml'
    evidence['repaired_xml_sha256'] = digest(repaired)
    run(['git', '-C', staged, 'apply', '--reverse', '--check',
         COMPONENT / '0001-map-normal-audio-routes-with-7.0-pipe-schema.patch'], 'reverse-check')
    fixture = work / 'fixture'
    (fixture / 'etc/audio').mkdir(parents=True)
    xml = fixture / 'etc/audio/audio_policy_config.xml'
    image = work / 'chip_prod-fixture.img'
    with image.open('wb') as stream:
        stream.truncate(8 * 1024 * 1024)
    xml.write_bytes(original_xml.read_bytes())
    run(['mkfs.ext4', '-q', '-F', '-d', fixture, image], 'original-mkfs')
    original_exit = run(['python3', REPO / 'scripts/verify_qemu_audio_policy_image.py',
                         '--chip-prod-image', image, '--output', work / 'original-image.json'],
                        'original-image-rejection', required=False)
    if original_exit != 1:
        raise ValueError('original unmapped XML was not rejected')
    xml.write_bytes(repaired.read_bytes())
    run(['mkfs.ext4', '-q', '-F', '-d', fixture, image], 'repaired-mkfs')
    run(['python3', REPO / 'scripts/verify_qemu_audio_policy_image.py',
         '--chip-prod-image', image, '--output', work / 'repaired-image.json'], 'repaired-image-readback')
    repaired.write_bytes(b'owned unknown source edit')
    rejection = run(['bash', COMPONENT / 'apply.sh', '--source-root', staged],
                    'unknown-edit-rejection', required=False)
    if rejection == 0 or repaired.read_bytes() != b'owned unknown source edit':
        raise ValueError('unknown source edit was changed or not rejected')
    if digest(original_xml) != original_sha:
        raise ValueError('production XML changed')
    evidence['production_xml_sha256'] = original_sha
    evidence['passed'] = True
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
