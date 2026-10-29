from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/contacts'
REVISION='65de33df8d6d7aaa5797a5625ed0e5938e5cb050'
FILES=(('oh-package.json5', '16115ebec8b27dfc738277ad17f66683e8b06c4638278bc0d54e093ee3c48f6c', 'bd1ffe4f1989bfa951ba9cae9e2fd2118111f4a39eb2f8f5493cc25cbd0d111c'), ('entry/src/main/module.json5', '45337d351839a70185504b0fa2c256e76b68e33d034dea2e530acaee88c48ef7', '7805f32a88ff986a9a9c16fee64a7c7d1ce5cc265397192b5dd90b00b189da0c'))
CRLF_FILES=('applications/standard/contacts/oh-package.json5',)
def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
