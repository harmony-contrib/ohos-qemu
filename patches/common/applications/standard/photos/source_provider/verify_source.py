#!/usr/bin/env python3
"""Pin the full Photos source provider stack; guest verification is separate."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/photos'
REVISION = '5d5fcdb4d65010232aca6f389be44e58cf11b18a'
FILES = (
    ('feature/faCard/src/main/ets/formability/FACardServiceStub.ets', '17ea34a321ad227df20eb6919d3d6646131720b76c2eb60c12dc7ad8e2741e16',
     'e2f29d0c8a3d5ba5da0263a0264783a5ef3cc0d8196d72ce810c69d6ff1a28d3'),
    ("build-profile.json5", '8dc98317a2488ffd6f0596f2af8393a408e7b8e91620a490f92580fa3f09ab09',
     'd793355134249659abe3e34d8949d4d5537c51798c7da13dcebcbe39b47804d4'),
    ("hvigor/hvigor-config.json5", '52e3d30029e28ade250e4e86a89a2dd40547db7011eacc5b961c826dcac2883b',
     '5564ce385ae961083dbe5f0e904a7955bbd97795c2eb70227a80712dc5b58a78'),
    ("oh-package.json5", '738bc917387544aeb5e569c9972d428b30f86fe5dbc83cd3a53022e4c135bc2d',
     'b30353de8f561c9bbb9fd90b251bc7e15eb36b5b167fd2b5fd07ebccbf6ae470'),
    ("browserCommon/oh-package.json5", 'fb611cfcee3756c733ab6ce944fdf58d31bbaf01a13177e2869624a00c3eff25',
     'f1444b112d6cacf41d183c478020c93a5381d9df670641306d1c3bef8e6add52'),
    ("imageEditor/common/build-profile.json5", '11ff80a2cef00496e85752722f9d9524d5f629f126acde506d831aa9ec99b21a',
     'f7745bf09b2b7013386b4a7c416a78ffa3efe55aa959996113b3dac40663e8ef'),
    ("imageEditor/common/src/main/cpp/sdk/projects/ohos/CMakeLists.txt", '9caff8018ee968539855a124be28ecb5a1934d9fd1c53b4dc83a8d0db32124b5',
     'bf442ce348bfd6ef7d352566edfd636b428d5de7c4813a8ab133b1aca01dd4d6'),
    ("imageEditor/common/src/main/cpp/sdk/src/Service/Asset/HmcAsset.cpp", '8cdab9f658dd3229db75bb8628758ca686fe949d9d29135c4072ee31045fc60c',
     '6632162626e85303ff44bf2624433dc937bed84dfe7a7eb46bcf5048add24f86'),
    ("common/src/main/ets/default/model/browser/photo/pipeline/ImagePipeline.ets", '7cf1df66f6d7d9c7365b8cbb593261769060fc9c7239ef8c4bbf89d146b216e0',
     '478af5dcc0556838ae92799f565cfcc373b9debe3cb7971e133a717742986e38'),
    ("common/src/main/ets/default/view/dialog/NetworkConnectionSwitchDialog.ets", 'c41600ee85fee454163b2989d9a7068e7f4972b0a009b23f1cd268fcb108ce89',
     'c2111c8b248d542f8e34d15af995609926a562613f59f9fad78f24dec89b5286'),
    ("imageEditor/common/src/main/ets/common/util/BreakPointSystem.ets", 'bd165710a965eb8ffcdbf6d6296ba9e232ac22410c3729871af6890eb414e15c',
     '676559a2baeb06d4a60afe7e572b7f8d6a8e710121fb3390ca2eda654e1f9869'),
    ("bundle.json", '05b8cb4bead8c24b035502e4408843494b16d6bb536032b52a496c34f83ea497',
     '8644d46be733d76ede110adfbfb05e37316cc22a456dee5b741a3052637de151'),
    ("BUILD.gn", None,
     '7f1b6f8831e0b655556921ce52bf80d9bd64991b8b45bf62ad5797ab5a56c5b0'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
