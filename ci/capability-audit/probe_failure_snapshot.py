"""Read actual application/window/render state before an owned failed caller exits."""
import re


def capture(shell, bundle, label):
    if re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+', bundle) is None:
        raise ValueError('one exact owned application bundle required')
    report = {'scope': 'readonly_failure_diagnostic_NOT_behavior_success', 'observations': {}}
    for name, script in (
            ('kernel-pids', 'pidof ' + bundle + ' || true'),
            ('ability-state', 'aa dump -a -u 100'),
            ('window-state', 'hidumper -s 4606 -a "-a"'),
            ('render-help', 'hidumper -s 10'),
            ('render-tree', 'hidumper -s 10 -a "RSTree"'),
            ('render-client-trees', 'hidumper -s 10 -a "client"'),
            ('render-contexts', 'hidumper -s 10 -a "uiContextState"'),
            ('render-surfaces', 'hidumper -s 10 -a "surface"'),
            ('render-processes', 'pidof render_service render_service_renderprocess || true')):
        try:
            report['observations'][name] = shell(script, label + '-' + name, True)
        except Exception as error:
            report['observations'][name] = {'capture_error': str(error)}
    return report
