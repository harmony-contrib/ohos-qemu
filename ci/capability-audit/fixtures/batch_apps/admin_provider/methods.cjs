const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const root=process.argv[2],scenario=process.argv[3];
const page=fs.readFileSync(root+'/entry/src/main/ets/pages/applicationInfo.ets','utf8').replaceAll('\r\n','\n');
const detail=fs.readFileSync(root+'/entry/src/main/ets/common/appManagement/appDetailData.ets','utf8').replaceAll('\r\n','\n');
const methods=page.slice(page.indexOf('  async aboutToAppear()'),page.lastIndexOf('}'));
const check=detail.slice(detail.indexOf('  async checkAppItem('),detail.indexOf('  async getBundleInfoItem('));
let active=scenario==='disable'||scenario==='super_admin',superAdmin=scenario==='super_admin';
let calls=[],closes=0,queryMode='normal',writeMode='normal',releaseQuery,releaseWrite,failQuery=false;
const tick=()=>new Promise(r=>setImmediate(r));
const manager={AdminType:{ADMIN_TYPE_NORMAL:0,ADMIN_TYPE_SUPER:1},
 async isAdminEnabled(want){calls.push(['query',want.bundleName]);if(queryMode==='reject')throw new Error('query unavailable');if(queryMode==='defer'){queryMode='normal';return new Promise(r=>releaseQuery=r);}return active;},
 async isSuperAdmin(name){calls.push(['super',name]);return superAdmin;},
 async enableAdmin(want,enterprise,type){calls.push(['enable',want.bundleName,enterprise.name,type]);if(writeMode==='reject')throw new Error('permission denied');if(writeMode==='defer')await new Promise(r=>releaseWrite=r);if(writeMode!=='mismatch')active=true;},
 async disableAdmin(want){calls.push(['disable',want.bundleName]);active=false;}
};
const sandbox={edmEnterpriseDeviceManager:manager,adminManager:manager,baseData:{EMPTY_STR:'',MAX_LEN:255},logger:{info(){},warn(){},error(){}},TAG:'test',appDetailData:{async terminateAbilityPage(){closes++;}},accountManager:{async getAccountUserId(){return true;}},bundle:{ExtensionAbilityType:{ENTERPRISE_ADMIN:1},ExtensionAbilityFlag:{GET_EXTENSION_ABILITY_INFO_WITH_APPLICATION:1},async queryExtensionAbilityInfo(){if(failQuery)throw new Error('missing');return [{}];}},utils:{isValid(x){return x!==undefined&&x!==null;}}};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes('class Page {\n'+methods+'}\nclass Detail {\n'+check+'}\nthis.Page=Page;this.Detail=Detail;', {mode:'transform'}),sandbox);
const request={parameters:{elementName:{bundleName:'com.example.admin',abilityName:'AdminExt'},enterprise:{name:'Example',description:'Real admin'},activeType:0}};
let current=request;
function create(){const p=new sandbox.Page();Object.assign(p,{pageActive:true,requestReady:true,request,storage:{get(){return current;}},elementNameVal:{bundleName:'com.example.admin',abilityName:'AdminExt'},enterInfo:{name:'Example',description:'Real admin'},isShowActive:false,isEnableButton:true,operationPending:false,operationError:''});return p;}
(async()=>{
 const p=create();
 if(scenario==='failed_then_valid_query'){
  const d=new sandbox.Detail();d.ret=true;failQuery=true;assert.equal(await d.checkAppItem(p.elementNameVal),false);failQuery=false;assert.equal(await d.checkAppItem(p.elementNameVal),true);
 }else if(scenario==='cancel'){
  await p.cancelAdmin();assert.equal(closes,1);assert.equal(calls.length,0);p.operationPending=true;await p.cancelAdmin();assert.equal(closes,1);
 }else if(scenario==='new_want_before_write'||scenario==='destroy_before_write'){
  queryMode='defer';const pending=p.activateAdmin(0);await tick();if(scenario==='new_want_before_write')current={...request};else p.aboutToDisappear();releaseQuery(false);await pending;assert.equal(calls.filter(x=>x[0]==='enable').length,0);assert.equal(closes,0);assert.equal(p.operationPending,false);
 }else if(scenario==='new_want_during_write'||scenario==='duplicate'){
  writeMode='defer';const pending=p.activateAdmin(0);await tick();assert.equal(calls.filter(x=>x[0]==='enable').length,1);if(scenario==='new_want_during_write')current={...request};else{await p.activateAdmin(0);await p.cancelAdmin();assert.equal(closes,0);}releaseWrite();await pending;assert.equal(calls.filter(x=>x[0]==='enable').length,1);assert.equal(closes,scenario==='duplicate'?1:0);assert.equal(p.operationPending,false);
 }else{
  if(scenario==='enable_failure')writeMode='reject';if(scenario==='state_mismatch')writeMode='mismatch';if(scenario==='query_failure')queryMode='reject';
  await p.activateAdmin(scenario==='unsupported'?1:0);
  if(scenario==='enable'){assert.equal(active,true);assert.equal(closes,1);assert.equal(calls.filter(x=>x[0]==='enable').length,1);assert.equal(p.operationError,'');}
  else if(scenario==='disable'){assert.equal(active,false);assert.equal(closes,1);assert.equal(calls.filter(x=>x[0]==='disable').length,1);}
  else{assert.equal(closes,0);assert.ok(p.operationError.length>0);if(scenario==='unsupported'||scenario==='super_admin'||scenario==='query_failure')assert.equal(calls.filter(x=>x[0]==='enable'||x[0]==='disable').length,0);}
  assert.equal(p.operationPending,false);
 }
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
