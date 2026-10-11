#!/usr/bin/env python3
"""Check packaged intent metadata and actual transformed sources, not runtime."""
import argparse
import json
from pathlib import Path
import re
import zipfile

from build_insight_decorator_probe import SCOPE, TEMPLATES, sources
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.capabilityaudit'
PREFIX = '@normalized:N&&&vpn-policy-probe/src/main/ets/'
NAMES = ('AuditEntry', 'AuditForm', 'AuditFunction', 'AuditLink', 'AuditPage')
TYPES = ('Entry', 'Form', 'FunctionMethod', 'Link', 'Page')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_metadata(document, nonce):
    require(re.fullmatch('[0-9a-f]{32}', nonce or '') is not None, 'fresh intent nonce required')
    require(isinstance(document, dict), 'actual intent profile must be an object')
    rows = document.get('extractInsightIntents')
    require(isinstance(rows, list) and len(rows) == len(NAMES), 'all five intent metadata records required')
    require([row.get('intentName') for row in rows if isinstance(row, dict)] == list(NAMES),
            'duplicate/missing/reordered intent records')
    for row, name, kind in zip(rows, NAMES, TYPES):
        require(row.get('decoratorType') == '@InsightIntent' + kind and
                row.get('bundleName') == BUNDLE and row.get('moduleName') == 'entry' and
                row.get('domain') == 'LocalDomain' and row.get('intentVersion') == '1.0.0',
                'intent identity/type differs: ' + name)
        filename = 'AuditFunctions' if name == 'AuditFunction' else name
        relative = 'pages/Index' if name == 'AuditPage' else 'intents/' + filename
        require(row.get('decoratorFile') == PREFIX + relative + '&', 'wrong intent source URL: ' + name)
    entry, form, function, link, page = rows
    require(entry.get('abilityName') == 'EntryAbility' and entry.get('executeMode') == ['background'],
            'entry ability/execution mode differs')
    require(entry.get('parameters') == {'type': 'object', 'properties': {
        'value': {'type': 'string'}, 'entity': {'$ref': '/schemas/AuditEntity'}},
        'required': ['value', 'entity']}, 'entry parameter schema differs')
    entities = entry.get('entities')
    require(isinstance(entities, list) and len(entities) == 1, 'entry must carry actual entity metadata')
    entity = entities[0]
    require(isinstance(entity, dict) and entity.get('decoratorType') == '@InsightIntentEntity' and
            entity.get('className') == 'AuditEntity' and entity.get('entityId') == 'audit' and
            entity.get('parentClassName') == 'IntentEntity' and
            entity.get('entityCategory') == 'audit entity' and
            entity.get('supportedQueryProperties') == ['value'] and
            entity.get('decoratorFile') == PREFIX + 'intents/AuditEntity&' and
            entity.get('parameters') == {'$id': '/schemas/AuditEntity', 'type': 'object',
                'properties': {'value': {'type': 'string'}}, 'required': ['value']},
            'entity schema/query/identity differs')
    require(form.get('abilityName') == 'AuditForm' and form.get('formName') == 'AuditWidget',
            'form binding differs')
    require(function.get('decoratorClass') == 'AuditFunctions' and function.get('functionName') == 'echo' and
            function.get('functionParamList') == ['value'] and function.get('parameters') == {
                'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']},
            'actual function class/method/parameters differ')
    require(link.get('uri') == 'audit://intent/' + nonce, 'link nonce/URI differs')
    require(page.get('uiAbility') == 'EntryAbility' and page.get('pagePath') == PREFIX + 'pages/Index&',
            'actual page routing differs')
    return rows


def verify(root, nonce):
    root = root.resolve()
    receipt = root / 'insight-decorator-probe-inputs.json'
    value = json.loads(receipt.read_text())
    expected = sources(nonce, 'valid')
    generated = root / 'entry/src/main/ets/pages/Index.ets'
    require(value.get('scope') == SCOPE and value.get('role') == 'normal' and
            value.get('run_id') == nonce and value.get('request_permissions') == [] and
            value.get('arch') in ('arm64', 'armv7a', 'x86_64') and
            value.get('strict_mode') == {'useNormalizedOHMUrl': True} and
            value.get('template_sha256') == digest(TEMPLATES / 'Index.ets') and
            value.get('generated_source') == str(generated) and
            value.get('generated_source_sha256') == digest(generated), 'exact build receipt required')
    require(set(value.get('additional_input_sha256', {})) == set(expected) - {
        'entry/src/main/ets/pages/Index.ets'}, 'exact additional build input set required')
    declaration = Path(value['sdk_declaration'])
    require(declaration.name == '@ohos.app.ability.InsightIntentDecorator.d.ts' and
            not declaration.is_symlink() and digest(declaration) == value.get('sdk_declaration_sha256'),
            'actual SDK declaration changed')
    for name, content in expected.items():
        path = root / name
        require(not path.is_symlink() and path.is_file(), 'missing/linked generated input: ' + name)
        require(path.read_text() == content if isinstance(content, str) else json.loads(path.read_text()) == content,
                'actual source differs: ' + name)
        if path != generated:
            require(value.get('additional_input_sha256', {}).get(name) == digest(path),
                    'additional source hash differs: ' + name)
    hap = root / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
    require(not hap.is_symlink() and hap.is_file(), 'actual built HAP required')
    with zipfile.ZipFile(hap) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate HAP entries')
        document = json.loads(archive.read('resources/base/profile/insight_intent.json'))
        module = json.loads(archive.read('module.json'))['module']
        require(module.get('hasInsightIntent') is True and module.get('requestPermissions') == [] and
                module.get('packageName') == 'vpn-policy-probe' and
                module.get('virtualMachine') == 'ark24.0.0.0', 'actual dynamic HAP intent declaration differs')
        require({'name': 'ohos.insight.intent', 'resource': '$profile:insight_intent'} in [
            {key: item.get(key) for key in ('name', 'resource')} for item in module.get('metadata', [])],
            'compiled module must reference its actual intent profile')
        require(len(archive.read('ets/modules.abc')) > 0, 'actual compiled ABC required')
        rows = verify_metadata(document, nonce)
    cache = root / 'entry/build/default/cache/default/default@CompileArkTS/esmodule/debug/entry/src/main/ets'
    transformed = {}
    for template in sorted(TEMPLATES.glob('*.ets')):
        name = ('pages/Index' if template.stem == 'Index' else 'intents/' + template.stem) + '.ts'
        path = cache / name
        require(not path.is_symlink() and path.is_file(), 'actual transformed source required: ' + name)
        text = path.read_text()
        require('InsightIntentDecorator' not in text and not re.search(
            r'@InsightIntent(?:Link|Page|Function|FunctionMethod|Entry|Form|Entity)\b', text),
            'compiler failed to erase compile-time decorators: ' + name)
        transformed[name] = {'path': str(path), 'sha256': digest(path)}
    return {'status': 'pass', 'scope': SCOPE, 'first_artifact_behavior_gate_passed': False,
        'run_id': nonce, 'arch': value['arch'], 'inputs': str(receipt), 'inputs_sha256': digest(receipt),
        'unsigned_hap': str(hap), 'unsigned_hap_sha256': digest(hap),
        'metadata': rows, 'transformed_sources': transformed,
        'not_verified': ['BMS intent registration', 'actual intent execution',
            'ArkUI page routing', 'Form creation', 'new package behavior', 'six-package acceptance']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document = verify(args.project, args.run_id)
    with args.output.open('x') as stream:
        stream.write(json.dumps(document, indent=2) + '\n')
