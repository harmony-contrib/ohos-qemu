#!/usr/bin/env python3
"""Allow only a final LF added to fourteen exact Release interface headers."""
import argparse
from pathlib import Path
import subprocess

REVISION = '4237e061441ea9392e83a353c0d52cb1c44404b3'
HEADERS = ('aafwk_browser_host_adapter.h', 'aafwk_browser_client_adapter.h',
    'aafwk_render_scheduler_host_adapter.h', 'aafwk_app_mgr_client_adapter.h',
    'drm_adapter.h', 'keystore_adapter.h', 'media_avsession_adapter.h', 'media_codec_adapter.h',
    'audio_cenc_info_adapter.h', 'ohos_drawing_text_adapter.h', 'ohos_image_decoder_adapter.h',
    'power_mgr_client_adapter.h', 'surface_control_adapter.h', 'sensor_adapter.h')


def check(work, before=False):
    repository = work / 'deps_code/webview'
    if repository.is_symlink() or subprocess.check_output(
            ['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('adapter header formatting requires the exact TPC Release WebView project')
    for name in HEADERS:
        relative = 'ohos_interface/include/ohos_adapter/' + name
        original = subprocess.check_output(['git', '-C', str(repository), 'show', REVISION + ':' + relative])
        path = repository / relative
        if any((repository / Path(*Path(relative).parts[:i])).is_symlink()
                for i in range(1, len(Path(relative).parts) + 1)):
            raise ValueError('aliased adapter source header: ' + name)
        if original.endswith(b'\n') or path.read_bytes() not in (
                (original, original + b'\n') if before else (original + b'\n',)):
            raise ValueError('unknown adapter header content, or missing final LF: ' + name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--before', action='store_true')
    args = parser.parse_args()
    check(args.source_root, args.before)
