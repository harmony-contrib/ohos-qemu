"""Select the public local NumberIdentity HAP's real directory; no synthetic data."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import stat
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "lib"))
from number_identity_provider import verify as verify_number_profile

PART = 'number_identity'
APP_DIR = '/system/app/com.ohos.numberidentityability'
PROFILE = 'vendor/ohemu/virt/virt_phone_full.json'
INSTALL = 'vendor/ohemu/virt/preinstall-config/install_list.json'
UNINSTALL = 'vendor/ohemu/virt/preinstall-config/uninstall_list.json'
SOURCE_PINS = {'base/telephony/number_identity/AppScope/app.json': '1b7110bab6b3d73824b55ddc486aff09919f37b899aed63354054b8e6dd3d545',
 'base/telephony/number_identity/AppScope/app.json5': '1b7110bab6b3d73824b55ddc486aff09919f37b899aed63354054b8e6dd3d545',
 'base/telephony/number_identity/BUILD.gn': '90c9c001e6981a35e945732ce5439ea69a6b345d89d7420d2fc7eb8516012871',
 'base/telephony/number_identity/bundle.json': '90eeb371e20929ec9364f94fb459b3ce193d96eed672d0a910aa5d2d7802b877',
 'base/telephony/number_identity/entry/src/main/module.json': '0daa69b14f5493cb6a61d0c116453afec040a2c349541889f98e3f5b2ed4d3bf',
 'base/telephony/number_identity/entry/src/main/module.json5': '9b0a2d769cf812b7bd0bc8b1e9e674ccc0fc174762417b138442bfeccc06d8b0',
 'base/telephony/number_identity/entry/build-profile.json5': 'bd223a25fb30f98b5772abe2c575e62ff87f20a2fe42b24c8604e2cc64c51ea7',
 'foundation/ability/ability_runtime/frameworks/native/appkit/app/main_thread.cpp': '3680fd9fb200b103a87bc01d530e0c68deadfac843825354adb4182763618c1e',
 'base/telephony/number_identity/frameworks/js/BUILD.gn': 'f22481dd92bb854a35b194b35f87917a4e5ba906c59be0ed4e2df8b8b4df9f14',
 'base/telephony/number_identity/frameworks/js/src/napi_number_identity.cpp': '28d6466d157bfdb3b115887bab861fa843a82bdc5b0216fbd80bf811217d5756',
 'base/telephony/number_identity/number_location/src/number_identity_datashare_stub_impl.cpp': 'd65b50a71901c8c5302ca548e65a51679dd479486e8e0be4aa79ac184dd55600',
 'base/telephony/number_identity/number_location/src/number_location_ability.cpp': '48bd4bfb2f2df9c0dea5a00ece8d844c61b9027b6bf58adcfe87df59f21bd46b',
 'base/telephony/number_identity/number_mark/src/number_mark_ability.cpp': '781f7bb3b699ee933d32f1c9c790bcc4c9824a8375c5c5e1ac1472f273d52bb8',
 'base/telephony/number_identity/number_mark/src/number_mark_result_set_bridge.cpp': '0c82dcb0349ae38baf581e432b0574aeadd731d97d2e8b085e1b15ea7ccd6230',
 'base/telephony/number_identity/shared/include/number_identity_models.h': 'f0d57770dcd8774e0db12f6ba7c1ae5bc21fb7a8d2f6aa7a899590c79aa3c053'}


def need(ok, message):
    if not ok: raise ValueError(message)


def regular(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and all(not p.is_symlink() for p in (path,*path.parents)), 'canonical unaliased input required')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'single regular file required')
    return path


def decode(data):
    def pairs(rows):
        result = {}
        for name,value in rows:
            need(name not in result, 'duplicate JSON key');result[name]=value
        return result
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def source_pins(root):
    actual = {relative: hashlib.sha256(regular(root/relative).read_bytes()).hexdigest()
              for relative in SOURCE_PINS}
    if actual == SOURCE_PINS:
        return dict(SOURCE_PINS)
    # Accept the successor only after all six loader/provider files authenticate.
    import importlib.util
    guard_path = Path(__file__).resolve().parents[5] / 'common/foundation/ability/ability_runtime/number_identity_native_trace495/verify_source.py'
    need(hashlib.sha256(regular(guard_path).read_bytes()).hexdigest() == 'ce5b65b7fddf75f9aa7c5134ca05145a58c1755c32365e0337ab286104d9515b',
         'fixed whole-sequence guard differs')
    spec = importlib.util.spec_from_file_location('number_selection_trace_guard', guard_path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.preflight_sequence(root, require_patched=True)
    expected = dict(SOURCE_PINS)
    expected.update({'foundation/ability/ability_runtime/frameworks/native/appkit/app/main_thread.cpp': 'ed25c0dd5459e94c802aa9abcfb70baa3aba8110ae8b1f4a4f2ffd0bdb3b4528', 'base/telephony/number_identity/number_location/src/number_identity_datashare_stub_impl.cpp': 'ecc474085ce71a77b641c0d6962554fbb3400683a63ea45e3720feebfc7d6715', 'base/telephony/number_identity/number_location/src/number_location_ability.cpp': '371c44cc4d8387d95092ee1c073e7a6976149b361914c55f0b10eeb89b973dd4'})
    need(actual == expected, 'public local source/config differs from complete successor')
    return expected


def configure(root, require_patched=False):
    root = Path(root)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and not root.is_symlink(), 'canonical real source root required')
    source_pins(root)
    # Original profile SHA is retained by the helper as the immutable baseline.
    # Source package readiness requires the authenticated two-field renewal.
    verify_number_profile(root)
    profile = decode(regular(root/PROFILE).read_bytes());rows=[]
    for subsystem in profile.get('subsystems',[]):
        if subsystem.get('subsystem')=='telephony':
            rows.extend(r for r in subsystem.get('components',[]) if r.get('component')==PART)
    need(len(rows)==1 and rows[0]=={'component':PART,'features':[]}, 'one explicit public NumberIdentity phone part required')
    policy = decode(regular(root/UNINSTALL).read_bytes())
    need(all(type(policy.get(k)) is list and all(type(v) is str for v in policy[k]) for k in ('uninstall_list','recover_list')), 'typed uninstall/recover arrays required')
    need(APP_DIR not in set(policy['uninstall_list'])-set(policy['recover_list']), 'NumberIdentity installation vetoed by explicit uninstall policy')
    path = regular(root/INSTALL);before=path.read_bytes();info=path.stat();document=decode(before);entries=document.get('install_list')
    need(type(entries) is list and all(type(r) is dict for r in entries), 'actual install list required')
    matches=[r for r in entries if r.get('app_dir')==APP_DIR]
    expected={'app_dir':APP_DIR,'removable':False}
    if matches:
        need(len(matches)==1 and set(matches[0])==set(expected) and matches[0]['app_dir']==APP_DIR and matches[0]['removable'] is False, 'unknown, duplicated or incorrectly typed local provider install entry')
        return 'already_applied'
    need(not require_patched, 'public local NumberIdentity HAP preinstall selection missing')
    entries.append(expected);data=(json.dumps(document,indent=2,ensure_ascii=False)+'\n').encode();temporary=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.number-local-',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,stat.S_IMODE(info.st_mode));current=path.stat()
        need(not path.is_symlink() and (info.st_dev,info.st_ino,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink)==
             (current.st_dev,current.st_ino,current.st_mtime_ns,current.st_ctime_ns,current.st_nlink) and path.read_bytes()==before, 'install list changed before publication')
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return 'applied'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--require-patched',action='store_true')
    args=parser.parse_args(argv)
    print(json.dumps({'status':configure(args.source_root,args.require_patched), 'scope':'public local provider selection only', 'guest_passed':False,'aggregate_provider_supported':False}));return 0


if __name__=='__main__':raise SystemExit(main())
