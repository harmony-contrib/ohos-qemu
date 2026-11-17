from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/theme'
REVISION='a436a43f1c0948fa12df6d520ec695ae4388a057'
FILES=(('product/phone/build-profile.json5', 'e55404b21d63359a3a5e82b97c207d4dc8cacb54f14554f3e1f353558d788fe3', '93adcb47fbf62829d6235a5163dfccb820596e27e0c17d6f8249f362028b250b'), ('product/pad/build-profile.json5', 'e55404b21d63359a3a5e82b97c207d4dc8cacb54f14554f3e1f353558d788fe3', '93adcb47fbf62829d6235a5163dfccb820596e27e0c17d6f8249f362028b250b'))
CRLF_FILES=('applications/standard/theme/product/phone/build-profile.json5', 'applications/standard/theme/product/pad/build-profile.json5')
def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
