"""Execute the patched environment-owned classes; not packaged-device evidence."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections
from test_tiff_dng_class_exports import STUB, MAIN

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/observer_info_classes'


class ObserverInfoClassTests(unittest.TestCase):
    def test_actual_class_code_environment_cleanup_reuse_and_failures(self):
        sections = patch_sections(COMPONENT / '0001-export-real-density-and-breakpoint-info-classes.patch')
        target = next(name for name in sections if name.endswith('/ui_observer_listener.cpp'))
        added = '\n'.join('\n'.join(after) for _, _, after in sections[target])
        actual = added.split('namespace {\nstruct ObserverInfoConstructors', 1)[1]
        actual = 'namespace {\nstruct ObserverInfoConstructors' + actual.split(
            '\nnamespace {\nconstexpr char NAV_BAR', 1)[0]
        replacements = {
            'MetadataNapi::InitRecordMetadata': 'InitObserverInfoClasses',
            'CreateRecordMetadata': 'CreateObserverInfo',
            'RecordMetadataConstructor': 'ObserverInfoConstructor',
            'recordConstructors': 'observerInfoConstructors',
            'DngMetadata': 'DensityInfo', 'TiffMetadata': 'WindowSizeLayoutBreakpointInfo',
        }
        main = MAIN
        for old, new in replacements.items(): main = main.replace(old, new)
        stub = STUB.replace('struct MetadataNapi { static Value* InitRecordMetadata(Env*, Value*); };',
                            'Value* InitObserverInfoClasses(Env*, Value*);')
        compile_run(stub + actual + main, language='c++')

    def test_density_uses_real_current_context_not_synthetic_object(self):
        sections = patch_sections(COMPONENT / '0001-export-real-density-and-breakpoint-info-classes.patch')
        dispatcher = '\n'.join('\n'.join(after) for name, hunks in sections.items()
                               if name.endswith('/ui_observer.cpp') for _, _, after in hunks)
        listener = '\n'.join('\n'.join(after) for name, hunks in sections.items()
                             if name.endswith('/ui_observer_listener.cpp') for _, _, after in hunks)
        self.assertIn('auto context = GetContextValue();', dispatcher)
        self.assertIn('OnDensityChange, density, context)', dispatcher)
        self.assertIn('IsNullOrUndefined(env_, context)', listener)
        self.assertIn('napi_set_named_property(env_, objValue, "context", context) == napi_ok', listener)
        self.assertIn('CreateObserverInfo(env_, true)', listener)
        self.assertIn('CreateObserverInfo(env_, false)', listener)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${OBSERVER_INFO_CLASSES_COMPONENT_SCRIPT}" --source-root'), 1)


if __name__ == '__main__': unittest.main()
