"""Compiler-evidence validation fixtures; no guest intent behavior is mocked as pass."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from build_always_on_vpn_probe import build_application
from build_insight_decorator_probe import CASES, SCOPE, TEMPLATES, module, sources
from verify_insight_decorator_build import BUNDLE, NAMES, PREFIX, TYPES, verify_metadata

NONCE = 'a' * 32


def metadata():
    rows = []
    for name, kind in zip(NAMES, TYPES):
        filename = 'AuditFunctions' if name == 'AuditFunction' else name
        relative = 'pages/Index' if name == 'AuditPage' else 'intents/' + filename
        rows.append(dict(intentName=name, decoratorType='@InsightIntent' + kind,
            bundleName=BUNDLE, moduleName='entry', domain='LocalDomain', intentVersion='1.0.0',
            decoratorClass='Index' if name == 'AuditPage' else filename,
            displayName='Audit ' + name.removeprefix('Audit').lower(),
            decoratorFile=PREFIX + relative + '&'))
    rows[0].update(abilityName='EntryAbility', executeMode=['background'], parameters={
        'type': 'object', 'properties': {'value': {'type': 'string'},
        'entity': {'$ref': '/schemas/AuditEntity'}}, 'required': ['value', 'entity']}, entities=[dict(
        decoratorType='@InsightIntentEntity', className='AuditEntity', entityId='audit',
        parentClassName='IntentEntity', entityCategory='audit entity', supportedQueryProperties=['value'],
        decoratorFile=PREFIX + 'intents/AuditEntity&', parameters={'$id': '/schemas/AuditEntity',
            'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']})])
    rows[1].update(abilityName='AuditForm', formName='AuditWidget')
    rows[2].update(decoratorClass='AuditFunctions', functionName='echo', functionParamList=['value'],
        parameters={'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']})
    rows[3]['uri'] = 'audit://intent/' + NONCE
    rows[4].update(uiAbility='EntryAbility', pagePath=PREFIX + 'pages/Index&')
    return dict(extractInsightIntents=rows)


class InsightDecoratorCompilationTests(unittest.TestCase):
    def test_all_seven_compiler_contracts_present_in_real_sources(self):
        text = '\n'.join(path.read_text() for path in TEMPLATES.glob('*.ets'))
        for name in ('Entity', 'Entry', 'Form', 'Function', 'FunctionMethod', 'Link', 'Page'):
            self.assertIn('@InsightIntent' + name + '(', text)
        generated = sources(NONCE, 'valid')
        self.assertNotIn('__INTENT_RUN__', str(generated))
        self.assertIn('entry/src/main/ets/pages/AuditWidget.ets', generated)
        self.assertEqual(generated['entry/src/main/resources/base/profile/form_config.json']['forms'][0]['src'],
            './ets/pages/AuditWidget.ets')
        self.assertNotIn({'srcEntry': './ets/intents/AuditWidget.ets'},
            generated['entry/src/main/resources/base/profile/insight_intent.json']['insightIntentsSrcEntry'])
        self.assertIn(NONCE, generated['entry/src/main/ets/intents/AuditLink.ets'])
        self.assertIn('NOT_guest', SCOPE)

    def test_ordinary_application_permissions_and_real_profile_binding(self):
        body = module('normal')['module']
        self.assertEqual(body['requestPermissions'], [])
        self.assertEqual(body['metadata'], [{'name': 'ohos.insight.intent', 'resource': '$profile:insight_intent'}])
        self.assertEqual(body['extensionAbilities'][0]['type'], 'form')
        self.assertFalse(body['extensionAbilities'][0]['exported'])
        with self.assertRaises(ValueError):
            module('system')

    def test_invalid_cases_are_exact_single_source_changes_not_disabled_checker(self):
        baseline = sources(NONCE, 'valid')
        for case in CASES[1:]:
            actual = sources(NONCE, case)
            self.assertEqual(actual.keys(), baseline.keys())
            self.assertEqual(sum(actual[key] != baseline[key] for key in actual), 1)
        for nonce, case in (('a' * 31, 'valid'), ('A' * 32, 'valid'), (NONCE, 'unknown')):
            with self.assertRaises(ValueError):
                sources(nonce, case)

    def test_exact_metadata_all_paths_entity_and_function(self):
        document = metadata()
        self.assertEqual(verify_metadata(document, NONCE), document['extractInsightIntents'])

    def test_reject_absent_duplicate_reordered_and_wrong_identity_records(self):
        original = metadata()
        for change in ('absent', 'duplicate', 'reordered', 'identity', 'type', 'source'):
            document = copy.deepcopy(original)
            rows = document['extractInsightIntents']
            if change == 'absent': rows.pop()
            elif change == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            elif change == 'reordered': rows.reverse()
            elif change == 'identity': rows[0]['bundleName'] = 'another.bundle'
            elif change == 'type': rows[0]['decoratorType'] = '@InsightIntentLink'
            else: rows[0]['decoratorFile'] = '@bundle:old/path'
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_metadata(document, NONCE)

    def test_reject_missing_or_wrong_entity_schema_and_query(self):
        for key in ('entities', 'parameters', 'supportedQueryProperties', 'entityId', 'parentClassName'):
            document = metadata()
            if key == 'entities': del document['extractInsightIntents'][0][key]
            else: del document['extractInsightIntents'][0]['entities'][0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_metadata(document, NONCE)

    def test_reject_missing_native_profile_required_identity_and_display(self):
        for index in range(len(NAMES)):
            for key in ('decoratorClass', 'displayName', 'domain', 'intentVersion'):
                document = metadata()
                del document['extractInsightIntents'][index][key]
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    verify_metadata(document, NONCE)

    def test_reject_wrong_mode_form_method_nonce_and_page(self):
        for index, key, value in ((0, 'executeMode', ['foreground']), (1, 'formName', 'absent'),
                (2, 'functionParamList', []), (2, 'functionName', 'other'),
                (3, 'uri', 'audit://intent/' + 'b' * 32), (4, 'pagePath', 'pages/Index')):
            document = metadata()
            document['extractInsightIntents'][index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_metadata(document, NONCE)

    def test_additional_sources_are_hashed_and_strict_mode_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / 'sdk'
            for name in ('ets', 'native'):
                path = sdk / name
                path.mkdir(parents=True)
                (path / 'oh-uni-package.json').write_text(json.dumps(dict(
                    apiVersion='26', releaseType='Release', platformVersion='26.0.0')))
            (sdk / 'ets/api').mkdir()
            (sdk / 'ets/api/@ohos.fixture.d.ts').write_text('export {};')
            root = Path(directory) / 'project'
            args = SimpleNamespace(output=root, sdk=sdk, role='normal', run_id=NONCE,
                arch='arm64', arkdown='actual-compiler')
            with patch('build_always_on_vpn_probe.subprocess.run') as compiler:
                build_application(args, 'page', TEMPLATES / 'Index.ets', 'inputs.json',
                    'fixture_NOT_guest', '@ohos.fixture.d.ts', extra_files={'entry/extra.ets': 'real source'},
                    strict_mode={'useNormalizedOHMUrl': True})
            profile = json.loads((root / 'entry/build-profile.json5').read_text())
            self.assertEqual(profile['buildOption']['strictMode'], {'useNormalizedOHMUrl': True})
            receipt = json.loads((root / 'inputs.json').read_text())
            self.assertEqual(len(receipt['additional_input_sha256']['entry/extra.ets']), 64)
            self.assertEqual(compiler.call_count, 1)
            self.assertNotIn('--skip-checker', compiler.call_args.args[0])

    def test_additional_sources_cannot_overwrite_or_escape_project(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory) / 'sdk'
            for name in ('ets', 'native'):
                path = sdk / name
                path.mkdir(parents=True)
                (path / 'oh-uni-package.json').write_text(json.dumps(dict(
                    apiVersion='26', releaseType='Release', platformVersion='26.0.0')))
            for index, name in enumerate(('entry/src/main/ets/pages/Index.ets', '../escape', '/absolute')):
                args = SimpleNamespace(output=Path(directory) / str(index), sdk=sdk,
                    role='normal', run_id=NONCE, arch='arm64', arkdown='compiler')
                with self.subTest(name=name), self.assertRaises(ValueError), patch(
                        'build_always_on_vpn_probe.subprocess.run') as compiler:
                    build_application(args, 'original', TEMPLATES / 'Index.ets', 'inputs.json',
                        'fixture_NOT_guest', '@ohos.fixture.d.ts', extra_files={name: 'overwrite'})
                self.assertFalse(compiler.called)
                self.assertEqual((args.output / 'entry/src/main/ets/pages/Index.ets').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
