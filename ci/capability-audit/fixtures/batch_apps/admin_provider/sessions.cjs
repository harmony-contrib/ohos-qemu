const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const root=process.argv[2],scenario=process.argv[3],tick=()=>new Promise(r=>setImmediate(r));
const extension=fs.readFileSync(root+'/entry/src/main/ets/MainAbility/UIExtensionAbility.ets','utf8');
const deploy=fs.readFileSync(root+'/entry/src/main/ets/pages/component/deployComponent.ets','utf8');
const declarations=extension.slice(extension.indexOf('interface ProvisionAdmin')).replace('export default class','class');
const methods=deploy.slice(deploy.indexOf('  aboutToAppear()'),deploy.lastIndexOf('}'));
let configuration={admin_info:[{admin:{bundleName:'example.admin',abilityName:'AdminExt'},admin_type:'SDA'}],enterprise_info:{organization_name:'Example',description:'Managed'}};
let configMode='normal',configRelease,writeMode='normal',writeRelease,active=false,writes=0,storage;
class Storage{constructor(){this.data=new Map();}setOrCreate(k,v){this.data.set(k,v);}get(k){return this.data.get(k);}clear(){this.data.clear();}static getShared(){return storage;}}
const manager={AdminType:{ADMIN_TYPE_NORMAL:0,ADMIN_TYPE_SUPER:1},async isAdminEnabled(){return active;},async enableAdmin(){writes++;if(writeMode==='reject')throw new Error('denied');if(writeMode==='defer')await new Promise(r=>writeRelease=r);if(writeMode!=='mismatch')active=true;}};
const sandbox={UIExtensionAbility:class{},LocalStorage:Storage,TAG:'test',logger:{error(){},info(){}},baseData:{ENABLE_ADMIN_FAILED:102,OOBE_NEXT_STEP_CODE:100,OOBE_PRE_STEP_CODE:101},configPolicy:{getOneCfgFile(){if(configMode==='reject')return Promise.reject(new Error('missing config'));if(configMode==='defer')return new Promise(r=>configRelease=r);return Promise.resolve('etc/edm/edm_provision_config.json');}},fs:{readTextSync(){return JSON.stringify(configuration);}},adminManager:manager};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(declarations+'\nclass Deploy {\n'+methods+'}\nthis.Extension=AutoDeployAbility;this.Deploy=Deploy;',{mode:'transform'}),sandbox);
function session(){return{loads:[],results:[],failDelivery:false,async loadContent(path,store){this.loads.push([path,store]);},async terminateSelfWithResult(result){this.results.push(result.resultCode);if(this.failDelivery)throw new Error('host unavailable');}};}
(async()=>{
 if(scenario.startsWith('extension_')){
  const ext=new sandbox.Extension(),s=session();
  if(scenario==='extension_missing')configMode='reject';
  if(scenario==='extension_invalid')configuration={admin_info:[],enterprise_info:{}};
  if(scenario==='extension_type')configuration.admin_info[0].admin_type='unsupported';
  if(scenario==='extension_destroyed'){
   configMode='defer';const pending=ext.onSessionCreate({},s);ext.onSessionDestroy(s);configRelease('config');await pending;assert.equal(s.loads.length,0);assert.equal(s.results.length,0);
  }else if(scenario==='extension_isolated'){
   const other=session();await Promise.all([ext.onSessionCreate({},s),ext.onSessionCreate({},other)]);assert.equal(s.loads.length,1);assert.equal(other.loads.length,1);assert.notEqual(s.loads[0][1],other.loads[0][1]);assert.equal(s.loads[0][1].get('session'),s);assert.equal(other.loads[0][1].get('session'),other);ext.onDestroy();assert.equal(ext.sessions.size,0);
  }else{
   await ext.onSessionCreate({},s);
   if(scenario==='extension_success'||scenario==='extension_duplicate'){assert.equal(s.loads.length,1);assert.equal(s.results.length,0);assert.equal(s.loads[0][1].get('adminType'),1);if(scenario==='extension_duplicate'){await ext.onSessionCreate({},s);assert.equal(s.loads.length,1);}}
   else{assert.equal(s.loads.length,0);assert.deepEqual(s.results,[102]);}
  }
  assert.equal(writes,0);
 }else{
  storage=new Storage();const s=session();storage.setOrCreate('adminInfo',{bundleName:'example.admin',abilityName:'AdminExt'});storage.setOrCreate('enterpriseInfo',{name:'Example',description:'Managed'});storage.setOrCreate('adminType',1);storage.setOrCreate('session',s);
  const d=new sandbox.Deploy();Object.assign(d,{pageActive:false,sessionFinished:false,operationPending:false});d.aboutToAppear();assert.equal(writes,0);
  if(scenario==='deploy_missing')d.abilityInfo=undefined;
  if(scenario==='deploy_failed')writeMode='reject';if(scenario==='deploy_mismatch')writeMode='mismatch';
  if(scenario==='deploy_cancel'){await d.terminateAbility(101);assert.deepEqual(s.results,[101]);assert.equal(writes,0);await d.EnableAdmin();assert.equal(writes,0);}
  else if(scenario==='deploy_duplicate'||scenario==='deploy_destroyed'){
   writeMode='defer';const pending=d.EnableAdmin();await tick();assert.equal(writes,1);await d.EnableAdmin();await d.terminateAbility(101);assert.equal(s.results.length,0);if(scenario==='deploy_destroyed')d.aboutToDisappear();writeRelease();await pending;assert.equal(writes,1);assert.deepEqual(s.results,scenario==='deploy_destroyed'?[]:[100]);
  }else if(scenario==='deploy_delivery_retry'){
   s.failDelivery=true;await d.EnableAdmin();assert.equal(writes,1);assert.deepEqual(s.results,[100]);s.failDelivery=false;await d.EnableAdmin();assert.equal(writes,1);assert.deepEqual(s.results,[100,100]);
  }else{
   await d.EnableAdmin();assert.equal(d.operationPending,false);
   if(scenario==='deploy_success'){assert.equal(writes,1);assert.deepEqual(s.results,[100]);await d.EnableAdmin();assert.equal(writes,1);assert.equal(s.results.length,1);}
   else{assert.deepEqual(s.results,[102]);assert.equal(writes,scenario==='deploy_missing'?0:1);}
  }
 }
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
