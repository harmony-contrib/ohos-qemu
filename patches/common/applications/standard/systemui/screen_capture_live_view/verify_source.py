#!/usr/bin/env python3
"""Exact fixed SystemUI notification component and read-only prerequisites."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/systemui'
REVISION = 'd0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
FILES = (('features/noticeitem/src/main/ets/com/ohos/noticeItem/common/constants.ts', '7f02b895ada53991fbac489c7963c85855f7f9edc2c369ed5918c8d1e3cfb5ff', 'c5a31fd7967cb7bbf4ed98788a2f212b4c1d4dc05b56dc5bc666af4905b5589f'), ('features/noticeitem/src/main/ets/com/ohos/noticeItem/model/NotificationManager.ts', '6505eea4cc127c806ee24f9b0de2abb45ef5581a33928f503d741e0ae9351124', 'ebfd669682287355eb825d01fe8e4c7839c3b8c5c86e46c11548a9bfe0f5a7af'), ('features/noticeitem/src/main/ets/com/ohos/noticeItem/model/ParseDataUtil.ts', '5eb5b8126460b1f691b7c830e6260179b43a6c6eb610892c3a493dbcb10d76dc', 'a3a5ad8aa28ad217ddec865664fe5d9f33ba18ac3563040cc863b70240dfbe78'), ('features/noticeitem/src/main/ets/com/ohos/noticeItem/model/rule/RuleController.ts', 'effb9c538da5151384c939be04ebb175c6935a1f8097adbe679604f4da8ef1e2', '4da5c1ad52f3dd067565cbad0d7c2b8bc4952c8b1e8cac6dbe8d14cb151f6550'), ('features/noticeitem/src/main/ets/com/ohos/noticeItem/view/item/notificationItem.ets', 'd858b0b04d57e0306260fb4c9ea5aa147a8832b983c9f9c97194333e43b80950', 'c37f4fc6bce40762c6a6c7f1bddb224cc1de4052ff0e52b84f47bd34bf602173'), ('features/noticeitem/src/main/ets/com/ohos/noticeItem/view/item/systemLiveViewItem.ets', None, '37f602a3c6a82a2affec3b9a957c50c28dbb8a853824a92a3fe98edb278b5b34'), ('features/statusbarcomponent/src/main/ets/com/ohos/pages/IconItemComponent.ets', 'cc65d71fe1a683afc0d48e95f43266b2811147376d2e1ea66883f132b400a83c', 'dfac31933d684016b2ca052ec94c34ea22449a7de67276b077b2590a1358d74b'), ('product/phone/statusbar/src/main/ets/pages/index.ets', '8a5b6445797c75a3661bd1181822a2e2435f45da8f7c25cf9987ac9682dcc67d', 'c4c66967ec9ba481d9c806846a352d95621e6686195d410695ae2d0dfe90c202'))
def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
def prerequisites(root):
    root = Path(root).resolve()
    data = json.loads((Path(__file__).parent / 'source_guard.json').read_text())
    if data['schema'] != 'screen-system-live-view578-source/v1':
        raise ValueError('unexpected live-view source guard')
    for row in data['readonly']:
        target = root / row['path']
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('live-view prerequisite contains a symlink')
            cursor = cursor.parent
        if (not target.is_file() or target.stat().st_size != row['bytes'] or
                hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']):
            raise ValueError('live-view prerequisite source differs: ' + row['path'])
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    prerequisites(args.source_root)
