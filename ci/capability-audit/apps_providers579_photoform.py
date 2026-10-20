"""Real 2in1 FormHost stage, called inside the original Knowledge actor.

The original curator owns every media mutation. This module neither sends a
synthetic FA event nor requests a manual form refresh. All observations keep
native journals, original phase receipts, FMS rows, UI trees and frame bytes.
"""
import json
import re

from apps_providers579_bindings import raw, bms_json, objects
from apps_providers579_project import bundle, require
from apps_providers579_runtime import KEYS, rows, one

ID = 'behavior:photo-provider-not-activated-2in1'
PHASES = ('prepare', 'hidden', 'unhidden', 'trashed', 'recovered', 'deleted', 'cleanup')


def _result(run, phase):
    return {'schema_version': 1, 'case': 'photosform', 'requirement_ids': [ID], 'run_id': run,
        'profile': '2in1', 'phase': phase, 'operations': [], 'observed_slices': [], 'failures': [],
        'unresolved_requirements': ['real_2in1_new_package_acceptance',
            'cloud_userPropertySettings_complete_provider_and_real_account_flow'],
        'runtime_pass': False, 'first_artifact_behavior_gate_passed': False, 'closed_requirement_ids': []}


class Flow:
    """Only local stage state and seven already-bound callbacks; no resources."""
    def __init__(self, callbacks, run, phase):
        require(type(callbacks) is dict and set(callbacks) == KEYS and all(callable(v) for v in callbacks.values()),
                'exact original held seven callbacks required')
        self.cb, self.run, self.result, self.serial = callbacks, run, _result(run, phase), 0

    def keep(self, kind, record):
        self.result['operations'].append({'kind': kind, 'record': record})
        return record

    def call(self, role, action, errors=False):
        self.serial += 1
        request_id = 'form_' + self.result['phase'] + '_' + str(self.serial) + '_' + action.replace('-', '_')
        request = {'run_id': self.run, 'request_id': request_id, 'action': action, 'payload': {}}
        self.keep('request', request)
        self.keep('start', self.cb['start'](role, action, request))
        record = self.keep('collect', self.cb['collect'](role, request_id))
        values = rows(record['journal'], self.run, role, request_id)
        require(values and any(row['event'] == 'request' for row in values), 'actual dispatched form caller request required')
        if not errors:
            require(any(row['event'] == 'done' for row in values) and not any(row['event'] in
                ('error', 'request-error', 'page-error', 'form-component-error') for row in values), 'actual native form action failed')
        return values, record

    def touch(self, action, payload=None):
        return self.keep('input_' + action, self.cb['input'](action, payload or {}))

    def fixture(self):
        record = self.keep('actual_curator_fixture', self.cb['network']('knowledge-fixture', {}))
        fixture = json.loads(raw(record['fixture']))
        require(fixture['phase'] == self.result['phase'], 'form observation differs from actual completed curator phase')
        self.result.update(boot_id=record['boot_id'], archive_sha256=record['archive_sha256'])
        return fixture

    @staticmethod
    def owned(values, event='running-forms', expected=None):
        forms = one(values, event)
        require(type(forms) is list and len(forms) == 1, 'exactly one real owned native form required')
        form = forms[0]
        require(re.fullmatch('[1-9][0-9]*', form['formId']) and form['bundleName'] == 'com.ohos.photos' and
                form['hostBundleName'] == bundle('photosform', 'grant') and form['moduleName'] == 'phone_photos' and
                form['abilityName'] == 'FormAbility' and form['formName'] == 'widget1', 'actual FMS provider/host identity differs')
        require(expected is None or form['formId'] == expected, 'native form ID changed after original caller death/recovery')
        return form

    def denied(self, role):
        values, record = self.call(role, 'boundaries')
        code = 202 if role == 'normal' else 201
        for event in ('form-info-error', 'form-running-error'):
            found = [row for row in values if row['event'] == event]
            require(len(found) == 1 and found[0]['code'] == code and json.loads(found[0]['value'])['codeType'] == 'number',
                    'every actual FormHost/observer call must reject real ordinary or undeclared-permission identity')
        require(not any(row['event'].endswith('-returned') for row in values), 'protected form API unexpectedly returned')
        return record


