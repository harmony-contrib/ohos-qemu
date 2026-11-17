const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
let source=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*?;\r?\n/gm,'').replace('export default class','class');
let controllers=[],closed=0,cancelled=0,disposed=0,loads=[],releaseLoad;
class Controller{constructor(w,c){if(!w.parameters?.dialogSessionId)throw new Error('missing session');this.id=w.parameters.dialogSessionId;controllers.push(this);}async cancel(){cancelled++;}dispose(){disposed++;}}
const stage={loadContent(name,storage){loads.push({name,storage});if(process.argv[3]==='load_error')return Promise.reject(new Error('page'));return new Promise((resolve,reject)=>releaseLoad={resolve,reject});}};
class LocalStorage{constructor(){this.data={};}setOrCreate(k,v){this.data[k]=v;}}
const sandbox={UIAbility:class{constructor(){this.context={async terminateSelf(){closed++;}};}},ChoosePickerController:Controller,LocalStorage,console:{error(){}}};vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\nthis.Ability=ChoosePickerAbility;',sandbox);
(async()=>{const a=new sandbox.Ability();
 if(process.argv[3]==='invalid'){a.onCreate({});await new Promise(r=>setImmediate(r));await a.onWindowStageCreate(stage);assert.equal(closed,1);assert.equal(loads.length,0);}
 else{a.onCreate({parameters:{dialogSessionId:'first'}});
  if(process.argv[3]==='load_error'){await a.onWindowStageCreate(stage);assert.equal(cancelled,1);}
  else if(process.argv[3]==='destroy_loading'){const p=a.onWindowStageCreate(stage);a.onWindowStageDestroy();a.onDestroy();releaseLoad.reject(new Error('late'));await p;assert.equal(cancelled,0);assert.equal(disposed,2);}
  else if(process.argv[3]==='isolated'){const b=new sandbox.Ability();b.onCreate({parameters:{dialogSessionId:'second'}});a.onNewWant({parameters:{dialogSessionId:'injected'}});await new Promise(r=>setImmediate(r));assert.equal(controllers.length,2);assert.equal(controllers[0].id,'first');assert.equal(controllers[1].id,'second');assert.equal(cancelled,1);a.onDestroy();assert.equal(disposed,1);assert.equal(b.onBackPressed(),true);assert.equal(cancelled,2);}
  else{const p=a.onWindowStageCreate(stage);releaseLoad.resolve();await p;assert.equal(loads[0].name,'pages/ChoosePicker');assert.equal(loads[0].storage.data.chooseController,controllers[0]);a.onDestroy();a.onDestroy();assert.equal(disposed,1);}
 }
 console.log('PASS '+process.argv[3]);
})().catch(e=>{console.error(e);process.exitCode=1;});
