// Host dependency doubles execute the exact delivered route/controller/ability.
// These tests do not claim SDK compilation, CalendarData IPC or guest behavior.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const { stripTypeScriptTypes } = require('node:module');
const path = require('node:path');
const files = process.argv[2];
function code(relative) {
  return stripTypeScriptTypes(fs.readFileSync(path.join(files,relative),'utf8')
    .replace(/^import .*?;\n/gm,'').replace(/export default class/g,'class')
    .replace(/export (class|function)/g,'$1'),{mode:'transform'});
}
const base = new Date();base.setHours(9,0,0,0);
const start = base.getTime(), end=start+3600000;
const original={id:11,type:0,title:'Existing appointment',startTime:start,endTime:end,
  description:'Existing note',reminderTime:[10],timeZone:'UTC',location:{location:'Office'},
  attendee:[{name:'A',email:'a@example.invalid'}],identifier:'original-identifier'};
const clone=value=>JSON.parse(JSON.stringify(value));
let data=[clone(original)], other=[{...clone(original),id:23,title:'Second calendar'}];
let calls=[], snapshots=[], managerMode='resolve',queryMode='resolve',getMode='resolve',
  writeMode='resolve',queryPending=[],getPending,writePending,managerPending,nextId=31;
function defer(list){return new Promise(resolve=>list.push(resolve));}
function result(kind,values) {
  if(kind==='reject')return Promise.reject(new Error('permission denied'));
  return Promise.resolve(clone(values));
}
function makeCalendar(id,items) {
  return {id,getAccount(){return {name:'Local '+id,type:0,displayName:'Calendar '+id};},
    queryEventInstances(a,b,ids,keys){calls.push(['query',id,a,b,ids,keys]);
      if(queryMode==='defer')return defer(queryPending);
      return result(queryMode,items().filter(e=>(!ids||ids.length===0||ids.includes(e.id))&&
        (e.instanceStartTime??e.startTime)<b&&(e.instanceEndTime??e.endTime)>a));},
    getEvents(filter,keys){calls.push(['get',id,filter,keys]);
      if(getMode==='defer')return new Promise(resolve=>getPending=resolve);
      return result(getMode,items().filter(e=>filter.ids.includes(e.id)));},
    addEvent(event){calls.push(['add',id,clone(event)]);
      if(writeMode==='defer')return new Promise(resolve=>writePending=resolve);
      if(writeMode==='reject')return Promise.reject(new Error('write rejected'));
      const value={...clone(event),id:nextId};data.push(value);return Promise.resolve(nextId);},
    updateEvent(event){calls.push(['update',id,clone(event)]);
      if(writeMode==='defer')return new Promise(resolve=>writePending=resolve);
      if(writeMode==='reject')return Promise.reject(new Error('write rejected'));
      data[data.findIndex(e=>e.id===event.id)]=clone(event);return Promise.resolve();},
    deleteEvent(eventId){calls.push(['delete',id,eventId]);
      if(writeMode==='defer')return new Promise(resolve=>writePending=resolve);
      if(writeMode==='reject')return Promise.reject(new Error('delete rejected'));
      data=data.filter(e=>e.id!==eventId);return Promise.resolve();}};
}
const first=makeCalendar(1,()=>data),second=makeCalendar(2,()=>other);
const manager={getAllCalendars(){calls.push(['calendars']);
  if(managerMode==='reject')return Promise.reject(new Error('read denied'));
  if(managerMode==='defer')return new Promise(resolve=>managerPending=resolve);
  return Promise.resolve(managerMode==='empty'?[]:[first,second]);},
  getCalendar(){calls.push(['default']);return managerMode==='default_failure'?
    Promise.reject(new Error('default unavailable')):Promise.resolve(first);}};
class LocalStorage {constructor(){this.values={};}setOrCreate(k,v){this.values[k]=v;return true;}}
const sandbox={Date,console,LocalStorage,UIAbility:class{constructor(){this.context={};}},
  calendarManager:{EventType:{NORMAL:0},EventFilter:{filterById(ids){return {ids};}},
    getCalendarManager(){if(managerMode==='init_failure')throw new Error('context unavailable');return manager;}}};
vm.createContext(sandbox);
vm.runInContext(code('entry/src/main/ets/calendar/CalendarRoute.ets')+'\n'+
  code('entry/src/main/ets/calendar/CalendarController.ets')+'\n'+
  code('entry/src/main/ets/MainAbility/MainAbility.ets')+
  '\nthis.C=CalendarController;this.parse=parseCalendarRoute;this.Ability=MainAbility;',sandbox);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const latest=()=>snapshots.at(-1);
