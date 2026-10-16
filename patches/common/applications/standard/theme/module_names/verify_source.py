from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/theme'
REVISION='a436a43f1c0948fa12df6d520ec695ae4388a057'
FILES=(('BUILD.gn', '8540390751f1ce9af524b18fa4c56b754daedfe9fe3c37e618c45dca147f2189', '67e2c45df3b190f461122c6869dde30c6a9b5ad428654795082b978e60ab8619'), ('build-profile.json5', 'c04f0d01df54b1aa237b4f5a964f43afc5d82b2a45bdb2c635a37f0a8b5a53a4', '1513415c5497ce6c9dbee3ea7329f207657e12792fc57c42baff0f52d7db8f34'), ('product/phone/src/main/module.json5', 'd6e2a5dc505588688c8c93152715729899832523839fe612cd169868408e830d', '8383e2dfe1a318ecf7bcae82cedb0cf27c6fa5fc4cff28ee4570347776a0120b'), ('product/pad/src/main/module.json5', '5cfd958b00be2df9370e50e732ab4509c01b5e87f53fb9bcb40849930ff20e4f', '40d3c63b856dd0e94af0648734e73ede7ded1bd9555a29c6001a15b7c585815c'))
CRLF_FILES=('applications/standard/theme/product/phone/src/main/module.json5', 'applications/standard/theme/product/pad/src/main/module.json5')
def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
