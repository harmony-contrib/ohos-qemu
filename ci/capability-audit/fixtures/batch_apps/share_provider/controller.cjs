const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const source=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*?;\r?\n/gm,'').replace(/export (class|interface)/g,'$1');
const scenario=process.argv[3];
const info=(name,overrides={})=>({bundleName:'receiver.'+name,moduleName:'entry',name,exported:true,enabled:true,applicationInfo:{enabled:true},...overrides});
let infos=[info('one'),info('one'),info('hidden',{exported:false}),info('disabled',{enabled:false}),info('appOff',{applicationInfo:{enabled:false}}),info('two')],queryMode='normal',labelMode='normal',startMode='normal',resultMode='normal',releaseQuery,releaseStart;
let queries=[],starts=[],results=[];
const bundleManager={AbilityFlag:{GET_ABILITY_INFO_WITH_APPLICATION:2},async queryAbilityInfo(want){queries.push(want);if(queryMode==='reject')throw new Error('query permission denied');if(queryMode==='defer')return new Promise(r=>releaseQuery=r);return infos;},async getAbilityLabel(bundle,module,name){if(labelMode==='reject')throw new Error('resource unavailable');return name+' label';}};
const session={async startAbilityAsCaller(want){starts.push(want);if(startMode==='throw')throw new Error('permission denied');if(startMode==='defer')return new Promise(r=>releaseStart=r);},async terminateSelfWithResult(result){results.push(result);if(resultMode==='reject')throw new Error('result delivery failed');}};
const sandbox={uri:{URI:class {constructor(s){const u=new URL(s);this.scheme=u.protocol.slice(0,-1);this.authority=u.host;this.path=u.pathname;this.userInfo=u.username;this.fragment=u.hash;}}},bundleManager,wantConstant:{Flags:{FLAG_AUTH_READ_URI_PERMISSION:1}}};vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\nthis.Controller=SharePickerController;',sandbox);
const create=(want={parameters:{type:'text/plain','ability.params.stream':'real text'}})=>new sandbox.Controller(want,session);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 if(scenario==='invalid_payloads'){
  for(const want of [{parameters:{type:'bad mime'}},{parameters:{type:'text/plain\n'}},{parameters:{'ability.params.stream':7}},{parameters:{type:'image/png','ability.params.stream':'not file bytes'}},{parameters:{'ability.params.stream':['a','b']}},{parameters:{'ability.params.stream':[]}},{parameters:{'ability.params.stream':'x\0y'}},{parameters:{'ability.subject':'x'.repeat(5001)}},{parameters:{uri:'file://owner/a'}},{flags:2,parameters:{uri:'file://owner/a'}},{flags:1,parameters:{uri:'https://example/a'}},{flags:1,parameters:{uri:'file://owner'}},{flags:1,parameters:{uri:'file:///no-authority'}},{flags:1,parameters:{uri:'file://user@owner/a'}},{flags:1,parameters:{uri:'file://owner/a%zz'}},{flags:1,parameters:{uri:'file://owner/a#fragment'}},{flags:1,parameters:{uri:'file://owner/a\n'}},{flags:1,parameters:{uri:'file://owner/a','ability.params.stream':['file://owner/b']}},{flags:1,parameters:{uri:'file://owner/a','ability.params.stream':['file://owner/a',7]}},{flags:1,parameters:{'ability.params.stream':Array(301).fill('file://owner/a')}}])assert.throws(()=>create(want));
  assert.equal(starts.length,0);assert.equal(results.length,0);
 }else if(scenario==='text_array'){
  const c=create({parameters:{type:'Text/Plain','ability.params.stream':['array text']}});await c.load();await c.choose(c.targets[0].key);assert.equal(starts[0].type,'text/plain');assert.equal(starts[0].parameters['ability.params.stream'],'array text');
 }else if(scenario==='file_flags_and_snapshot'){
  const streams=['file://owner/a','file://owner/b'];const c=create({flags:3,parameters:{type:'image/png',uri:streams[0],'ability.params.stream':streams,'ability.subject':'photos','ohos.aafwk.param.callerToken':999,bundleName:'injected'}});streams[0]='file://attacker/changed';await c.load();await c.choose(c.targets[0].key);assert.equal(starts[0].flags,1);assert.equal(starts[0].uri,'file://owner/a');assert.deepEqual(Array.from(starts[0].parameters['ability.params.stream']),['file://owner/a','file://owner/b']);assert.deepEqual(Object.keys(starts[0].parameters).sort(),['ability.params.stream','ability.subject']);assert.equal(starts[0].bundleName,'receiver.one');assert.equal(results[0].want.parameters.outcome,'launched');
 }else if(scenario==='cancel_query'){
  queryMode='defer';const c=create();const loading=c.load();await tick();await c.cancel();releaseQuery(infos);await loading;assert.equal(c.targets.length,0);assert.equal(starts.length,0);assert.equal(results[0].resultCode,1);
 }else if(scenario==='destroy_query'){
  queryMode='defer';const c=create();const loading=c.load();c.dispose();releaseQuery(infos);await loading;await c.cancel();assert.equal(c.targets.length,0);assert.equal(starts.length,0);assert.equal(results.length,0);
 }else if(scenario==='destroy_launch'||scenario==='duplicate'){
  startMode='defer';const c=create();await c.load();const pending=c.choose(c.targets[0].key);await tick();await c.choose(c.targets[1].key);await c.cancel();assert.equal(starts.length,1);assert.equal(results.length,0);if(scenario==='destroy_launch')c.dispose();releaseStart();await pending;assert.equal(starts.length,1);assert.equal(results.length,scenario==='duplicate'?1:0);
 }else if(scenario==='stale_target'){
  const c=create();await c.load();const key=c.targets[0].key;infos=[info('other')];await c.choose(key);assert.equal(queries.length,2);assert.equal(starts.length,0);assert.equal(results.length,0);assert.ok(c.error.length>0);
 }else if(scenario==='destroy_revalidation'){
  const c=create();await c.load();queryMode='defer';const pending=c.choose(c.targets[0].key);c.dispose();releaseQuery(infos);await pending;assert.equal(starts.length,0);assert.equal(results.length,0);
 }else if(scenario==='result_retry'){
  resultMode='reject';const c=create();await c.load();await c.choose(c.targets[0].key);assert.equal(c.launched,true);assert.match(c.error,/result delivery failed/);resultMode='normal';await c.choose(c.targets[1].key);assert.equal(starts.length,1);assert.equal(results.length,2);assert.equal(results[1].want.parameters.selectedAbilityName,'one');await c.cancel();assert.equal(results.length,2);
 }else if(scenario==='cancel_after_launch_failure'){
  resultMode='reject';const c=create();await c.load();await c.choose(c.targets[0].key);resultMode='normal';await c.cancel();assert.equal(starts.length,1);assert.equal(results[1].resultCode,0);assert.equal(results[1].want.parameters.outcome,'launched');
 }else{
  if(scenario==='query_failure')queryMode='reject';if(scenario==='label_failure')labelMode='reject';if(scenario==='permission_failure')startMode='throw';if(scenario==='empty_targets')infos=[];
  const c=create(scenario==='empty_payload'?{parameters:{}}:undefined);await c.load();
  if(scenario==='query_failure'||scenario==='empty_targets'){assert.equal(c.targets.length,0);if(scenario==='query_failure')assert.match(c.error,/query permission denied/);await c.cancel();assert.equal(starts.length,0);assert.equal(results[0].resultCode,1);}
  else{assert.equal(c.targets.length,2);assert.equal(starts.length,0);if(scenario==='label_failure')assert.equal(c.targets[0].label,'receiver.one: one');await c.choose(scenario==='unknown_target'?'not-enumerated':c.targets[0].key);if(scenario==='permission_failure'||scenario==='unknown_target'||scenario==='empty_payload'){assert.equal(results.length,0);assert.ok(c.error.length>0);if(scenario!=='permission_failure')assert.equal(starts.length,0);}else{assert.equal(starts.length,1);assert.equal(results[0].resultCode,0);}}
 }
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
