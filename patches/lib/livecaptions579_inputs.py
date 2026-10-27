"""Finite source/dependency admission for Live Captions product preparation."""
from pathlib import Path
import hashlib
import os

FIXED = {
    'encoder': ('0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6', 12937772),
    'decoder': ('06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527', 89853865),
    'tokens': ('306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930', 835554),
    'vad': ('a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28', 1807522),
}
LICENSES = {
    'whisper': 'b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d',
    'sherpa': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'ort_notices': 'd7d726424fc23a8395c139bbc7eb2aefa2b5bb2eb3332ec34ad0442d149d2308',
}
ASSET_DESTINATIONS = {
    'encoder': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-encoder.int8.onnx',
    'decoder': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-decoder.int8.onnx',
    'tokens': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-tokens.txt',
    'vad': 'entry/src/main/resources/rawfile/silero_vad.onnx',
    'notices': 'entry/src/main/resources/rawfile/LIVE_CAPTIONS_NOTICES.txt',
    'har': 'sherpa_onnx-1.11.2.har',
}


def asset_destinations():
    return dict(ASSET_DESTINATIONS)


def _resolve_artifact_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() and path.is_file() and not path.is_symlink():
        return path
    cache_root = Path(os.environ.get('CACHE_ROOT', '/Volumes/PSSD/qemu'))
    lottie_root = cache_root / 'artifacts/livecaptions-lottie-7.0'
    marker = 'issue-20-20261006/'
    if marker in raw_path:
        rel = raw_path.split(marker, 1)[1]
        candidate = lottie_root / rel
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    if not path.is_absolute():
        candidate = (lottie_root / path).resolve()
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return path


def raw(ref):
    if type(ref) is not dict or set(ref) not in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}):
        raise ValueError('exact unchanged original input Ref required')
    path = _resolve_artifact_path(ref['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(f'actual regular absolute dependency artifact required: {ref["path"]}')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref['sha256']:
        raise ValueError('actual admitted dependency bytes changed')
    return data


def product_assets(inputs, abi):
    if abi not in ('arm64-v8a', 'x86_64', 'armeabi-v7a') or inputs['language'] != 'en' or inputs['model'] != 'whisper-tiny.en':
        raise ValueError('fixed actual English CPU model and OHOS ABI required')
    assets = inputs['assets']
    for name, (sha, size) in FIXED.items():
        data = raw(assets[name])
        if len(data) != size or assets[name]['sha256'] != sha:
            raise ValueError('actual pinned inference input differs: ' + name)
    notices = raw(assets['notices'])
    notice_limit = 12 * 1024 * 1024 if abi == 'armeabi-v7a' else 2 * 1024 * 1024
    if len(notices) < 100 or len(notices) > notice_limit:
        raise ValueError('bounded complete user-visible notices required')
    for name, sha in LICENSES.items():
        data = raw(inputs['licenses'][name])
        if inputs['licenses'][name]['sha256'] != sha or data not in notices:
            raise ValueError('actual complete model/runtime attribution is missing: ' + name)
    for name in ('ort', 'libcxx', 'silero'):
        if raw(inputs['licenses'][name]) not in notices:
            raise ValueError('actual native/model dependency license absent: ' + name)
    raw(assets['har'])
    if abi != 'armeabi-v7a':
        if assets['har']['sha256'] != 'd196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0':
            raise ValueError('exact existing actual two-ABI HAR required')
    else:
        from livecaptions579_arm32_contract import admit
        admit(inputs)
    return {destination: assets[name] for name, destination in asset_destinations().items()}
