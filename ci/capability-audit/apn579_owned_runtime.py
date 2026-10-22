"""Fixed wrapper for the original Apps APN stage, on its original OwnedIO.

Parent registers the typed family and selected pre-VM helper only. This source
implements the dispatcher and context; no separate Owner or resource launcher.
The original Apps callback dictionary stays available to its original reviewer.
"""
from pathlib import Path
import json
from capability578_owned_io import require, reference
from apn579_owned_bindings import virtual_sim
from apn579_owned_oracle import verify


def run(root_io, parameters, apps_bindings):
    from apps_ui578_bindings import bind
    from apps_ui578_runtime import run as run_apps
    require(type(parameters) is dict and set(parameters) == {'case','output','ui_plan','full_blink'} and
        parameters['case'] == 'apn' and type(parameters['full_blink']) is bool and
        Path(parameters['output']) == Path(root_io.output) / 'runtime' and
        type(apps_bindings) is dict and not apps_bindings,
        'only the original fixed APN stage/output and fresh reviewer bindings are accepted')
    with virtual_sim(root_io) as modem:
        apps_bindings.update(bind(root_io))
        result = run_apps(root_io.guest,apps_bindings,parameters)
        modem.join_apps(result,Path(parameters['output']) / 'evidence.json')
        # L22 reuses this exact held peer after original complete APN CRUD.
        # Its failures are preserved separately and replayed by Root only
        # after IO.close and the original Owner final settlement.
        from telephony579_runtime import run as run_transactions
        run_transactions(root_io,modem)
    # The independent replay uses the preserved original stdout/footer, peer
    # stdin and raw typed journals after reverse cleanup, before root reviews
    # the unchanged original Apps result with its existing raw UI verifier.
    try:
        replay = verify(root_io,reference(modem.output / 'evidence.json'))
        (modem.output / 'replay.json').write_text(json.dumps(replay,indent=2) + '\n')
    except Exception as error:
        modem.report['runtime_pass'] = False
        modem.report['failures'].append('independent actual raw replay: ' + str(error))
        modem.save()
        raise
    return result
