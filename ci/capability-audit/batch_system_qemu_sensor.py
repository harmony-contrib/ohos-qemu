#!/usr/bin/env python3
"""Run the actual external sensor transport over real sockets; no guest closure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMPONENT = ROOT / 'patches/common/drivers/peripheral/sensor/qemu_external'
FILES = COMPONENT / 'files/hdi_impl'
CASES = ['roundtrip', 'fragmented', 'range_edges', 'duplicate_register', 'sampling_limit',
         'wrong_nonce', 'wrong_magic', 'wrong_version', 'zero_sequence', 'repeated_sequence',
         'nan', 'infinity', 'out_of_range', 'short_frame', 'disconnect_replay', 'disable_replay',
         'unauthorized', 'callback_reentry', 'callback_destroy', 'disable_backpressure',
         'callback_limit', 'file_protection', 'symlink_protection', 'active_path_protection',
         'stale_path', 'path_replacement']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output, cxx='c++'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    binary = output / 'sensor_input'
    argv = [cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g', '-I' + str(FILES),
            str(FILES / 'qemu_sensor_input.cpp'), str(HERE / 'batch_system_qemu_sensor_harness.cpp'),
            '-o', str(binary)]
    proc = subprocess.run(argv, capture_output=True, text=True)
    (output / 'compile.log').write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise ValueError('actual transport compilation failed; see compile.log')
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
               ASAN_OPTIONS=f'detect_leaks={int(platform.system() != "Darwin")}:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    rows = []
    # Keep Unix paths below Darwin's smaller sockaddr_un limit.
    with tempfile.TemporaryDirectory(prefix='qsi-', dir='/tmp') as directory:
        for index, case in enumerate(CASES):
            path = Path(directory) / (str(index) + '.sock')
            command = [str(binary), case, str(path)]
            proc = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
            (output / (case + '.log')).write_text(proc.stdout + proc.stderr)
            rows.append(dict(scenario=case, argv=command, exit_code=proc.returncode))
            if proc.returncode:
                raise ValueError('real socket boundary failed: ' + case)
        # The separate Python controller sends a fresh external challenge through the shipped C++ transport.
        from batch_system_qemu_sensor_controller import load_trace
        random_source = random.SystemRandom()
        challenge = [dict(at_ms=i * 20, **{axis: random_source.uniform(-140, 140) for axis in ('x', 'y', 'z')})
                     for i in range(3)]
        challenge_path = output / 'external-controller-input.json'
        challenge_path.write_text(json.dumps(challenge, indent=2) + '\n')
        path = Path(directory) / 'controller.sock'
        server_command = [str(binary), 'external_controller', str(path)]
        server = subprocess.Popen(server_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=env)
        try:
            if server.stdout.readline().strip() != 'READY':
                raise ValueError('external controller server failed before readiness')
            controller_command = [sys.executable, str(HERE / 'batch_system_qemu_sensor_controller.py'),
                                  '--unix-path', str(path), '--input', str(challenge_path),
                                  '--output', str(output / 'external-controller-sent.json')]
            controller = subprocess.run(controller_command, capture_output=True, text=True, env=env, timeout=10)
            stdout, stderr = server.communicate(timeout=5)
            (output / 'external_controller.log').write_text(controller.stdout + controller.stderr + stdout + stderr)
            if controller.returncode or server.returncode:
                raise ValueError('external controller challenge failed')
            actual = [line.split() for line in stdout.splitlines() if len(line.split()) == 4]
            expected = load_trace(challenge_path)
            if len(actual) != 3:
                raise ValueError('controller delivered an unexpected number of samples')
            previous = 0
            for delivered, sample in zip(actual, expected):
                for axis, value in zip(('x', 'y', 'z'), delivered[:3]):
                    if abs(float(value) - sample[axis]) > 0.000001:
                        raise ValueError('controller challenge axes/values did not reach actual transport')
                timestamp = int(delivered[3])
                if timestamp <= previous:
                    raise ValueError('controller challenge lost monotonic timestamps')
                previous = timestamp
            rows.append(dict(scenario='external_controller', argv=server_command,
                             controller_argv=controller_command, exit_code=0))
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()
    result = dict(status='pass_real_host_sensor_input', platform=platform.platform(),
                  compiler=subprocess.check_output([cxx, '--version'], text=True).splitlines()[0],
                  source_sha256={p.name: sha(p) for p in sorted(FILES.glob('*'))},
                  compile_argv=argv, binary_sha256=sha(binary), cases=rows,
                  authorized_host_test_uid=os.geteuid(), product_vdi_writer_uid=0,
                  runtime_tested=False, requirements_closed=0, first_artifact_behavior_gate_passed=False,
                  limitations='Actual shipped transport/protocol and real peer credentials/sockets executed; '
                              'host tests explicitly authorize the host UID. Product VDI pins UID 0. '
                              'No official HDI headers/TU, SensorService/MSDP API, SELinux or packaged guest '
                              'has been validated by this host transport test.')
    (output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', default='c++')
    args = parser.parse_args()
    result = run(args.output, args.cxx)
    print(json.dumps(dict(status=result['status'], cases=len(result['cases']))))
