const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
let loads=[],results=[],release,rejectLoad;
class Storage{constructor(){this.data=new Map();}setOrCreate(k,v){this.data.set(k,v);}get(k){return this.data.get(k);}}
const code=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*?;\r?\n/gm,'').replace('export default class','class');
class Controller{constructor(want){if(want.bad)throw new Error('invalid');this.want=want;this.disposed=false;}dispose(){this.disposed=true;}}
const sandbox={UIExtensionAbility:class{},SharePickerController:Controller,LocalStorage:Storage,console};vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(code,{mode:'transform'})+'\nthis.Extension=SharePickerExtension;',sandbox);
const scenario=process.argv[3];
function session(){return{async loadContent(path,storage){loads.push([this,path,storage]);if(scenario==='load_failure')throw new Error('UI failed');if(scenario==='destroy_while_loading')return new Promise((a,b)=>{release=a;rejectLoad=b;});},async terminateSelfWithResult(result){results.push([this,result]);}};}
(async()=>{
 const e=new sandbox.Extension(),a=session(),b=session();
 if(scenario==='isolated'){
  await e.onSessionCreate({text:'first'},a);await e.onSessionCreate({text:'second'},b);assert.notEqual(loads[0][2],loads[1][2]);const ca=loads[0][2].get('shareController'),cb=loads[1][2].get('shareController');e.onSessionDestroy(a);assert.equal(ca.disposed,true);assert.equal(cb.disposed,false);e.onDestroy();assert.equal(cb.disposed,true);assert.equal(e.sessions.size,0);assert.equal(e.opened.size,0);
 }else if(scenario==='invalid_duplicate'){
  await e.onSessionCreate({bad:true},a);await e.onSessionCreate({bad:true},a);assert.equal(loads.length,0);assert.equal(results.length,1);assert.equal(results[0][1].resultCode,401);e.onSessionDestroy(a);assert.equal(e.opened.size,0);
 }else if(scenario==='load_failure'){
  await e.onSessionCreate({},a);assert.equal(results.length,1);assert.equal(results[0][1].resultCode,16000050);assert.equal(e.sessions.size,0);assert.equal(loads[0][2].get('shareController').disposed,true);
 }else if(scenario==='destroy_while_loading'){
  const pending=e.onSessionCreate({},a);e.onSessionDestroy(a);rejectLoad(new Error('host gone'));await pending;assert.equal(results.length,0);assert.equal(loads[0][2].get('shareController').disposed,true);
 }else throw new Error(scenario);
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
