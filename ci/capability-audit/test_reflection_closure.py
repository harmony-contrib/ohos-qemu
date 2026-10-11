"""Runtime presence must not hide failed constructors or missing behavior."""
import unittest
from verify_gap_closure import reflection_closes_contract
from verify_arkts_exports_results import SETTINGS_TTS_VALUES


class ReflectionClosureTests(unittest.TestCase):
    def test_functions_classes_variables_and_arbitrary_namespaces_never_close_by_presence(self):
        for kind in ('function', 'class', 'variable', 'namespace'):
            for value_type in range(10):
                with self.subTest(kind=kind, value_type=value_type):
                    self.assertFalse(reflection_closes_contract('@ohos.contact',
                        {'name': 'ContactAttributes', 'kind': kind}, dict(read_status=0, read_exception=False,
                            value_type=value_type, enum_contract_applicable=True, enum_contract_valid=True)))

    def test_enum_requires_exact_contract_and_real_numeric_type(self):
        row = dict(read_status=0, read_exception=False, value_type=6,
                   enum_contract_applicable=True, enum_contract_valid=True)
        requirement = dict(name='Mode', kind='enum')
        self.assertTrue(reflection_closes_contract('@ohos.example', requirement, row))
        for key, bad in (('read_status', 1), ('read_exception', True), ('value_type', 7),
                         ('enum_contract_applicable', False), ('enum_contract_valid', False),
                         ('enum_contract_valid', 1)):
            self.assertFalse(reflection_closes_contract('@ohos.example', requirement, dict(row, **{key: bad})))

    def test_tts_exception_only_covers_actual_constant_values_and_existing_alias(self):
        row = dict(name='TTS', read_status=0, read_exception=False, value_type=7,
                   settings_tts_values=SETTINGS_TTS_VALUES, settings_tts_alias_equal=True)
        requirement = dict(name='TTS', kind='namespace')
        self.assertTrue(reflection_closes_contract('@ohos.settings', requirement, row))
        self.assertFalse(reflection_closes_contract('@ohos.other', requirement, row))
        for kind in ('function', 'class', 'variable'):
            self.assertFalse(reflection_closes_contract('@ohos.settings', dict(requirement, kind=kind), row))
        self.assertFalse(reflection_closes_contract('@ohos.settings', requirement,
                                                   dict(row, settings_tts_alias_equal=False)))


if __name__ == '__main__':
    unittest.main()
