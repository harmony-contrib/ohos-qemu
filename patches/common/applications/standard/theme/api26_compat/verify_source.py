from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT='applications/standard/theme'
REVISION='a436a43f1c0948fa12df6d520ec695ae4388a057'
FILES=(('product/phone/src/main/module.json5', '8383e2dfe1a318ecf7bcae82cedb0cf27c6fa5fc4cff28ee4570347776a0120b', 'ecbfc51a2d30c4b4581a1eb5f463f822f5270a0438b7b91faa52b0565f795ebf'), ('product/phone/src/main/ets/Application/AbilityStage.ts', '496469245077084ef3f046e7ebe8460e21fa28bdf4dae4f4798536c2a6806b18', '20d1bd91dd42c6f282140978749ed3050e33d1f374fbdcce58bcc248f380754d'), ('product/pad/src/main/ets/Application/AbilityStage.ts', '496469245077084ef3f046e7ebe8460e21fa28bdf4dae4f4798536c2a6806b18', '20d1bd91dd42c6f282140978749ed3050e33d1f374fbdcce58bcc248f380754d'))
CRLF_FILES=('applications/standard/theme/product/phone/src/main/module.json5',)
def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)
