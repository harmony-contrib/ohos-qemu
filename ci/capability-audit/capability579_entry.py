"""Connect fixed package DATA to the original runtime Owner before it starts."""
from pathlib import Path
import sys

from assemble_capability579_inputs import checked_ref, json_ref, require
from export_capability579_from_guest import make_deferred_inputs
from capability578_stage import install_on_original_children

ROOT = Path(__file__).resolve().parents[2]
SOURCE_INPUTS = (
    'capability579_entry.py', 'capability578_stage.py', 'capability578_owned_io.py',
    'capability578_callers.py', 'assemble_capability579_inputs.py',
    'export_capability579_from_guest.py', 'capability579_mms_provider.py',
    'capability579_calendar_integration.py', 'capability579_calendar_owner.py',
)


def install(children, request_ref, *, paired_stage, calendar_phase1, calendar_phase2):
    canonical = ROOT / 'ci/capability-audit'
    for name in SOURCE_INPUTS:
        path = canonical / name
        require(children.policy.sources.get(str(path)) == checked_ref({
            'path': str(path), 'sha256': children.policy.sources.get(str(path))})['sha256'],
            'explicit current source-kit admission required: ' + name)
    for module_name in ('assemble_capability579_inputs', 'export_capability579_from_guest', 'capability578_stage'):
        require(Path(sys.modules[module_name].__file__).resolve() == canonical / (module_name + '.py'),
                'only the fixed canonical capability entry modules may be loaded')
    ref = checked_ref(request_ref)
    require(callable(paired_stage), 'fixed root source-kit paired implementation required')
    require(callable(calendar_phase1) and callable(calendar_phase2),
            'fixed reviewed Calendar phase implementations required')
    value = json_ref(ref)
    require(type(value) is dict and set(value) == {'schema', 'package', 'services', 'native_export',
        'caption_runtime_data', 'caption_product_assets', 'permission_ui', 'recipes_root', 'profile',
        'media579_product_export', 'usb579_product_export', 'telephony579_product_export'} and
        value['schema'] == 'actual-root-capability579-deferred-request/v1',
        'explicit finite package/native/service/caption input DATA required')
    factory = make_deferred_inputs(**{key: item for key, item in value.items() if key != 'schema'})

    def deferred(owner, resources):
        checked_ref(ref)
        require(not hasattr(owner, 'capability579_export_factory'),
                'one fixed package export factory per original Owner required')
        owner.capability579_export_factory = factory
        return factory(owner, resources)

    from capability579_calendar_integration import run_held_phase1, run_after_main

    def held(owner, resources, inputs, **context):
        return run_held_phase1(owner, resources, inputs, phase1=calendar_phase1, **context)

    def after(owner, resources, inputs):
        calendar = run_after_main(owner, resources, inputs, phase2=calendar_phase2)
        paired = paired_stage(owner, resources, inputs)
        return {'schema': 'actual-capability579-post-main-stages/v1', 'calendar': calendar, 'paired': paired,
                'first_artifact_behavior_gate_passed': False}

    install_on_original_children(children, deferred_inputs=deferred, held_stage=held, after_suite=after)
