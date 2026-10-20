"""Finite source/dependency admission; caller is root's original preparation.

No downloading, tools, build/SDK/VM/process or Owner operations are performed.
License/provenance inputs remain explicit raw artifacts. This is not acceptance.
"""
from pathlib import Path
import hashlib

FIXED = {
 'encoder': ('0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6',12937772),
 'decoder': ('06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527',89853865),
 'tokens': ('306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930',835554),
 'vad': ('a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28',1807522),
}
LICENSES = {'whisper':'b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d',
 'sherpa':'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
 'ort_notices':'d7d726424fc23a8395c139bbc7eb2aefa2b5bb2eb3332ec34ad0442d149d2308'}


def raw(ref):
    if type(ref) is not dict or set(ref) != {'path','sha256'}:
        raise ValueError('exact unchanged original input Ref required')
    path=Path(ref['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('actual regular absolute dependency artifact required')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ref['sha256']:
        raise ValueError('actual admitted dependency bytes changed')
    return data


def product_assets(inputs, abi):
    if abi not in ('arm64-v8a','x86_64','armeabi-v7a') or inputs['language']!='en' or inputs['model']!='whisper-tiny.en':
        raise ValueError('fixed actual English CPU model and OHOS ABI required')
    assets=inputs['assets']
    for name,(sha,size) in FIXED.items():
        data=raw(assets[name])
        if len(data)!=size or assets[name]['sha256']!=sha:
            raise ValueError('actual pinned inference input differs: '+name)
    notices=raw(assets['notices'])
    if len(notices)<100 or len(notices)>2*1024*1024:
        raise ValueError('bounded complete user-visible notices required')
    for name,sha in LICENSES.items():
        data=raw(inputs['licenses'][name])
        if inputs['licenses'][name]['sha256']!=sha or data not in notices:
            raise ValueError('actual complete model/runtime attribution is missing: '+name)
    for name in ('ort','libcxx','silero'):
        if raw(inputs['licenses'][name]) not in notices:
            raise ValueError('actual native/model dependency license absent: '+name)
    har=raw(assets['har'])
    if abi!='armeabi-v7a':
        if assets['har']['sha256']!='d196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0':
            raise ValueError('exact existing actual two-ABI HAR required')
    elif not raw(inputs['ohos32_source_build']) or not har:
        raise ValueError('root-owned genuine OHOS32 source build receipt and real HAR required')
    from livecaptions579_provider_project import asset_destinations
    return {destination: assets[name] for name,destination in asset_destinations().items()}
