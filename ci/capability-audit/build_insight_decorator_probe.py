#!/usr/bin/env python3
"""Compile real API26 dynamic intent decorators; not an intent-execution gate."""
import argparse
import os
from pathlib import Path
import re

from build_always_on_vpn_probe import build_application, module as base_module

TEMPLATES = Path(__file__).with_name('insight_decorator_sources')
SCOPE = 'real_API26_dynamic_decorator_metadata_NOT_guest_intent_execution'
CASES = ('valid', 'duplicate-name', 'orphan-method', 'invalid-page', 'invalid-form')


def module(role, compiled=False):
    if role != 'normal':
        raise ValueError('decorator compiler probe is an ordinary application')
    value = base_module(role, compiled)
    body = value['module']
    body['metadata'] = [{'name': 'ohos.insight.intent', 'resource': '$profile:insight_intent'}]
    body['extensionAbilities'] = [{
        'name': 'AuditForm', 'srcEntry': './ets/intents/AuditForm.ets', 'type': 'form',
        'exported': False,
        'metadata': [{'name': 'ohos.extension.form', 'resource': '$profile:form_config'}]}]
    return value


def sources(run_id, case):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or case not in CASES:
        raise ValueError('fresh nonce and exact decorator case required')
    result = {}
    for path in sorted(TEMPLATES.glob('*.ets')):
        name = ('pages/Index.ets' if path.name == 'Index.ets' else 'intents/' + path.name)
        result['entry/src/main/ets/' + name] = path.read_text().replace('__INTENT_RUN__', run_id)
    if case == 'duplicate-name':
        key = 'entry/src/main/ets/intents/AuditLink.ets'
        result[key] = result[key].replace("intentName: 'AuditLink'", "intentName: 'AuditFunction'")
    elif case == 'orphan-method':
        key = 'entry/src/main/ets/intents/AuditFunctions.ets'
        result[key] = result[key].replace('@InsightIntentFunction()\n', '')
    elif case == 'invalid-page':
        key = 'entry/src/main/ets/pages/Index.ets'
        result[key] = result[key].replace("pagePath: './ets/pages/Index.ets'", "pagePath: './ets/pages/Absent.ets'")
    elif case == 'invalid-form':
        key = 'entry/src/main/ets/intents/AuditForm.ets'
        result[key] = result[key].replace("formName: 'AuditWidget'", "formName: 'AbsentWidget'")
    result['entry/src/main/resources/base/profile/insight_intent.json'] = {
        'insightIntentsSrcEntry': [{'srcEntry': './ets/intents/' + path.name}
            for path in sorted(TEMPLATES.glob('*.ets')) if path.name != 'Index.ets']}
    result['entry/src/main/resources/base/profile/form_config.json'] = {'forms': [{
        'name': 'AuditWidget', 'displayName': '$string:app_name',
        'description': '$string:app_name', 'src': './ets/pages/Index.ets',
        'uiSyntax': 'arkts', 'window': {'designWidth': 720, 'autoDesignWidth': True},
        'colorMode': 'auto', 'isDefault': True, 'updateEnabled': False,
        'scheduledUpdateTime': '00:00', 'updateDuration': 0,
        'defaultDimension': '2*2', 'supportDimensions': ['2*2']}]}
    return result


def build(args):
    files = sources(args.run_id, args.case)
    page = files.pop('entry/src/main/ets/pages/Index.ets')
    return build_application(args, page, TEMPLATES / 'Index.ets',
        'insight-decorator-probe-inputs.json', SCOPE, '@ohos.app.ability.InsightIntentDecorator.d.ts',
        module_factory=module, extra_files=files, strict_mode={'useNormalizedOHMUrl': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=('normal',), default='normal')
    parser.add_argument('--case', choices=CASES, default='valid')
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