const writes=()=>calls.filter(c=>['add','update','delete'].includes(c[0]));
function controller(){return new sandbox.C({},view=>snapshots.push(view));}
async function ready(c){c.foreground();await tick();assert.equal(latest().ready,true,latest().error);}
const uri=(id=11,a=start,b=end,host='com.ohos.calendar')=>`calendar://${host}?event_id=${id}&start=${a}&end=${b}`;
const args=['User title',new Date(start).toISOString(),new Date(end).toISOString(),'User note','5',0];
(async()=>{
  const scenario=process.argv[3],c=controller();
  if(scenario==='routes'){
    assert.equal(sandbox.parse('').eventId,0);
    for(const host of ['com.ohos.calendar','com.ohos.calendardata'])assert.equal(sandbox.parse(uri(11,start,end,host)).eventId,11);
    for(const bad of ['https://example.invalid','calendar://com.ohos.calendar',uri()+'&delete=1',
      uri().replace('event_id=11','event_id=11&event_id=12'),uri().replace('com.ohos.calendar','evil'),
      uri(0),uri(-1),uri(3.5),uri(2147483648),uri(11,end,start),uri(11,0,367*86400000),
      uri().replace('start=','start=%20'),uri().replace('11&','011&'),'x'.repeat(513)])assert.throws(()=>sandbox.parse(bad),bad);
    assert.equal(calls.length,0);
  } else if(scenario==='real_reads_and_permissions'){
    await ready(c);assert.equal(latest().events[0].id,11);assert.equal(latest().calendars.length,2);
    const query=calls.find(x=>x[0]==='query');assert.equal(query[3]-query[2],86400000);
    assert.ok(query[5].includes('reminderTime'));assert.equal(writes().length,0);
    managerMode='reject';await c.refresh();assert.equal(latest().ready,false);assert.equal(latest().events.length,0);
    assert.match(latest().error,/read denied/);assert.equal(writes().length,0);
  } else if(scenario==='default_calendar'){
    managerMode='empty';await ready(c);assert.equal(calls.filter(x=>x[0]==='default').length,1);
    assert.equal(latest().calendars[0].id,1);
  } else if(scenario==='deep_link_current_calendar'){
    c.setUri(uri(23,start,end,'com.ohos.calendardata'));await ready(c);
    assert.equal(latest().selected.id,23);assert.equal(latest().calendarId,2);assert.equal(writes().length,0);
    c.setUri(uri(23,start+1,end));await tick();assert.equal(latest().ready,false);
    assert.match(latest().error,/已删除、已变更|不可访问/);assert.equal(writes().length,0);
  } else if(scenario==='malformed_uri_no_backend'){
    c.setUri(uri()+'&write=1');c.foreground();await tick();assert.equal(calls.length,0);
    assert.equal(latest().ready,false);assert.match(latest().error,/无效/);
    c.setUri('');await tick();assert.equal(latest().ready,true);
  } else if(scenario==='cancel_no_mutation'){
    await ready(c);c.select(11,start);assert.equal(latest().selected.id,11);c.cancel();
    assert.equal(latest().selected,undefined);await c.remove(11,false);assert.equal(writes().length,0);
  } else if(scenario==='create_explicit_and_duplicate'){
    await ready(c);writeMode='defer';const saving=c.save(...args);await tick();
    await c.save(...args);c.cancel();assert.equal(writes().length,1);assert.equal(latest().writing,true);
    assert.equal(writes()[0][2].reminderTime[0],5);writePending(31);await saving;
    assert.equal(latest().writing,false);assert.match(latest().notice,/已保存/);
  } else if(scenario==='edit_preserves_fields'){
    await ready(c);c.select(11,start);await c.save(...args.slice(0,5),11);
    const event=writes()[0][2];assert.equal(event.id,11);assert.equal(event.title,'User title');
    for(const key of ['attendee','identifier','timeZone','location'])assert.deepEqual(event[key],original[key]);
    assert.equal(calls.filter(x=>x[0]==='get').length,1);assert.equal(writes()[0][0],'update');
  } else if(scenario==='invalid_and_complex_write_rejected'){
    await ready(c);
    for(const fields of [['',args[1],args[2],'','',0],['x','bad',args[2],'','',0],
      ['x',args[1],args[1],'','',0],['x',args[1],args[2],'','-1',0],
      ['x',args[1],args[2],'','10081',0],['x'.repeat(5001),args[1],args[2],'','',0],
      ['x',args[1],args[2],'',' ',0],['x',args[1],args[2],'','',-1]]){
      await c.save(...fields);assert.ok(latest().error.length>0);
    }
    for(const property of [{type:1},{isAllDay:true},{isLunar:true},{recurrenceRule:{recurrenceFrequency:0}},
      {reminderTime:[5,10]}]){
      data=[{...clone(original),...property}];await c.refresh();c.select(11,start);
      await c.save(...args.slice(0,5),11);await c.remove(11,true);
    }
    assert.equal(writes().length,0);
  } else if(scenario==='invalid_backend_data_fails_closed'){
    for(const property of [{id:0},{id:2147483648},{startTime:-1},{endTime:start},
      {instanceStartTime:-1},{instanceEndTime:8640000000000001}]){
      data=[{...clone(original),...property}];c.foreground();await tick();
      assert.equal(latest().ready,false);assert.match(latest().error,/日程数据无效/);
      assert.equal(latest().events.length,0);
    }
    assert.equal(writes().length,0);
  } else if(scenario==='write_failure_and_delete_confirmation'){
    await ready(c);writeMode='reject';await c.save(...args);assert.match(latest().error,/write rejected/);
    assert.equal(latest().notice,'');c.select(11,start);await c.remove(11,false);
    assert.equal(writes().length,1);await c.remove(11,true);assert.match(latest().error,/delete rejected/);
    writeMode='resolve';c.select(11,start);await c.remove(11,true);assert.match(latest().notice,/已删除/);
    assert.equal(data.length,0);
  } else if(scenario==='background_before_read_and_before_write'){
    managerMode='defer';c.foreground();c.background();managerPending([first]);await tick();
    assert.equal(latest().ready,false);assert.equal(calls.filter(x=>x[0]==='query').length,0);
    managerMode='resolve';await ready(c);c.select(11,start);getMode='defer';
    const saving=c.save(...args.slice(0,5),11);assert.ok(c.readFilter);c.background();assert.ok(c.readFilter);
    getPending([clone(original)]);await saving;assert.equal(c.readFilter,undefined);
    assert.equal(writes().length,0);assert.equal(latest().ready,false);
    getMode='resolve';await ready(c);assert.equal(latest().events[0].id,11);
  } else if(scenario==='destroy_during_submitted_write'){
    await ready(c);writeMode='defer';const saving=c.save(...args);await tick();c.dispose();
    const count=snapshots.length;writePending(31);await saving;c.foreground();await c.save(...args);
    assert.equal(writes().length,1);assert.equal(snapshots.length,count);assert.equal(latest().ready,false);
  } else if(scenario==='new_want_stale_read'){
    queryMode='defer';c.foreground();await tick();assert.equal(queryPending.length,1);
    queryMode='resolve';c.setUri(uri(23));await tick();assert.equal(latest().selected.id,23);
    queryPending[0]([clone(original)]);await tick();assert.equal(latest().selected.id,23);
    assert.equal(latest().events[0].id,23);assert.equal(writes().length,0);
  } else if(scenario==='new_want_during_write'){
    await ready(c);writeMode='defer';const saving=c.save(...args);await tick();c.setUri(uri(23));
    writePending(31);await saving;assert.equal(latest().selected.id,23);assert.equal(latest().calendarId,2);
  } else if(scenario==='new_want_during_prewrite_read'){
    await ready(c);c.select(11,start);getMode='defer';
    const saving=c.save(...args.slice(0,5),11);c.setUri(uri(23));
    getPending([clone(original)]);await saving;assert.equal(writes().length,0);
    assert.equal(latest().ready,true);assert.equal(latest().selected.id,23);
  } else if(scenario==='restart_and_isolated_abilities'){
    await ready(c);await c.save(...args);c.dispose();const otherController=controller();
    await ready(otherController);assert.ok(latest().events.some(e=>e.id===31));
    c.setUri(uri(11));assert.equal(latest().ready,true);assert.equal(writes().length,1);
  } else if(scenario==='ability_lifecycle_and_old_window_callback'){
    const ability=new sandbox.Ability();ability.onCreate({uri:uri(23)});ability.onForeground();
    let callback;ability.onWindowStageCreate({loadContent(page,storage,cb){assert.equal(page,'pages/index');callback=cb;}});
    callback({code:0});await tick();assert.equal(ability.storage.values.calendarView.selected.id,23);
    ability.onBackground();assert.equal(ability.storage.values.calendarView.ready,false);
    ability.onNewWant({uri:uri(11)});ability.onForeground();await tick();
    assert.equal(ability.storage.values.calendarView.selected.id,11);
    ability.onWindowStageDestroy();ability.onWindowStageCreate({loadContent(page,storage,cb){cb({code:0});}});
    await tick();const before=ability.storage.values.calendarView;callback({code:4});
    assert.equal(ability.storage.values.calendarView,before);ability.onDestroy();
    assert.equal(writes().length,0);
  } else if(scenario==='ability_initialization_error_is_visible'){
    managerMode='init_failure';const ability=new sandbox.Ability();ability.onCreate({});let loaded=false;
    ability.onWindowStageCreate({loadContent(page,storage,cb){loaded=true;assert.equal(page,'pages/index');cb({code:0});}});
    assert.equal(loaded,true);assert.match(ability.storage.values.calendarView.error,/context unavailable/);
    assert.equal(ability.storage.values.calendarView.ready,false);assert.equal(writes().length,0);
  } else throw new Error(scenario);
  console.log('PASS '+scenario);
})().catch(error=>{console.error(error);process.exitCode=1;});
