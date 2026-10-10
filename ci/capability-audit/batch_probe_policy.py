"""Collect independent probe failures without relaxing acceptance or VM health."""
from contextlib import contextmanager
import subprocess


@contextmanager
def independent_probe(report, name, health, save):
    # Health errors are intentionally outside the recoverable probe handler.
    # An unhealthy, replaced or incompletely cleaned guest cannot be reused.
    health('before-' + name)
    result = {'status': 'running'}
    report.setdefault('independent_probes', {})[name] = result
    save()
    try:
        yield
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        message = name + ': ' + type(error).__name__ + ': ' + str(error)
        result.update(status='fail', error=message)
        report['failures'].append(message)
        report.update(status='fail', first_artifact_behavior_gate_passed=False)
        save()
    try:
        health('after-' + name)
    except Exception as error:
        result.update(status='fail', fatal_health_error=type(error).__name__ + ': ' + str(error))
        report.update(status='fail', first_artifact_behavior_gate_passed=False)
        save()
        raise
    if result['status'] == 'running':
        result['status'] = 'pass'
    save()