def run(guest, root_callbacks, parameters):
    require(type(parameters) is dict and set(parameters) == {'run_id', 'profile'} and parameters['profile'] == '2in1' and
            re.fullmatch('[a-f0-9]{32}', parameters['run_id']), 'real 2in1 package/caller data only')
    flow = Flow(root_callbacks, parameters['run_id'], 'prepare')
    try:
        prepared = flow.keep('prepared_callers', flow.cb['prepare_callers']('photosform', flow.run, ('normal', 'grant', 'denied')))
        require(prepared['profile'] == '2in1', 'phone package cannot accept the 2in1 Photos requirement')
        for role in ('normal', 'grant', 'denied'):
            flow.keep('installed_' + role, flow.cb['install'](role))
        fixture = flow.fixture()
        provider = flow.keep('actual_product_provider', flow.cb['network']('photoform-provider', {}))
        require({'2in1', 'phone', 'default', 'tablet'} <= set(provider['app_types'].split(',')),
                'actual product BMS supported-app-types compatibility is required')
        actual = bms_json(raw(provider['provider_bms']).decode())
        require(any(row.get('bundleName') == 'com.ohos.photos' for row in objects(actual)), 'real provider BMS install required')
        description, _ = flow.call('grant', 'describe')
        infos = one(description, 'form-provider-info')
        require(any(row.get('bundleName') == 'com.ohos.photos' and row.get('moduleName') == 'phone_photos' and
                    row.get('abilityName') == 'FormAbility' and row.get('name') == 'widget1' for row in infos),
                'actual FMS form metadata must expose the installed existing provider')
        require(one(description, 'running-forms') == [], 'fresh own host must have no native retained forms')
        flow.denied('normal'); flow.denied('denied')
        values, acquisition = flow.call('grant', 'show')
        acquired = one(values, 'form-acquired')
        form = flow.owned(values)
        require(acquired['idString'] == form['formId'], 'FormComponent acquisition and FMS allocated identity disagree')
        values, _ = flow.call('grant', 'publish')
        form = flow.owned(values, 'form-published', form['formId'])
        require(form['formLocation'] == 0, 'actual FMS publication location must be DESKTOP')
        flow.call('grant', 'configure')
        flow.touch('photoform-select-photo')
        selection = flow.touch('photos-select-fixture')
        challenge = fixture['challenge']['cases'][0]
        require(selection['uri'] == fixture['uris'][challenge['case_id']], 'form editor must select original actual nonce asset')
        flow.touch('back')
        current, _ = flow.call('grant', 'observe')
        flow.owned(current, expected=form['formId'])
        painted = flow.touch('photoform-pixels', {'expected': 'visible'})
        # Real cancellation leaves the published form and chosen image intact.
        flow.call('grant', 'configure'); flow.touch('back')
        current, _ = flow.call('grant', 'observe'); flow.owned(current, expected=form['formId'])
        cancelled = flow.touch('photoform-pixels', {'expected': 'visible'})
        flow.result['form_id'] = form['formId']
        flow.result['observed_slices'].append({'slice': 'actual_2in1_form_acquisition_config_nonce_and_cancel',
            'acquisition': acquisition, 'selection': selection, 'painted': painted, 'cancelled': cancelled})
    except Exception as error:
        flow.result['failures'].append({'type': type(error).__name__, 'message': str(error)})
    return flow.result


def observe_phase(root_callbacks, run_id, phase, form_id):
    require(phase in PHASES[1:] and re.fullmatch('[1-9][0-9]*', form_id), 'existing real FMS id and original phase required')
    flow = Flow(root_callbacks, run_id, phase)
    try:
        flow.fixture()
        # Kill/relaunch the actual caller once; only its persisted native form
        # ID can reattach. No fresh substitute form or manual refresh is sent.
        if phase == 'unhidden':
            flow.touch('force-stop', {'role': 'grant'})
            values, _ = flow.call('grant', 'attach')
            Flow.owned(values, expected=form_id)
        values, record = flow.call('grant', 'observe')
        form = Flow.owned(values, expected=form_id)
        require(form['formLocation'] == 0, 'native published form location changed')
        expected = 'visible' if phase in ('unhidden', 'recovered') else 'absent'
        pixels = flow.touch('photoform-pixels', {'expected': expected})
        flow.result['observed_slices'].append({'slice': 'native_form_after_original_' + phase,
            'form_id': form_id, 'fms': record, 'render': pixels})
        if phase == 'cleanup':
            flow.denied('normal'); flow.denied('denied')
            removed, removed_raw = flow.call('grant', 'delete-form')
            require(one(removed, 'form-delete-after') == [], 'actual FMS must remove the owned published form')
            describe, _ = flow.call('grant', 'describe')
            require(one(describe, 'running-forms') == [], 'owned native form survives cleanup')
            flow.result['observed_slices'].append({'slice': 'actual_FMS_delete_and_permission_restore_boundary', 'raw': removed_raw})
    except Exception as error:
        flow.result['failures'].append({'type': type(error).__name__, 'message': str(error)})
    return flow.result
