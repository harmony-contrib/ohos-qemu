#!/usr/bin/env python3
"""Fail closed on partial or unknown system sharing edits."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/mms'
REVISION = '26df98e3738f4219aa45efe6a3e7f6b1be55c051'
FILES = (('entry/src/main/ets/MainAbility/MainAbility.ets', '52302643f006cca7ec787006ace9ca17bf4c51e5b4f8f8ddec52bd6e46b27371', '3ee269a4106c98c26cf09213a6411ec3934a4af6ffd0cea4fd0ed42d67855abf'), ('entry/src/main/ets/pages/conversation/conversationController.ets', 'dcec0ff4f0176af281fe2f864fdf78f1edeac2826e5bab99cb1ae83e70d3dc3c', '350d1484df2f21610793a2e40608837692ab3f113aa6220e947e0fc7d3e5c4de'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgController.ets', '02b16a9c5bec95dd92eed21803d1825901e9f6230df3078da76308f45f018a94', 'ea702caeb33e400ffd8104a113e32a624e11d44e5baa68cbdd57d21878ec9876'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgPage.ets', '669be49892acb9c72d6b5f43a5d2be678579a982908ef320487ec568bb6c7b72', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f'), ('entry/src/main/ets/utils/SendDataAttachment.ets', None, '311e253e1c34b0819b9319070681b75419ec438033d20f71b27dc55fab05d273'), ('entry/src/main/ets/utils/SendDataPayload.ets', None, 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa'), ('entry/src/main/ets/utils/WantUtil.ets', 'e80c63b3e30ab9baa1daa4189909df523a6b65adc26a7fdf30350083983a74fa', 'd176254730825164da791cfa18f5a260e19d75061058a852b9b058fc0268a1a3'), ('entry/src/main/module.json5', '67c6b55f3817af6f9bfab4f8696cf18766b9e07e821b44dbe60417aa215b8b51', 'f95d349f88e48ad35e9a354d2fc150a4d7c3624df253f6a3733c1da372e1d7ce'))

LEGACY_FILES = (('entry/src/main/ets/MainAbility/MainAbility.ets', '52302643f006cca7ec787006ace9ca17bf4c51e5b4f8f8ddec52bd6e46b27371', '3ee269a4106c98c26cf09213a6411ec3934a4af6ffd0cea4fd0ed42d67855abf'), ('entry/src/main/ets/pages/conversation/conversationController.ets', 'dcec0ff4f0176af281fe2f864fdf78f1edeac2826e5bab99cb1ae83e70d3dc3c', '350d1484df2f21610793a2e40608837692ab3f113aa6220e947e0fc7d3e5c4de'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgController.ets', '02b16a9c5bec95dd92eed21803d1825901e9f6230df3078da76308f45f018a94', 'ea702caeb33e400ffd8104a113e32a624e11d44e5baa68cbdd57d21878ec9876'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgPage.ets', '669be49892acb9c72d6b5f43a5d2be678579a982908ef320487ec568bb6c7b72', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f'), ('entry/src/main/ets/utils/SendDataAttachment.ets', None, '311e253e1c34b0819b9319070681b75419ec438033d20f71b27dc55fab05d273'), ('entry/src/main/ets/utils/SendDataPayload.ets', 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa', 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa'), ('entry/src/main/ets/utils/WantUtil.ets', '9c4bddf3b65cc57e909e38527f5ce92927fa4219c5141d39451f4cad5f063eda', 'd176254730825164da791cfa18f5a260e19d75061058a852b9b058fc0268a1a3'), ('entry/src/main/module.json5', '67ce57d6262cffd662be30497c9bdcd60be1acef87418c04801de6623438187f', 'f95d349f88e48ad35e9a354d2fc150a4d7c3624df253f6a3733c1da372e1d7ce'))

# Complete previous attachment component only; individual old/new file mixtures reject.
PREVIOUS_FILES = (('entry/src/main/ets/MainAbility/MainAbility.ets', '3ee269a4106c98c26cf09213a6411ec3934a4af6ffd0cea4fd0ed42d67855abf', '3ee269a4106c98c26cf09213a6411ec3934a4af6ffd0cea4fd0ed42d67855abf'), ('entry/src/main/ets/pages/conversation/conversationController.ets', '350d1484df2f21610793a2e40608837692ab3f113aa6220e947e0fc7d3e5c4de', '350d1484df2f21610793a2e40608837692ab3f113aa6220e947e0fc7d3e5c4de'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgController.ets', 'ea702caeb33e400ffd8104a113e32a624e11d44e5baa68cbdd57d21878ec9876', 'ea702caeb33e400ffd8104a113e32a624e11d44e5baa68cbdd57d21878ec9876'), ('entry/src/main/ets/pages/transmitmsg/transmitMsgPage.ets', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f'), ('entry/src/main/ets/utils/SendDataAttachment.ets', '72f32087061d1731649d7b5bab26bbbc6e726e11c1bf4407681b59cec26268c3', '72f32087061d1731649d7b5bab26bbbc6e726e11c1bf4407681b59cec26268c3'), ('entry/src/main/ets/utils/SendDataPayload.ets', 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa', 'd0acb0b25a2d9f8f7553cb14c8732d8eab8b7e5ae9c59b7811a533bfeb9522fa'), ('entry/src/main/ets/utils/WantUtil.ets', '3924357e0dadb41cd3fc87d9204a9f6000a0504e0f64110da1e495ae694fbb43', '3924357e0dadb41cd3fc87d9204a9f6000a0504e0f64110da1e495ae694fbb43'), ('entry/src/main/module.json5', 'f95d349f88e48ad35e9a354d2fc150a4d7c3624df253f6a3733c1da372e1d7ce', 'f95d349f88e48ad35e9a354d2fc150a4d7c3624df253f6a3733c1da372e1d7ce'))

def state(root):
    try:
        return 'final' if validate_component(root, PROJECT, REVISION, FILES) else 'original'
    except ValueError as original_error:
        try:
            validate_component(root, PROJECT, REVISION, PREVIOUS_FILES, require_patched=True)
        except ValueError:
            pass
        else:
            return 'previous_attachment'
        try:
            present = [(name, expected, expected) for name, expected, _ in LEGACY_FILES if expected is not None]
            validate_component(root, PROJECT, REVISION, present, require_patched=True)
            root_path = Path(root).resolve()
            for name, expected, _ in LEGACY_FILES:
                if expected is not None:
                    continue
                target = root_path / PROJECT / name
                cursor = target
                while cursor != root_path:
                    if cursor.is_symlink():
                        raise ValueError('legacy MMS input contains a symlink')
                    cursor = cursor.parent
                if target.exists():
                    raise ValueError('legacy MMS new attachment helper must be absent')
        except ValueError:
            raise original_error
        return 'legacy_text'

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
