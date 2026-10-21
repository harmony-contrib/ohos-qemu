"""Original caller builder code, fixed adapter only; no Owner/SDK resource wrapper."""
from pathlib import Path
from types import FunctionType
import capability578_callers as original
import photos579_project as project

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')


def adapter(family, case, run, role, parameters):
    project.require(family == 'apps_providers579' and case == 'photos', 'one fixed restart caller batch')
    project.validate(case, run, role, parameters)
    return project, project.source_files(case, run, role, parameters), project.module_fields(case, role, parameters), project.bundle(case, role)


def prepare_callers(io, family, case, run, roles, parameters):
    project.sources()
    project.require(Path(original.__file__).resolve() == ROOT / 'ci/capability-audit/capability578_callers.py' and
        Path(original.prepare_callers.__code__.co_filename).resolve() == Path(original.__file__) and
        family == 'apps_providers579' and case == 'photos' and roles == project.ROLES['photos'] and run == io.run_id,
        'same original held IO and exact unchanged builder body')
    project.validate(case, run, parameters=parameters)
    namespace = dict(original.prepare_callers.__globals__)
    namespace['adapter'] = adapter
    project.require(all(namespace[key] is value for key, value in original.prepare_callers.__globals__.items()
        if key != 'adapter'), 'every original SDK/sign/command dependency retained')
    body = FunctionType(original.prepare_callers.__code__, namespace, original.prepare_callers.__name__,
        original.prepare_callers.__defaults__, original.prepare_callers.__closure__)
    body.__kwdefaults__ = original.prepare_callers.__kwdefaults__
    result = body(io, family, case, run, roles, parameters)
    from batch_media_knowledge_project import check_sdk
    result['sdk'] = check_sdk(io.owner.config['sdk'], '2in1')
    return result
