const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const { stripTypeScriptTypes } = require('node:module');
const root = process.argv[2], contacts = 'applications/standard/contacts/entry/src/main/ets/';
const defer = () => { let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}; };
const tick = async () => { for(let i=0;i<12;i++)await Promise.resolve(); };
const read = name => fs.readFileSync(path.join(root,name),'utf8');
let total=0;

function harness() {
  const tasks=[], timers=new Map(), intervals=new Map(), events=new Map(), globals=new Map();
  const data={tasks,timers,intervals,events,globals,audit:()=>Promise.resolve({}),workerReplies:[],windows:[],creates:[],pixelReplies:[],stores:new Map(),logs:[],telemetry:0};
  let serial=0;
  class Storage { constructor(values={}){this.map=new Map(Object.entries(values));}setOrCreate(k,v){this.map.set(k,v)}get(k){return this.map.get(k)} }
  class HMap extends Map {hasKey(k){return this.has(k)}remove(k){return this.delete(k)}}
  class Source {refresh(v){this.value=v}totalCount(){return this.value?.length??0}}
  class Task {constructor(fn,...args){this.fn=fn;this.args=args}}
  const work={runInWorker:(req,cb,args)=>data.workerReplies.push({req,cb,args})};
  const helpers={GetGlobalThis:()=>helpers,UIContextName:'context',DataWorkerName:'worker',UiExtentionAbilityParams:'parameters',UiExtentionAbilityUIExtensionContentSession:'session',set:(k,v)=>globals.set(k,v),remove:k=>globals.delete(k),getValue:k=>globals.get(k),getDefaultUIContext:()=>globals.get('context'),getUIExtensionContentSession:()=>globals.get('session')};
  const makeEvent=(type,cb)=>{if(!events.has(type))events.set(type,new Set());events.get(type).add(cb)};
  const off=(type,cb)=>{assert.ok(cb,'must unregister a specific owned callback');events.get(type)?.delete(cb)};
  const context={config:{fontSizeScale:1,language:'en-US',colorMode:0},resourceManager:{getColorSync:()=>0xffffffff}};
  const sandbox={console:{log:()=>{},info:()=>{},warn:()=>{},error:(...v)=>data.logs.push(v)},Promise,Map,Set,Array,JSON,Math,Date,Number,String,Error,Object,
    TAG:'test',MODULE_TAG:'test',OHOS_URI:'content://com.ohos.contacts/data/anco/',DEFAULT_MAX_SELECT_CONTACTS:10000,DELAY_TIME:100,
    URL_TYPE_CONTACT_LIST:'ContactList',URL_TYPE_CONTACT_DETAIL:'ContactDetail',
    $r:()=>({}),HashMap:HMap,HashSet:Set,AlphabetIndexerPresenter:Source,ContactPickerDataSource:Source,
    HiLog:{i:()=>{},w:()=>{},e:(...a)=>data.logs.push(a),d:()=>{}},
    ContactsGlobalThisHelper:helpers,WorkFactory:{getTask:()=>work,getWorker:()=>data.worker},WorkerType:{DataWorker:0},
    DataWorkerTask:{getInstanceCurThread:()=>work},assembleLogUtils:(...a)=>data.audit(...a),
    ContactListPresenter:{getInstance:()=>({getPhotosInfoAsync:()=>Promise.resolve(),startPreInit:cb=>cb()})},
    ContactAbilityModel:{getAllContactSizeSync:()=>Promise.resolve({count:0})},
    taskpool:{Task,Priority:{HIGH:1},cancel:t=>{t.cancelled=true},execute:t=>{const d=defer();tasks.push({t,...d});return d.promise},executeDelayed:(_d,t)=>{const d=defer();tasks.push({t,...d});return d.promise}},
    getPickerContactsByFilter(){},getPickerContactsNoFilter(){},updateSearchPickerListFromDb(){},
    emitter:{emit:()=>{},on:makeEvent,off},
    addPermissionUsedRecord:()=>{data.telemetry++},
    AppStorage:{setOrCreate:(k,v)=>data.stores.set(k,v),SetOrCreate:(k,v)=>data.stores.set(k,v),get:k=>data.stores.get(k),delete:k=>data.stores.delete(k)},LocalStorage:Storage,
    setTimeout:(cb,ms)=>{const id=++serial;timers.set(id,cb);return id},clearTimeout:id=>timers.delete(id),
    setInterval:(cb,ms)=>{const id=++serial;intervals.set(id,cb);return id},clearInterval:id=>intervals.delete(id),
    UIExtensionAbility:class {constructor(){this.context=context}},
    UiExtentionParam:class {},osAccount:{getAccountManager:()=>({getOsAccountLocalId:()=>Promise.resolve(100)})},
    FontScaleState:{updateAppFontGearSize:()=>{}},AccessibilityUtil:{getInstance:()=>({getAccessibilitySwitchState:()=>{}})},
    ScreenFormUtil:{isNewFormSmallFoldScreen:()=>false},StringUtil:{isEmpty:v=>!v},
    HiAppEvent:{getInstance:()=>({SchedulerUpload:()=>{}})},
    display:{getFoldStatus:()=>0,getDefaultDisplaySync:()=>({width:100,height:200}),on:makeEvent,off},
    window:{AvoidAreaType:{TYPE_SYSTEM:0,TYPE_NAVIGATION_INDICATOR:1}},
    BreakpointUtil:{getWidthBreakpoint:()=> 'sm',judgingVerdeBreakpoint:()=>{}},DisplaySplitUtil:{updateSplitStatus:()=>{}},
    ListenerManager:class{registerListeners(){}unRegisterListeners(){}},CallServiceManager:{getInstance:()=>({updateMeetimeLoginFlag(){}})},
    Extension:class{constructor(){this.context=context}},windowManager:{create:()=>{const d=defer();data.creates.push(d);return d.promise}},
    wallPaper:{getPixelMap:(_type,cb)=>data.pixelReplies.push(cb)}
  };
  const box=vm.createContext(sandbox);
  function load(relative,name,marker='export default class') {
    let code=read(relative);code=code.slice(code.indexOf(marker)).split('\n@Concurrent')[0].replace(/\bexport (?:default )?/g,'');
    code=stripTypeScriptTypes(code,{mode:'transform'});
    vm.runInContext(code+'\nthis.'+name+'='+name+';',box,{filename:relative});
    return box[name];
  }
  load(contacts+'workers/base/WorkerWrapper.ets','WorkerWrapper','export class WorkerMessage');
  const Scope=box.WorkerRequestScope=vm.runInContext('WorkerRequestScope',box);
  const Session=load(contacts+'uiExtentionAbility/PickerSession.ets','PickerSession');
  const Presenter=load(contacts+'presenter/contact/batchselectcontacts/ContactsPickerPresenter.ets','ContactsPickerPresenter');
  const ExtensionAbility=load(contacts+'uiExtentionAbility/ContactUiExtentionAbility.ets','ContactUiExtentionAbility');
  const Renderer=load('applications/standard/theme/product/phone/src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts','WallpaperExtAbility');
  const worker=new box.WorkerWrapper(0,false);data.worker=worker;globals.set('worker',worker);globals.set('context',context);
  // Extract complete real non-DSL page methods with balanced lexical braces.
  function method(source,signature){
    const start=source.indexOf(signature);assert.ok(start>=0,signature);let i=source.indexOf('{',start),depth=0,quote=null;
    for(;i<source.length;i++){
      const c=source[i],next=source[i+1];
      if(quote){if(c==='\\'){i++;continue}if(c===quote)quote=null;continue}
      if(c==='/'&&next==='/'){i=source.indexOf('\n',i);continue}
      if(c==='/'&&next==='*'){i=source.indexOf('*/',i+2)+1;continue}
      if(c==='"'||c==="'"||c==='`'){quote=c;continue}
      if(c==='{')depth++;if(c==='}'&&--depth===0)return source.slice(start,i+1);
    }
    throw Error('Missing method end '+signature);
  }
  const pageSource=read(contacts+'pages/contacts/batchselectcontacts/ContactsPickerPage.ets');
  const pageMethods=['  private delay(','  private mirrorLegacyFlags(','  public async registerSubscriber()','  async aboutToAppear()','  aboutToDisappear()'];
  const code='class PickerPageMethods {\n'+pageMethods.map(s=>method(pageSource,s)).join('\n')+'\n}\nthis.PickerPageMethods=PickerPageMethods;';
  vm.runInContext(stripTypeScriptTypes(code,{mode:'transform'}),box);
  const indexSource=read(contacts+'pages/ContactUiExtentionIndex.ets');
  const indexMethods=['  private isLegacyFlow()','  private get currentBusy()'];
  vm.runInContext(stripTypeScriptTypes('class RootPageMethods {\n'+indexMethods.map(s=>method(indexSource,s)).join('\n')+'\n}\nthis.RootPageMethods=RootPageMethods;',{mode:'transform'}),box);
  const created=[],subscriptions=[],unsubscribed=[];
  box.subscribeInfo={events:['event.custom.contacts.VCARD_SHARE']};
  box.commonEventManager={createSubscriber:(_info,cb)=>created.push(cb),subscribe:(s,cb)=>subscriptions.push({s,cb}),unsubscribe:s=>unsubscribed.push(s)};
  data.subscribers={created,subscriptions,unsubscribed};
  function nativeSession(){const chunks=[],results=[];const proxy={hidePrivacyContentForHost(){},createSubWindowWithOptions:()=>{const d=defer();data.creates.push(d);return d.promise},properties:{uiExtensionHostWindowProxyRect:{width:100,height:200}},getWindowAvoidArea:()=>({topRect:{height:0},bottomRect:{height:0}}),on:makeEvent,off};return {chunks,results,proxy,getUIExtensionHostWindowProxy:()=>proxy,loadContent(){this.loaded=true},setWindowBackgroundColor(){},setReceiveDataCallback(cb){this.receive=cb},sendData(data){chunks.push(data)},terminateSelfWithResult(result){results.push(result);return Promise.resolve()}}}
  function request(){const native=nativeSession(),params={isContactsPicker:true,isContactMultiSelect:true,isDisplayByName:false,selectLimit:10000,userId:100,callerBundleName:'caller',callerToken:42};const req=new Session(native,context,params,worker);return {req,native,p:Presenter.createForSession(req)}}
  function win(){return {closed:0,shown:0,loaded:0,on:makeEvent,off,getWindowProperties:()=>({windowRect:{width:100,height:200}}),getWindowAvoidArea:()=>({topRect:{height:0},bottomRect:{height:0}}),loadContent(){this.loaded++;return Promise.resolve()},resize:()=>Promise.resolve(),setWindowTouchable:()=>Promise.resolve(),showWindow(){this.shown++;return Promise.resolve()},show(){this.shown++;return Promise.resolve()},setFollowParentWindowLayoutEnabled:()=>Promise.resolve(),setWindowBackgroundColor(){},setShadow(){},setFullScreen:()=>Promise.resolve(),destroyWindow(){this.closed++;return Promise.resolve()},destroy(){this.closed++;return Promise.resolve()}}}
  return {data,box,Scope,Session,Presenter,ExtensionAbility,Renderer,request,nativeSession,win,worker,context,Page:box.PickerPageMethods,RootPage:box.RootPageMethods};
}

