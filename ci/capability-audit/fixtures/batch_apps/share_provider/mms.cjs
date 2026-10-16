const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const root=process.argv[2],scenario=process.argv[3];
const payload=fs.readFileSync(root+'/entry/src/main/ets/utils/SendDataPayload.ets','utf8').replace(/^import .*?;\r?\n/gm,'').replace('export class','class');
const util=fs.readFileSync(root+'/entry/src/main/ets/utils/WantUtil.ets','utf8');
const handle=util.slice(util.indexOf('  private handlePlainSendData('),util.indexOf('  // deepLink 网页url跳转短信'));
const third=util.slice(util.indexOf('  private buildThirdParam('),util.indexOf('  /**\n   * 根据彩信位置文本内容'));
let loads=[],toasts=[],routes=[],release,mode='normal';
const sandbox={HiLog:{i(){},e(){}},TAG:'test',DynamicLoader:{getInstance(){return {fire(name){loads.push(name);if(mode==='reject')return Promise.reject(new Error('load failed'));if(mode==='defer')return new Promise(r=>release=r);return Promise.resolve();}};}},AppStorage:{setOrCreate(){}},promptAction:{showToast(x){toasts.push(x.message);}}};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(payload+'\nclass Handler {shareGeneration: number=1;\n'+handle+third+'}\nthis.Payload=SendDataPayload;this.Handler=Handler;',{mode:'transform'}),sandbox);
const want={action:'ohos.want.action.sendData',type:'text/plain',parameters:{'ability.params.stream':'preserve\nshared text',contactObjects:'ignored attacker recipient',isRcs:true}},stack={pushPathByName(name,params){routes.push([name,params]);}},tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 if(scenario==='payload_validation'){
  for(const stream of [undefined,[],['a','b'],4,'','x\0y','x'.repeat(262145)])assert.throws(()=>sandbox.Payload.text({...want,parameters:{'ability.params.stream':stream}}));
  assert.equal(sandbox.Payload.text({...want,type:'image/png'}),undefined);assert.equal(sandbox.Payload.text({...want,uri:'file://owner/a'}),undefined);assert.equal(sandbox.Payload.text({...want,parameters:{'ability.picker.records':{},'ability.params.stream':'x'}}),undefined);assert.equal(sandbox.Payload.text({...want,parameters:{'ability.params.stream':['text']}}),'text');
 }else{
  const handler=new sandbox.Handler();if(scenario==='stale_request')mode='defer';if(scenario==='loader_failure')mode='reject';if(scenario==='invalid_text')want.parameters['ability.params.stream']=[];
  assert.equal(handler.handlePlainSendData(want,stack,1),true);
  if(scenario==='stale_request'){handler.shareGeneration=2;release();}
  await tick();
  if(scenario==='invalid_text'||scenario==='loader_failure'){assert.equal(routes.length,0);assert.equal(toasts.length,1);}
  else if(scenario==='stale_request')assert.equal(routes.length,0);
  else{assert.deepEqual(loads,['TransmitMsg']);assert.equal(routes.length,1);assert.equal(routes[0][0],'TransmitMsg');assert.equal(routes[0][1].transmitContentDetail,'preserve\nshared text');assert.equal(routes[0][1].transmitContentList[0].content,'preserve\nshared text');assert.equal(routes[0][1].isRcs,false);assert.equal(routes[0][1].contactObjects,undefined);}
 }
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e);process.exitCode=1;});
