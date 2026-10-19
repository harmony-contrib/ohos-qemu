// Actual delivered page method bodies, with plain host state and service doubles.
// ArkUI decorators/rendering, windows and public services are NOT executed here.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const base=process.argv[2],page=fs.readFileSync(path.join(base,'entry/src/main/ets/pages/index.ets'),'utf8');
function method(signature){const start=page.indexOf(signature);assert.ok(start>0,signature);let i=page.indexOf('{',start)+1,depth=1;while(depth){depth+=(page[i]==='{')-(page[i]==='}');i++;}return page.slice(start,i);}
const names=['aboutToAppear():','aboutToDisappear():','private async routeChanged():','private startBusiness():','private openBrowser():','private openReminder():','private viewChanged():','private editable(','private openForm(','private cancel():','onBackPress():'];
let calls=[],pending=[],contextFailure=false;
class Reader {constructor(){calls.push('reader-created');this.status='';}dispose(){calls.push('reader-disposed');}open(uri){calls.push('read '+uri);return new Promise(resolve=>pending.push(event=>{this.event=event;resolve();}));}}
class Business {constructor(context,publish){this.publish=publish;calls.push('business-created');}foreground(){calls.push('business-read');}background(){calls.push('business-background');this.publish({ready:false});}dispose(){calls.push('business-dispose');}}
class View {ready=false;writing=false;selected=undefined;}
const sandbox={Date,console,CalendarReminderReader:Reader,CalendarBusinessController:Business,CalendarView:View,
 calendarManager:{EventType:{NORMAL:0}},getContext(){if(contextFailure)throw new Error('context gone');return{};}};
const fields=`route='';revision=0;foreground=true;browsing=false;view=new CalendarView();form=false;deleteConfirm=false;reader=undefined;controller=undefined;generation=0;appearing=false;`;
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes('class Index {'+fields+names.map(method).join('\n')+'}',{mode:'transform'})+'\nthis.Page=Index;',sandbox);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 let p=new sandbox.Page();p.aboutToAppear();assert.equal(p.browsing,true);assert.ok(calls.includes('business-read'));assert.equal(p.reader,undefined);p.aboutToDisappear();
 calls=[];p=new sandbox.Page();p.route='first';p.aboutToAppear();assert.equal(p.browsing,false);const old=pending.shift();
 p.route='second';const now=p.routeChanged();const current=pending.shift();current({title:'Fresh',startTime:10,endTime:20});await now;
 old({title:'Stale',startTime:1,endTime:2});await tick();assert.equal(p.reminderTitle,'Fresh');
 assert.equal(calls.filter(x=>x==='business-read').length,0);p.openBrowser();assert.equal(p.browsing,true);assert.ok(calls.includes('business-read'));
 const display=p.reminderTitle;p.foreground=false;await p.routeChanged();assert.equal(p.reminderTitle,'');assert.ok(calls.includes('business-background'));
 p.foreground=true;p.route='third';const reading=p.routeChanged();const exit=pending.shift();p.aboutToDisappear();exit({title:'After exit',startTime:1,endTime:2});await reading;assert.equal(p.reminderTitle,'');
 p=new sandbox.Page();p.view.writing=true;assert.equal(p.onBackPress(),false);p.view.writing=false;p.form=true;assert.equal(p.onBackPress(),true);assert.equal(p.form,false);
 contextFailure=true;p=new sandbox.Page();p.aboutToAppear();assert.match(p.view.error,/context gone/);
 p=new sandbox.Page();p.route='context-error';await p.aboutToAppear();await tick();assert.match(p.reminderStatus,/context gone/);contextFailure=false;
 const source=fs.readFileSync(path.join(base,'entry/src/main/ets/MainAbility/MainAbility.ets'),'utf8').replace(/^import .*?;\n/gm,'').replace('export default class','class');
 const a={UIAbility:class{},LocalStorage:class{values=new Map();setOrCreate(k,v){this.values.set(k,v);}}};vm.createContext(a);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\nthis.Ability=MainAbility;',a);
 const one=new a.Ability(),two=new a.Ability();one.onCreate({uri:'saved'});two.onCreate({});let storage;
 one.onWindowStageCreate({loadContent(page,local){storage=local;}});assert.equal(storage.values.get('calendarForeground'),false);
 one.onForeground();assert.equal(storage.values.get('calendarForeground'),true);one.onWindowStageDestroy();assert.equal(storage.values.get('calendarForeground'),false);
 one.onWindowStageCreate({loadContent(page,local){assert.equal(local,storage);}});assert.equal(storage.values.get('calendarForeground'),true);
 one.onBackground();assert.equal(storage.values.get('calendarForeground'),false);const rev=storage.values.get('calendarRevision');one.onNewWant({uri:'saved'});assert.ok(storage.values.get('calendarRevision')>rev);
 assert.notEqual(one.storage,two.storage);one.onDestroy();assert.equal(storage.values.get('calendarForeground'),false);
 console.log('PASS host-only actual page lifecycle bodies: reminder supersession, explicit browse, background/exit/init errors; actual Ability foreground/window/storage lifecycle');
})().catch(e=>{console.error(e);process.exitCode=1;});