async function check(name,run){try{await run(harness());total++;}catch(error){console.error('Failed actual-source scenario: '+name);throw error}}
async function main(){
  await check('scope idempotent + cleanup after dispose',async h=>{const s=new h.Scope();let c=0;s.onDispose(()=>c++);s.dispose();s.dispose();s.onDispose(()=>c++);assert.equal(c,2)});
  await check('worker audit cancellation',async h=>{const d=defer();h.data.audit=()=>d.promise;const s=new h.Scope();let n=0;const pending=h.worker.sendRequest('get',{},()=>n++,s);s.dispose();d.resolve({});await pending;assert.equal(h.data.workerReplies.length,0);assert.equal(n,0)});
  await check('worker audit rejection',async h=>{h.data.audit=()=>Promise.reject(Error('audit'));const s=new h.Scope();let result='pending';await h.worker.sendRequest('get',{},v=>result=v,s);assert.equal(result,undefined)});
  await check('worker removes only its callback and tolerates duplicate',async h=>{h.worker.useWorker=true;const messages=[];h.worker.mWorker={postMessage:m=>messages.push(m)};const a=new h.Scope(),b=new h.Scope();let n=0;await h.worker.sendRequest('get',{},()=>n++,a);await h.worker.sendRequest('get',{},()=>n++,b);assert.equal(h.worker.callBacks.size,2);a.dispose();assert.equal(h.worker.callBacks.size,1);const cb=[...h.worker.callBacks.values()][0];cb({});cb({});assert.equal(n,1);assert.equal(h.worker.callBacks.size,0);assert.ok(h.worker.mWorker)});
  await check('legacy worker path unchanged',async h=>{let n=0;await h.worker.sendRequest('plain',{},()=>n++);h.data.workerReplies[0].cb({});assert.equal(n,1)});
  await check('save navigation accessor is preserved without replacing public session presenter',async h=>{const native=h.nativeSession(),req=new h.Session(native,h.context,{isSaveContact:true},h.worker);const saved=h.Presenter.createForSession(req);assert.equal(h.Presenter.getInstance(),saved);const pub=h.request();assert.notEqual(pub.p,saved);assert.equal(h.Presenter.getInstance(),saved);req.dispose();assert.notEqual(h.Presenter.getInstance(),saved)});
  await check('legacy flag mirroring never writes public selection state globally',async h=>{const p=new h.Page(),{req}=h.request();p.pickerSession=req;p.sessionParameters=req.params;p.isShowBindSheet=true;p.mirrorLegacyFlags('isShowBindSheet');assert.equal(h.data.stores.has('isShowBindSheet'),false);p.sessionParameters={isSaveContact:true};p.mirrorLegacyFlags('isShowBindSheet');assert.equal(h.data.stores.get('isShowBindSheet'),true);p.isSearching=true;p.mirrorLegacyFlags('isSearching');assert.equal(h.data.stores.get('isPickerSearch'),true)});
  await check('root uses local selection busy and original save navigation busy',async h=>{const page=new h.RootPage();page.uiExtentionParam={};page.isGettingPickerData=true;page.legacyGettingPickerData=false;assert.equal(page.currentBusy,true);page.uiExtentionParam={isSaveContact:true};assert.equal(page.currentBusy,false);page.legacyGettingPickerData=true;assert.equal(page.currentBusy,true)});
  await check('actual chunk205 + terminal + duplicate',async h=>{const {p,native}=h.request();p.isContactsPicker=true;p.isMultiSelect=true;p.dealContactName=()=>[];p.dealPickerDataResult=()=>Array.from({length:205},(_,id)=>({id}));const selected=new Map([[1,{id:1}]]);await p.confirm(selected);await p.confirm(selected);assert.equal(native.chunks.length,3);assert.deepEqual(native.chunks.map(x=>JSON.parse(x.pickerData).length),[100,100,5]);assert.deepEqual(native.chunks.map(x=>x.index),[0,1,2]);assert.ok(native.chunks.every(x=>x.total===205));assert.equal(native.results.length,1);assert.equal(native.results[0].resultCode,0)});
  await check('empty default selection avoids backend and returns empty chunk',async h=>{const {p,native}=h.request();p.isContactsPicker=true;p.dealContactName=()=>[];p.dealPickerDataResult=()=>[];p.returnDefaultSelectContactData();await tick();assert.equal(h.data.workerReplies.length,0);assert.equal(native.results[0].resultCode,0);assert.equal(JSON.parse(native.chunks[0].pickerData).length,0)});
  await check('legacy sendData and Want preserved',async h=>{const {p,native}=h.request();p.isContactsPicker=false;p.dealContactName=()=>[{name:'chosen'}];p.dealPickerDataResult=()=>[];await p.confirm(new Map([[7,{id:7}]]));assert.equal(native.chunks[0].resultCode,0);assert.deepEqual([...native.results[0].want.parameters.selectContactIds],[7])});
  await check('cancel invalidates pending selected query',async h=>{const {p,native}=h.request();p.isContactsPicker=true;p.dealContactName=()=>[];p.dealPickerDataResult=()=>[];p.selectedContactsMap.set(1,new Set(['1']));p.selectBatchContact();await tick();const old=h.data.workerReplies[0].cb;p.returnDefaultSelectContactData();await tick();old(new Map([[1,{id:1}]]));await tick();assert.equal(native.results.length,1);assert.equal(JSON.parse(native.chunks[0].pickerData).length,0)});
  await check('destroyed query cannot reach newer session',async h=>{const old=h.request(),now=h.request();let n=0;old.p.getPickerDataByIds(new Set([1]),()=>n++);await tick();old.req.dispose();h.data.workerReplies[0].cb(new Map([[1,{}]]));assert.equal(n,0);assert.equal(now.native.results.length,0);assert.ok(now.req.active)});
  await check('chunk transport failure returns failure not success',async h=>{const {req,native}=h.request();native.sendData=()=>{throw Error('transport')};await req.deliver([{pickerData:'[]'}],{resultCode:0});assert.equal(native.results[0].resultCode,-1)});
  await check('terminal retry does not repeat chunks',async h=>{const {req,native}=h.request();let n=0;native.terminateSelfWithResult=result=>{native.results.push(result);return n++===0?Promise.reject(Error('once')):Promise.resolve()};await req.deliver([{pickerData:'[]'}],{resultCode:0});await req.deliver([{pickerData:'[]'}],{resultCode:0});assert.equal(native.chunks.length,1);assert.equal(native.results.length,2);assert.equal(req.active,false)});
  await check('pending terminate cannot cancel a newer request',async h=>{const old=h.request(),now=h.request(),d=defer();old.native.terminateSelfWithResult=()=>d.promise;const result=old.req.finish({resultCode:1});old.req.dispose();d.resolve();await result;assert.ok(now.req.active);assert.equal(now.native.results.length,0)});
  await check('reentrant session destroy between chunks cannot emit success',async h=>{const {req,native}=h.request(),now=h.request();native.sendData=chunk=>{native.chunks.push(chunk);req.dispose()};await req.deliver([{pickerData:'a'},{pickerData:'b'}],{resultCode:0});assert.equal(native.chunks.length,1);assert.equal(native.results.length,0);assert.ok(now.req.active)});
  await check('query count rejection settles real error',async h=>{const {p,native}=h.request();h.box.ContactAbilityModel.getAllContactSizeSync=()=>Promise.reject(Error('database'));await p.preInitContactList(100);await tick();assert.equal(native.results[0].resultCode,-1)});
  await check('count after dispose cannot schedule tasks',async h=>{const {p,req}=h.request(),d=defer();h.box.ContactAbilityModel.getAllContactSizeSync=()=>d.promise;const pending=p.preInitContactList(100);req.dispose();d.resolve({count:1});await pending;assert.equal(h.data.tasks.length,0)});
  await check('page task rejection no hanging async executor',async h=>{const {p,native}=h.request();h.box.ContactAbilityModel.getAllContactSizeSync=()=>Promise.resolve({count:1});const pending=p.preInitContactList(100);await tick();h.data.tasks[0].reject(Error('query'));await pending;await tick();assert.equal(native.results[0].resultCode,-1)});
  await check('old search cannot update new search',async h=>{const {p}=h.request();p.getSearchContactResultFromDb('old');p.getSearchContactResultFromDb('new');h.data.tasks[0].resolve([{entityId:'1'}]);await tick();assert.equal(p.contactSearchOffset,0);h.data.tasks[1].resolve([]);await tick();assert.equal(p.tasks.size,0)});
  await check('extension duplicate create and listeners idempotent teardown',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession();await ext.onSessionCreate({parameters:{userId:100}},s);assert.equal(h.data.intervals.size,1);await ext.onSessionCreate({parameters:{}},s);assert.equal(h.data.intervals.size,1);ext.onSessionDestroy(s);ext.onSessionDestroy(s);ext.onDestroy();assert.equal(h.data.intervals.size,0);assert.ok([...h.data.events.values()].every(x=>x.size===0));assert.equal(h.data.globals.has('session'),false)});
  await check('extension destroy during create closes late window without show',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession();const pending=ext.onSessionCreate({parameters:{isContactsPicker:true,userId:100}},s);await tick();ext.onSessionDestroy(s);const w=h.win();h.data.creates[0].resolve(w);await pending;assert.equal(w.closed,1);assert.equal(w.shown,0);assert.equal(h.data.intervals.size,0)});
  await check('extension old destroy does not clear newer session or listeners',async h=>{const ext=new h.ExtensionAbility(),old=h.nativeSession(),now=h.nativeSession();await ext.onSessionCreate({parameters:{userId:100}},old);await ext.onSessionCreate({parameters:{userId:100}},now);ext.onSessionDestroy(old);assert.equal(h.data.globals.get('session'),now);assert.equal(h.data.intervals.size,1);ext.onDestroy();assert.equal(h.data.intervals.size,0)});
  await check('extension creation rejection returns error and cleans',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession();const pending=ext.onSessionCreate({parameters:{isContactsPicker:true,userId:100}},s);await tick();h.data.creates[0].reject(Error('window'));await pending;assert.equal(s.results[0].resultCode,-1);assert.equal(h.data.intervals.size,0)});
  await check('extension account completion after destroy cannot load UI',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession(),d=defer();h.box.osAccount.getAccountManager=()=>({getOsAccountLocalId:()=>d.promise});const pending=ext.onSessionCreate({parameters:{userId:100}},s);ext.onSessionDestroy(s);d.resolve(100);await pending;assert.equal(s.loaded,undefined);assert.equal(h.data.intervals.size,0)});
  await check('extension account rejection cleans without fake result',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession();h.box.osAccount.getAccountManager=()=>({getOsAccountLocalId:()=>Promise.reject(Error('account'))});await ext.onSessionCreate({parameters:{userId:100}},s);assert.equal(s.results[0].resultCode,-1);assert.equal(h.data.intervals.size,0)});
  await check('overlapping account queries preserve request user ID',async h=>{const ext=new h.ExtensionAbility(),a=h.nativeSession(),b=h.nativeSession(),one=defer(),two=defer();let index=0;h.box.osAccount.getAccountManager=()=>({getOsAccountLocalId:()=>index++===0?one.promise:two.promise});const first=ext.onSessionCreate({parameters:{userId:100}},a),second=ext.onSessionCreate({parameters:{userId:120}},b);one.resolve(100);await first;two.resolve(120);await second;assert.equal(a.results.length,0);assert.equal(b.results.length,0);assert.ok(a.loaded&&b.loaded);ext.onDestroy()});
  await check('extension show completion after destroy cannot continue setup',async h=>{const ext=new h.ExtensionAbility(),s=h.nativeSession(),w=h.win(),show=defer();let followed=0;w.showWindow=()=>show.promise;w.setFollowParentWindowLayoutEnabled=()=>{followed++;return Promise.resolve()};const pending=ext.onSessionCreate({parameters:{isContactsPicker:true,userId:100}},s);await tick();h.data.creates[0].resolve(w);await tick();ext.onSessionDestroy(s);show.resolve();await pending;assert.equal(w.closed,1);assert.equal(followed,0);assert.equal(h.data.intervals.size,0)});
  await check('subscriber late creation and late event cannot close a new page',async h=>{const page=new h.Page(),s=h.data.subscribers;let closed=0;page.pageScope=new h.Scope();page.handleVcardShareSubscribeCB=()=>closed++;page.unsubscribeCB=()=>{};await page.registerSubscriber();page.pageScope.dispose();page.pageScope=new h.Scope();await page.registerSubscriber();s.created[0](null,'old');s.created[1](null,'new');assert.deepEqual(s.unsubscribed,['old']);assert.equal(s.subscriptions.length,1);page.pageScope.dispose();page.pageScope=new h.Scope();s.subscriptions[0].cb(null,{});assert.equal(closed,0);assert.deepEqual(s.unsubscribed,['old','new'])});
  await check('public picker cannot be closed by unaddressed Contacts import broadcast',async h=>{const page=new h.Page();page.pageScope=new h.Scope();page.pickerSession=h.request().req;await page.registerSubscriber();assert.equal(h.data.subscribers.created.length,0)});
  await check('page account completion after disappear cannot initialize presenter',async h=>{const page=new h.Page(),{req}=h.request(),account=defer();let initialized=0;page.pageScope=new h.Scope();page.pickerSession=req;page.sessionParameters=req.params;page.sessionPresenter={aboutToAppear:()=>initialized++,isActive:()=>true};page.init=()=>{};page.unInit=()=>{};page.intelligenceGroupAddContactDialogControler={close(){}};page.showOnlyAccessedAlert=()=>{};page.titleMethodClass={};page.slidingMultipleSelectionsUtil={};h.box.osAccount.getAccountManager=()=>({getOsAccountLocalId:()=>account.promise});const pending=page.aboutToAppear();page.aboutToDisappear();account.resolve(100);await pending;assert.equal(initialized,0);assert.equal(h.data.timers.size,0)});
  await check('wallpaper late create after destroy',async h=>{const r=new h.Renderer(),w=h.win();r.onCreated({});r.onDestroy();h.data.creates[0].resolve(w);await tick();assert.equal(w.closed,1);assert.equal(w.shown,0)});
  await check('wallpaper destroy during load',async h=>{const r=new h.Renderer(),w=h.win(),load=defer();w.loadContent=()=>load.promise;r.onCreated({});h.data.creates[0].resolve(w);await tick();r.onDestroy();load.resolve();await tick();assert.equal(w.closed,1);assert.equal(w.shown,0)});
  await check('wallpaper old failure cannot close new window',async h=>{const r=new h.Renderer(),old=h.win(),now=h.win(),load=defer();old.loadContent=()=>load.promise;r.onCreated({});h.data.creates[0].resolve(old);await tick();r.onCreated({});h.data.creates[1].resolve(now);await tick();load.reject(Error('old'));await tick();assert.equal(old.closed,1);assert.equal(now.closed,0);assert.equal(now.shown,1);r.onDestroy();r.onDestroy();assert.equal(now.closed,1)});
  await check('wallpaper creation failure logs real error',async h=>{const r=new h.Renderer();r.onCreated({});h.data.creates[0].reject(Error('window'));await tick();assert.ok(h.data.logs.some(x=>String(x).includes('creation failed')))});
  await check('wallpaper image generations and post-destroy completion',async h=>{const r=new h.Renderer();r.onCreated({});r.onWallpaperChanged(0);const old=h.data.pixelReplies[0],latest=h.data.pixelReplies[1];latest(null,'new');old(null,'old');assert.equal(h.data.stores.get('slPixelData'),'new');r.onDestroy();latest(null,'after');assert.equal(h.data.stores.get('slPixelData'),'new')});
  await check('wallpaper synchronous read error is caught without image success',async h=>{const r=new h.Renderer();h.box.wallPaper.getPixelMap=()=>{throw Error('read')};r.onCreated({});assert.equal(h.data.stores.has('slPixelData'),false);assert.ok(h.data.logs.some(x=>String(x).includes('request failed')))});
  console.log(total+' actual source scenarios passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
