"""QEMU-only truthful HDI codec advertisements; software codecs are unchanged."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'vendor/ohemu'
REVISION = 'b56c5a95ec590543691278b85afe9fe228744163'
DIRECTORY = 'virt/hdf_config/uhdf/media_codec/'
FILES = (
    (DIRECTORY + 'media_codec_capabilities.hcs',
     'ad6746ed5b629f83f39da28b2afc89a552e0f369ec746518fa9f55d55b22ac92',
     'a359d96d11cbd2fce21afece11effc04ae7a76cf57ab8c1aeed833d80702fa6e'),
    (DIRECTORY + 'codec_adapter_capabilities.hcs',
     '4f9a587210648e69b6cb6a3fee1d395cf6575acc041a79a6bffcac1e5e7aa1c2',
     'b059c4084a8f4a77719c2f0f30f57604ddbce687354d30f5a7ef71ee786dca32'),
    (DIRECTORY + 'codec_component_capabilities.hcs',
     '0026f214c51e3c02251ead992a9d9a79a55ec9f7036c85c31507e8decb85a405',
     'a359d96d11cbd2fce21afece11effc04ae7a76cf57ab8c1aeed833d80702fa6e'),
    (DIRECTORY + 'codec_hdi1.0_capabilities.hcs',
     'f893297c64a00bd95a52021fafe886b796deed7312f9110fdc778871551bd7cf',
     'f8552993a96e68ff6bc276b4e01cabdbbef3b158e7b5e826d108b4e7efd6d953'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
