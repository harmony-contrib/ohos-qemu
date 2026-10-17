#!/usr/bin/env python3
"""Create exact two-project modal-share/plain-text-draft candidates from pinned inputs."""
from pathlib import Path
import base64,difflib,gzip,hashlib,json,re
ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'ci/capability-audit/fixtures/batch_apps/share_provider'
meta=json.loads((FIX/'provenance.json').read_text())
original={path:gzip.decompress(base64.b64decode(record['gzip_base64'])).decode() for path,record in meta['files'].items()}
after=dict(original)
settings='applications/standard/settings';mms='applications/standard/mms'
module=settings+'/product/phone/src/main/module.json5';marker='    "extensionAbilities": ['
assert after[module].count(marker)==1
extension={'name':'SharePickerExtensionAbility','srcEntry':'./ets/Setting/SharePicker/SharePickerExtension.ets','type':'sysPicker/share','exported':True,'extensionProcessMode':'instance'}
after[module]=after[module].replace(marker,marker+'\n'+('\n'.join('      '+line for line in json.dumps(extension,indent=2,ensure_ascii=False).splitlines()))+',',1)
profile=settings+'/product/phone/src/main/resources/base/profile/main_pages.json';doc=json.loads(after[profile]);assert 'pages/SharePicker' not in doc['src'];doc['src'].append('pages/SharePicker');after[profile]=json.dumps(doc,indent=2)+'\n'
for filename,relative in [('SharePickerController.ets','Setting/SharePicker/SharePickerController.ets'),('SharePickerExtension.ets','Setting/SharePicker/SharePickerExtension.ets'),('SharePicker.ets','pages/SharePicker.ets')]:
 after[settings+'/product/phone/src/main/ets/'+relative]=(FIX/'candidate'/filename).read_text()
module=mms+'/entry/src/main/module.json5';text=after[module];start=text.index('"name": "com.ohos.mms.MainAbility"');idx=text.index('"skills": [',start)+len('"skills": [');skill={'actions':['ohos.want.action.sendData'],'uris':[{'type':'text/plain'}]};text=text[:idx]+'\n'+('\n'.join('          '+line for line in json.dumps(skill,indent=2).splitlines()))+','+text[idx:];after[module]=text
payload=mms+'/entry/src/main/ets/utils/SendDataPayload.ets';after[payload]=(FIX/'candidate/SendDataPayload.ets').read_text()
util=mms+'/entry/src/main/ets/utils/WantUtil.ets';text=after[util];text=text.replace("import ConversationController from '../pages/conversation/conversationController';", "import ConversationController from '../pages/conversation/conversationController';\nimport promptAction from '@ohos.promptAction';\nimport { SendDataPayload } from './SendDataPayload';")
text=text.replace('export class WantUtil {','export class WantUtil {\n  private shareGeneration: number = 0;')
marker="    GlobalContext.getContext().setObject('abilityWant', null)";assert text.count(marker)==1
text=text.replace(marker,marker+"\n    const generation: number = ++this.shareGeneration;\n    abilityWant.parameters = abilityWant.parameters ?? {};\n    if (this.handlePlainSendData(abilityWant, pageInfos, generation)) {\n      return;\n    }")
idx=text.index('  // deepLink 网页url跳转短信')
text=text[:idx]+'''  private handlePlainSendData(want: AbilityWant, pageInfos: NavPathStack, generation: number): boolean {
    let text: string | undefined;
    try {
      text = SendDataPayload.text(want);
    } catch (error) {
      HiLog.e(TAG, 'Invalid text sendData: ' + (error as Error).message);
      promptAction.showToast({ message: '分享内容无效，未创建消息' });
      return true;
    }
    if (text === undefined) {
      return false;
    }
    // Open the existing recipient/draft UI. Receiving an intent never sends SMS.
    const param = this.buildThirdParam({ content: text });
    DynamicLoader.getInstance().fire('TransmitMsg').then(() => {
      if (generation !== this.shareGeneration) {
        return;
      }
      AppStorage.setOrCreate('isSettingShow', false);
      pageInfos.pushPathByName('TransmitMsg', param);
    }).catch((error: Error) => {
      if (generation === this.shareGeneration) {
        HiLog.e(TAG, 'Cannot open shared-text draft: ' + error.message);
        promptAction.showToast({ message: '无法打开消息草稿，未发送消息' });
      }
    });
    return true;
  }

'''+text[idx:];after[util]=text
previous=ROOT/'ci/capability-audit/fixtures/batch_apps/settings_lifetime_previous'
old_hashes=json.loads((previous/'provenance.json').read_text())['sha256']
for project,component in [(settings,'patches/common/applications/standard/settings/share_picker'),(mms,'patches/common/applications/standard/mms/send_data_text')]:
 dest=ROOT/component;dest.mkdir(parents=True,exist_ok=True);patch='';states=[];upgrade=''
 for path,text in after.items():
  if not path.startswith(project+'/'):continue
  before=original.get(path,'');relative=path[len(project)+1:]
  first=text
  if project==settings and path in old_hashes:
   first=gzip.decompress(base64.b64decode((previous/(Path(path).name+'.gz.b64')).read_bytes())).decode()
   assert hashlib.sha256(first.encode()).hexdigest()==old_hashes[path]
   upgrade+='diff --git a/'+path+' b/'+path+'\n'
   upgrade+=''.join(difflib.unified_diff(first.splitlines(True),text.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
  patch+='diff --git a/'+path+' b/'+path+'\n'
  if path not in original:patch+='new file mode 100644\n'
  for line in difflib.unified_diff(before.splitlines(True),first.splitlines(True),fromfile='a/'+path if path in original else '/dev/null',tofile='b/'+path):patch+=line if line.endswith('\n') else line+'\n\\ No newline at end of file\n'
  states.append((relative,hashlib.sha256(before.encode()).hexdigest() if path in original else None,hashlib.sha256(text.encode()).hexdigest()))
 (dest/'0001-provide-real-modal-sharing-and-text-receiver.patch').write_bytes(patch.encode())
 if upgrade:(dest/'0002-isolate-async-share-session-lifetimes.patch').write_text(upgrade)
 verifier=dest/'verify_source.py'
 if verifier.exists():
  current=verifier.read_text()
  assert "PROJECT = "+repr(project) in current and "REVISION = "+repr(meta['projects'][project]) in current
  updated,count=re.subn(r'^FILES = .*$',lambda _: 'FILES = '+repr(tuple(states)),current,count=1,flags=re.MULTILINE)
  assert count==1
  verifier.write_text(updated)
 else:verifier.write_text('''#!/usr/bin/env python3
"""Fail closed on partial or unknown system sharing edits."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = '''+repr(project)+'\nREVISION = '+repr(meta['projects'][project])+'\nFILES = '+repr(tuple(states))+'''

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
''')
 (dest/'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
meta['patched_sha256']={p:hashlib.sha256(s.encode()).hexdigest() for p,s in after.items()}
meta['added_extension']=extension
(FIX/'provenance.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
