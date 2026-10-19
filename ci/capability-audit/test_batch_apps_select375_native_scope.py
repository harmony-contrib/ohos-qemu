"""Execute extracted native predicates with explicit host values, not native IPC."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from batch_apps_select375_fixture import COMPONENT, installer, materialize


def condition(source, start):
    begin = source.index('(', source.index(start))
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == '(') - (source[end] == ')')
        end += 1
    return source[begin + 1:end - 1]


class NativeScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='select375-native-source-')
        cls.root = Path(cls.temp.name).resolve()
        materialize(cls.root)
        cls.install = installer()
        with mock.patch.object(cls.install, 'revisions'):
            cls.install.apply(cls.root)
        base = cls.root / cls.install.NATIVE / 'services/abilitymgr'
        cls.ams = (base / 'src/ability_manager_service.cpp').read_text()
        cls.manager = (base / 'src/dialog_session/dialog_session_manager.cpp').read_text()
        cls.header = (base / 'include/dialog_session/dialog_session_manager.h').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def node(self, script):
        result = subprocess.run(['node', '--unhandled-rejections=strict', '-e', script],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_request_tuple_predicate_normal_and_all_identity_rejections(self):
        expression = condition(self.manager, 'if (owner->startAdmitted')
        expression = expression.replace('->', '.').replace('nullptr', 'null')
        expression = expression.replace('std::chrono::steady_clock::now()', 'now')
        expression = expression.replace('AppExecFwk::AbilityType::PAGE', 'PAGE')
        # Keep the extracted C++ boolean operators and every comparison. All
        # values model strongly typed native fields; no arbitrary coercion used.
        script = '''const assert=require('node:assert/strict');
const PAGE='PAGE', DIALOG_SESSION_ID='dialogSessionId';
const nativeString=value=>({empty:()=>value.length===0});
function fixture(){
 const owner={startAdmitted:false,committed:false,busy:false,pid:-1,dialogToken:null,expiresAt:100,
  sourceUserId:100,bundleName:'com.ohos.settings',moduleName:'phone',abilityName:'PickerDialog',uid:20010001,tokenId:77};
 const origin={callerToken:'real-original-token',requestCode:41,userId:100,callerAccessTokenId:88};
 const caller={callerToken:origin.callerToken,requestCode:41,userId:100,callerAccessTokenId:88};
 const record={IsTerminating:()=>false,GetOwnerMissionUserId:()=>100,GetApplicationInfo:()=>({accessTokenId:88})};
 const target={callerToken:null,requestCode:-1,specifyTokenId:0,specifiedFullTokenId:0,userId:-1,
  want:{GetStringParam:()=> 'legacy_picker_1_2_3_4',GetDeviceIdRef:()=>nativeString(''),GetActionRef:()=>nativeString('')},
  abilityInfo:{type:PAGE,visible:false,bundleName:owner.bundleName,moduleName:'phone',name:'PickerDialog',applicationInfo:{uid:owner.uid,accessTokenId:77}},
  appInfo:{isSystemApp:true,enabled:true,uid:owner.uid,accessTokenId:77}};
 return {owner,origin,caller,record,target,id:'legacy_picker_1_2_3_4',now:99,requestedUserId:100};
}
'''
        script += 'function valid({owner,origin,caller,record,target,id,now,requestedUserId}){return !(' + expression + ');}\n'
        script += '''assert.equal(valid(fixture()),true);
const mutations=[
 x=>x.id='forged-session',x=>x.owner.startAdmitted=true,x=>x.owner.committed=true,
 x=>x.owner.busy=true,x=>x.owner.pid=123,x=>x.owner.dialogToken='attached',x=>x.now=100,
 x=>x.record=null,x=>x.record.IsTerminating=()=>true,x=>x.origin.callerToken=null,
 x=>x.caller.callerToken='wrong-caller',x=>x.caller.requestCode=42,x=>x.caller.userId=0,
 x=>x.owner.sourceUserId=0,x=>x.record.GetOwnerMissionUserId=()=>0,
 x=>x.caller.callerAccessTokenId=89,x=>x.record.GetApplicationInfo=()=>({accessTokenId:89}),
 x=>x.target.callerToken='direct-start-caller',x=>x.target.requestCode=1,
 x=>x.target.specifyTokenId=88,x=>x.target.specifiedFullTokenId=88,
 x=>x.requestedUserId=0,x=>x.requestedUserId=-1,
 x=>x.target.want.GetDeviceIdRef=()=>nativeString('remote'),x=>x.target.want.GetActionRef=()=>nativeString('select'),
 x=>x.target.abilityInfo.type='SERVICE',x=>x.target.abilityInfo.visible=true,
 x=>x.target.appInfo.isSystemApp=false,x=>x.target.appInfo.enabled=false,
 x=>x.target.abilityInfo.bundleName='fake',x=>x.target.abilityInfo.moduleName='other',
 x=>x.target.abilityInfo.name='other',x=>x.target.appInfo.uid=20010002,
 x=>x.target.appInfo.accessTokenId=78,x=>x.target.abilityInfo.applicationInfo.uid=0,
 x=>x.target.abilityInfo.applicationInfo.accessTokenId=78];
for(const change of mutations){const x=fixture();change(x);assert.equal(valid(x),false,String(change));}
// Exact admitted request cannot be reused by a callback before UI attachment.
const x=fixture();assert.equal(valid(x),true);x.owner.startAdmitted=true;assert.equal(valid(x),false);
'''
        self.node(script)

    def test_real_process_predicate_excludes_uid_only_and_reentry(self):
        expression = condition(self.ams, 'if (previous_ != nullptr || consumed_')
        translations = {
            'previous_': 's.previous', 'consumed_': 's.consumed', 'nullptr': 'null',
            'IPCSkeleton::GetCallingUid()': 's.uid', 'IPCSkeleton::GetCallingPid()': 's.pid',
            'IPCSkeleton::GetCallingTokenID()': 's.token',
            'static_cast<uint32_t>(IPCSkeleton::GetSelfTokenID())': 's.selfToken',
            'getuid()': 's.selfUid', 'getpid()': 's.selfPid', 'FOUNDATION_UID': '5523',
            'PermissionVerification::GetInstance()->CheckSpecificSystemAbilityAccessPermission("foundation")': 's.nativeFoundationToken',
        }
        for old, new in translations.items():
            expression = expression.replace(old, new)
        self.node('''const assert=require('node:assert/strict');
const fixture=()=>({previous:null,consumed:false,uid:5523,selfUid:5523,pid:123,selfPid:123,
 token:99,selfToken:99,nativeFoundationToken:true});
const valid=s=>!(''' + expression + ''');
assert.equal(valid(fixture()),true);
for(const [key,value] of [['previous',{}],['consumed',true],['uid',1000],['selfUid',1000],
 ['pid',124],['selfPid',124],['token',0],['token',100],['selfToken',100],['nativeFoundationToken',false]]){
 const s=fixture();s[key]=value;assert.equal(valid(s),false,key);
}
''')

    def test_request_scoped_raii_and_no_global_permission_change(self):
        self.assertIn('static thread_local LegacyPickerStartScope *current_', self.ams)
        self.assertIn('const AbilityRequest &origin_', self.ams)
        self.assertIn('LegacyPickerStartScope(const LegacyPickerStartScope &) = delete', self.ams)
        self.assertIn('~LegacyPickerStartScope()\n    {\n        current_ = previous_;', self.ams)
        self.assertEqual(self.ams.count('LegacyPickerStartScope startScope(id, request);'), 1)
        show = self.ams[self.ams.index('int32_t AbilityManagerService::ShowPickerDialog('):]
        self.assertLess(show.index('LegacyPickerStartScope::Current() != nullptr'), show.index('CreateLegacyPickerSession'))
        self.assertLess(show.index('LegacyPickerStartScope startScope(id, request);'), show.index('IN_PROCESS_CALL(StartAbility(dialog'))
        self.assertIn('!isSelector && specifyTokenId == 0 && !isCallByShortcut && !isFreeInstallFromService', self.ams)
        self.assertIn('!found->second->startAdmitted || !IsLegacyPickerOwner(*found->second, false)', self.manager)
        self.assertIn('owner->startAdmitted = true;', self.manager)
        self.assertIn('consumed_ = true;', self.ams)
        self.assertNotIn('SupportSystemAbilityPermission::SUPPORTED_UIDS', self.ams)
        self.assertIn('bool startAdmitted = false;', self.header)

    def test_real_start_user_is_explicit_before_request_user_assignment(self):
        begin = self.ams.index('int AbilityManagerService::StartAbilityInner(StartAbilityWrapParam &param)')
        inner = self.ams[begin:]
        self.assertIn('int32_t oriValidUserId = GetValidUserId(param.userId);', inner)
        self.assertIn('param.isFreeInstallFromService, oriValidUserId);', inner)
        # The actual producer assigns request.userId only AFTER its permission
        # call; a host fixture that sets it to 100 would hide a real rejection.
        self.assertLess(inner.index('param.isFreeInstallFromService, oriValidUserId);'),
                        inner.index('abilityRequest.userId = validUserId;'))
        self.assertIn('pickerScope->Consume(abilityRequest, requestedUserId)', self.ams)
        self.assertIn('AdmitLegacyPickerStart(id_, origin_, target, requestedUserId)', self.ams)
        self.assertIn('requestedUserId < 0 || requestedUserId != origin.userId', self.manager)
        self.assertNotIn('target.userId != origin.userId', self.manager)
        ams_header = (self.root / self.install.NATIVE /
                      'services/abilitymgr/include/ability_manager_service.h').read_text()
        self.assertEqual(ams_header.count('int32_t requestedUserId = -1'), 3)

    def test_actual_current_support_header_does_not_grant_foundation_generically(self):
        support = self.root / self.install.NATIVE / 'services/common/include/support_system_ability_permission.h'
        source = support.read_text()
        whitelist = source.split('SUPPORTED_UIDS{', 1)[1].split('};', 1)[0]
        self.assertNotIn('5523', whitelist)
        self.assertIn('IPCSkeleton::GetCallingUid()) != SUPPORTED_UIDS.end()', source)


if __name__ == '__main__':
    unittest.main()
