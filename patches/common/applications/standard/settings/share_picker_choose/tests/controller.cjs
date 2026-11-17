// Execute the actual candidate ETS methods. Platform services are explicit
// host doubles; these checks do not prove an ArkTS build or native delegation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const source=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*?;\r?\n/gm,'').replace(/export (class|interface)/g,'$1');
const scenario=process.argv[3],id='legacy_picker_1_2_3_4',other='legacy_picker_5_6_7_8';
const target=(name,extra={})=>({bundleName:'receiver.'+name,moduleName:'entry',abilityName:name,visible:true,appIndex:0,...extra});
let infos=[target('one'),target('one'),target('hidden',{visible:false}),target('clone',{appIndex:1}),target('two')];
let sends=[],gets=[],closes=[],sendMode='normal',getMode='normal',labelMode='normal',closeMode='normal',releaseSend,releaseLabel;
const dialogSession={getDialogSessionInfo(s){gets.push(s);if(getMode==='throw')throw new Error('invalid owner/session');return {targetAbilityInfos:infos};},sendDialogResult(s,w,a){sends.push({id:s,want:w,allowed:a});if(sendMode==='throw')throw new Error('sync native error');if(sendMode==='reject')return Promise.reject(new Error('native error'));if(sendMode==='stale')return Promise.reject(new Error('target no longer matches'));if(sendMode==='defer')return new Promise(r=>releaseSend=r);return Promise.resolve();}};
const bundleManager={getAbilityLabel(b,m,n){if(labelMode==='reject')return Promise.reject(new Error('resource unavailable'));if(labelMode==='defer')return new Promise(r=>releaseLabel=r);return Promise.resolve(n+' label');}};
const context={terminateSelf(){closes.push('close');if(closeMode==='reject')return Promise.reject(new Error('close error'));return Promise.resolve();}};
const sandbox={dialogSession,bundleManager};vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\nthis.Controller=ChoosePickerController;',sandbox);
const create=(want={parameters:{dialogSessionId:id}})=>new sandbox.Controller(want,context),tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 if(scenario==='invalid_session'){
  for(const want of [{},{parameters:{}},{parameters:{dialogSessionId:7}},{parameters:{dialogSessionId:''}},{parameters:{dialogSessionId:'123_456'}},{parameters:{dialogSessionId:'legacy_picker_1_2_3_4/../x'}},{parameters:{dialogSessionId:'legacy_picker_1_2_3_4\n'}},{parameters:{dialogSessionId:'legacy_picker_'+'1'.repeat(200)+'_2_3_4'}}])assert.throws(()=>create(want));
  assert.equal(sends.length,0);assert.equal(gets.length,0);
 }else if(scenario==='opaque_payload'){
  const c=create({uri:'file://attacker/not-authorized',type:'image/png',action:'ohos.want.action.choose',entities:['injected'],flags:0x7fffffff,parameters:{dialogSessionId:id,requestCode:99,'ohos.ability.params.token':{forged:true},'ohos.aafwk.param.callerToken':999,'ability.params.stream':['file://other/a%zz'],isSelector:true}});
  await c.load();await c.choose(c.targets[0].key);assert.equal(c.accepted,true);assert.deepEqual(gets,[id,id]);assert.equal(sends.length,1);assert.deepEqual(JSON.parse(JSON.stringify(sends[0])),{id,want:{bundleName:'receiver.one',moduleName:'entry',abilityName:'one'},allowed:true});assert.equal(closes.length,1);
 }else if(scenario==='enumeration'||scenario==='label_failure'||scenario==='empty'||scenario==='get_failure'){
  if(scenario==='label_failure')labelMode='reject';if(scenario==='empty')infos=[];const c=create();if(scenario==='get_failure')getMode='throw';await c.load();assert.equal(c.loading,false);assert.equal(sends.length,0);
  assert.equal(c.targets.length,scenario==='empty'||scenario==='get_failure'?0:2);if(scenario==='label_failure')assert.equal(c.targets[0].label,'receiver.one: one');if(scenario==='get_failure')assert.match(c.error,/invalid owner/);await c.cancel();assert.equal(sends[0].allowed,false);assert.equal(closes.length,1);
 }else if(scenario==='owner_denied'){
  getMode='throw';assert.throws(()=>create(),/invalid owner/);assert.equal(sends.length,0);assert.equal(closes.length,0);
 }else if(scenario==='unknown_target'){
  const c=create();await c.load();await c.choose('never-enumerated');assert.equal(sends.length,0);assert.equal(c.accepted,false);assert.ok(c.error);await c.cancel();assert.equal(sends[0].allowed,false);
 }else if(scenario==='stale_target'||scenario==='sync_start_error'||scenario==='async_start_error'){
  const c=create();await c.load();sendMode=scenario==='stale_target'?'stale':scenario==='sync_start_error'?'throw':'reject';await c.choose(c.targets[0].key);assert.equal(c.accepted,false);assert.equal(c.busy,false);assert.equal(closes.length,0);assert.ok(c.error);sendMode='normal';await c.cancel();assert.equal(sends[1].allowed,false);assert.equal(closes.length,1);
 }else if(scenario==='cancel_loading'||scenario==='destroy_loading'){
  labelMode='defer';infos=[target('one')];const c=create(),pending=c.load();await tick();if(scenario==='cancel_loading')await c.cancel();else c.dispose();releaseLabel('late label');await pending;assert.equal(c.targets.length,0);assert.equal(sends.length,scenario==='cancel_loading'?1:0);if(sends.length)assert.equal(sends[0].allowed,false);
 }else if(scenario==='duplicate'||scenario==='destroy_start'){
  const c=create();await c.load();sendMode='defer';const pending=c.choose(c.targets[0].key);await tick();await c.choose(c.targets[1].key);await c.cancel();assert.equal(sends.length,1);if(scenario==='destroy_start')c.dispose();releaseSend();await pending;assert.equal(c.accepted,true);assert.equal(closes.length,scenario==='duplicate'?1:0);assert.equal(c.busy,false);
 }else if(scenario==='close_retry'||scenario==='cancel_after_accept'){
  const c=create();await c.load();closeMode='reject';await c.choose(c.targets[0].key);assert.equal(c.accepted,true);assert.equal(sends.length,1);assert.match(c.error,/close error/);closeMode='normal';if(scenario==='close_retry')await c.choose(c.targets[1].key);else await c.cancel();assert.equal(sends.length,1);assert.equal(closes.length,2);await c.choose(c.targets[0].key);await c.cancel();assert.equal(closes.length,2);
 }else if(scenario==='cancel_close_retry'){
  const c=create();closeMode='reject';await c.cancel();assert.equal(c.cancelled,true);assert.equal(sends.length,1);closeMode='normal';await c.cancel();assert.equal(sends.length,1);assert.equal(closes.length,2);
 }else if(scenario==='cancel_error'){
  const c=create();sendMode='throw';await c.cancel();assert.equal(c.cancelled,false);assert.match(c.error,/sync native error/);assert.equal(closes.length,1);assert.equal(c.busy,false);
 }else if(scenario==='cancel_both_errors'){
  const c=create();sendMode='reject';closeMode='reject';await c.cancel();assert.equal(c.cancelled,false);assert.match(c.error,/native error/);assert.match(c.error,/close error/);assert.equal(c.busy,false);sendMode='normal';closeMode='normal';await c.cancel();assert.equal(c.cancelled,true);
 }else if(scenario==='isolation'){
  const c=create(),d=create({parameters:{dialogSessionId:other}});await c.load();await d.load();c.dispose();await c.choose('receiver.one/entry/one');await d.choose(d.targets[0].key);assert.equal(sends.length,1);assert.equal(sends[0].id,other);assert.equal(closes.length,1);
 }else if(scenario==='destroy_then_cancel'){
  const c=create();await c.load();c.dispose();c.dispose();await c.load();await c.cancel();await c.choose('receiver.one/entry/one');assert.equal(sends.length,0);assert.equal(closes.length,0);assert.equal(c.targets.length,0);
 }else throw new Error('unknown scenario '+scenario);
 console.log('PASS '+scenario);
})().catch(error=>{console.error(error);process.exitCode=1;});
