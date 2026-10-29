"""Exact JSFramework source pair only; native Linux Mocha/runtime are separate."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'lib'))
from exact_source_states import validate_component
PROJECT = 'third_party/jsframework'
REVISION = 'abb00e2f162379c008b71fbaccd015dce5706322'
FILES = (('test/lib.ts', '7ee212673b59822b0b610d6c1f71b27c88b38816502239f11f8d4fc10140208e', 'd43ca5eebc45c543d1aa007321b67c734680221e78143d5b2c8916bf06c84556'), ('js_framework_build.sh', 'eb195e2f35f0cefa90afdde8571a82a059d88d55e2f756c3518cbf5418635d34', '3f764daec8c916e40adf4a738695c266e80095fa6be3a5fa2c3fb3edd06a5750'))
PATCH = '0001-model-native-compiler-for-host-tests-and-propagate-child-status.patch'
PATCH_SHA256 = 'cbf44b5668dbf51f6b48c7ade66b2bab6cc3e60e86243360de8cdb87bd28626b'
COMPONENT = Path(__file__).resolve().parent
EXPECTED = {'schema': 'jsframework-native-test-bridge-source/v1', 'project': 'third_party/jsframework', 'revision': 'abb00e2f162379c008b71fbaccd015dce5706322', 'files': [{'relative': 'test/lib.ts', 'original_sha256': '7ee212673b59822b0b610d6c1f71b27c88b38816502239f11f8d4fc10140208e', 'final_sha256': 'd43ca5eebc45c543d1aa007321b67c734680221e78143d5b2c8916bf06c84556'}, {'relative': 'js_framework_build.sh', 'original_sha256': 'eb195e2f35f0cefa90afdde8571a82a059d88d55e2f756c3518cbf5418635d34', 'final_sha256': '3f764daec8c916e40adf4a738695c266e80095fa6be3a5fa2c3fb3edd06a5750'}], 'patch': '0001-model-native-compiler-for-host-tests-and-propagate-child-status.patch', 'patch_sha256': 'cbf44b5668dbf51f6b48c7ade66b2bab6cc3e60e86243360de8cdb87bd28626b', 'scope': 'exact two-source Node unit compiler bridge and child status propagation; product runtime/native-only policy and test oracle unchanged', 'actual_linux_mocha_build_runtime_pending': True, 'first_artifact_behavior_gate_passed': False}

def unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate JSFramework exact metadata')
        result[key] = value
    return result

def metadata():
    p = COMPONENT/'source_states.json'
    if p.is_symlink() or not p.is_file():
        raise ValueError('regular exact JSFramework metadata required')
    value = json.loads(p.read_text(),object_pairs_hook=unique)
    if value != EXPECTED:
        raise ValueError('JSFramework exact source metadata differs')
    patches = list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if len(patches)!=1 or patches[0].name!=PATCH or patches[0].is_symlink() or not patches[0].is_file() or hashlib.sha256(patches[0].read_bytes()).hexdigest()!=PATCH_SHA256:
        raise ValueError('JSFramework exact numbered patch differs')
    return value

def validate(root,require_patched=False):
    metadata()
    root = Path(root).resolve()
    for relative,_,_ in FILES:
        p = root/PROJECT/relative
        for parent in (p,*p.parents):
            if parent==root:
                break
            if parent.is_symlink():
                raise ValueError('JSFramework source alias: '+relative)
        if not p.is_file() or p.stat().st_nlink!=1:
            raise ValueError('JSFramework regular unique source required: '+relative)
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--require-patched',action='store_true')
    args=parser.parse_args(argv)
    state=validate(args.source_root,args.require_patched)
    print(json.dumps(dict(scope='exact two-source JSFramework source state only',patched=state,compiled=False,native_linux_mocha_passed=False,runtime_passed=False,first_artifact_behavior_gate_passed=False)))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
