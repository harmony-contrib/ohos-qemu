// Host service doubles execute the installed business controller body, not SDK/IPC.
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
const FIXED_NOW=Date.parse('2026-10-19T12:00:00.000Z');
class FixedDate extends Date {constructor(...args){super(...(args.length?args:[FIXED_NOW]));}static now(){return FIXED_NOW;}}
const base = new FixedDate();base.setHours(9,0,0,0);
const start = base.getTime(), end=start+3600000;
const original={id:11,type:0,title:'Existing appointment',startTime:start,endTime:end,
  description:'Existing note',reminderTime:[10],timeZone:'UTC',location:{location:'Office'},
  attendee:[{name:'A',email:'a@example.invalid'}],identifier:'original-identifier',service:{type:'Meeting',uri:'calendar-audit://meeting/original'}};
const clone=value=>JSON.parse(JSON.stringify(value));
let data=[clone(original)], other=[{...clone(original),id:23,title:'Second calendar'}];
let calls=[], snapshots=[], managerMode='resolve',queryMode='resolve',getMode='resolve',
  writeMode='resolve',queryPending=[],getPending,writePending,managerPending,nextId=31;
function defer(list){return new Promise(resolve=>list.push(resolve));}
function result(kind,values) {
  if(kind==='reject')return Promise.reject(new Error('permission denied'));
  return Promise.resolve(clone(values));
}
const PUBLIC_EVENT_KEYS=['id','type','title','startTime','endTime','isAllDay','location','description','reminderTime','recurrenceRule','attendee','service','identifier','isLunar','timeZone','instanceStartTime','instanceEndTime'];
function makeCalendar(id,items) {
  return {id,getAccount(){return {name:'Local '+id,type:0,displayName:'Calendar '+id};},
    queryEventInstances(a,b,ids,keys){assert.deepEqual(Array.from(keys),PUBLIC_EVENT_KEYS);calls.push(['query',id,a,b,ids,keys]);
      if(queryMode==='defer')return defer(queryPending);
      return result(queryMode,items().filter(e=>(!ids||ids.length===0||ids.includes(e.id))&&
        (e.instanceStartTime??e.startTime)<b&&(e.instanceEndTime??e.endTime)>a));},
    getEvents(filter,keys){assert.deepEqual(Array.from(keys),PUBLIC_EVENT_KEYS);calls.push(['get',id,filter,keys]);
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
let grantMode='resolve',readGrant=0,writeGrant=0,grantPending,grantRequests=[];
const sandbox={Date:FixedDate,console,
  abilityAccessCtrl:{createAtManager(){return {requestPermissionsFromUser(context,names){
    const name=names[0];grantRequests.push(name);calls.push(['permission',name]);
    if(grantMode==='defer')return new Promise(resolve=>grantPending=resolve);
    if(grantMode==='throw')return Promise.reject(Object.assign(new Error('consent cancelled'),{code:12100001}));
    const auth=name.includes('WRITE')?writeGrant:readGrant;
    return Promise.resolve({permissions:grantMode==='wrong'?['ohos.permission.UNRELATED']:names,authResults:[auth]});
  }}}},
  calendarManager:{EventType:{NORMAL:0},EventFilter:{filterById(ids){return {ids};}},
    getCalendarManager(){calls.push(['manager']);if(managerMode==='init_failure')throw new Error('context unavailable');return manager;}}};
vm.createContext(sandbox);
vm.runInContext(code('entry/src/main/ets/calendar/CalendarBusinessController.ets')+
  '\nthis.C=CalendarBusinessController;',sandbox);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const latest=()=>snapshots.at(-1);
const writes=()=>calls.filter(c=>['add','update','delete'].includes(c[0]));
const wgrants=()=>grantRequests.filter(x=>x.includes('WRITE'));
function controller(){return new sandbox.C({},view=>snapshots.push(view));}
async function ready(c){c.foreground();await tick();assert.equal(latest().ready,true,latest().error);}
const args=['User title',new Date(start).toISOString(),new Date(end).toISOString(),'User note','5',0];
(async()=>{
 const c=controller(),scenario=process.argv[3];
 if(scenario==='read_permission_and_real_query'){
  await ready(c);assert.equal(calls[0][0],'permission');assert.equal(latest().events[0].id,11);
  assert.equal(calls.find(x=>x[0]==='query')[3]-calls.find(x=>x[0]==='query')[2],86400000);
  c.select(11,start);c.cancel();c.chooseCalendar(2);await tick();c.moveDay(1);await tick();
  assert.equal(wgrants().length,0);assert.equal(writes().length,0);
 }else if(scenario==='read_denied_cancel_wrong_result'){
  for(const mode of ['deny','throw','wrong']){
   grantMode=mode==='deny'?'resolve':mode;readGrant=mode==='deny'?-1:0;
   c.foreground();await tick();assert.equal(latest().ready,false);assert.ok(latest().error);
  }
  assert.equal(calls.filter(x=>['manager','calendars','query'].includes(x[0])).length,0);
 }else if(scenario==='default_calendar'){
  managerMode='empty';await ready(c);assert.equal(latest().calendarId,1);assert.equal(calls.filter(x=>x[0]==='default').length,1);
 }else if(scenario==='create_explicit_confirmed'){
  await ready(c);await c.save(...args);assert.equal(writes().length,1);assert.equal(writes()[0][0],'add');
  assert.equal(writes()[0][2].timeZone,'UTC');assert.equal(writes()[0][2].reminderTime[0],5);
  assert.ok(latest().events.some(e=>e.id===31));assert.match(latest().notice,/已保存/);assert.equal(latest().writing,false);
 }else if(scenario==='write_denied_cancel_no_mutation'){
  await ready(c);for(const mode of ['deny','throw','wrong']){
   grantMode=mode==='deny'?'resolve':mode;writeGrant=mode==='deny'?-1:0;
   await c.save(...args);assert.ok(latest().error);assert.equal(latest().writing,false);
  }assert.equal(writes().length,0);assert.equal(latest().notice,'');
 }else if(scenario==='invalid_form_never_requests_write'){
  await ready(c);for(const fields of [['',args[1],args[2],'','',0],['x','bad',args[2],'','',0],
   ['x',args[1],args[1],'','',0],['x',args[1],args[2],'','-1',0],['x',args[1],args[2],'','10081',0],
   ['x'.repeat(5001),args[1],args[2],'','',0],['x',args[1],args[2],'',' ',0],
   ['x',args[1],args[2],'','',-1],['x','2026-02-30T09:00:00.000Z',args[2],'','',0],
   ['x',args[1].slice(0,-1),args[2],'','',0]]){await c.save(...fields);assert.ok(latest().error);}
  assert.equal(wgrants().length,0);assert.equal(writes().length,0);
 }else if(scenario==='edit_preserves_fields_and_timezone'){
  await ready(c);c.select(11,start);await c.save(...args.slice(0,5),11);
  const event=writes()[0][2];assert.equal(writes()[0][0],'update');assert.equal(event.title,'User title');
  for(const key of ['attendee','identifier','timeZone','location','service'])assert.deepEqual(event[key],original[key]);
  assert.equal(calls.filter(x=>x[0]==='get').length,1);assert.match(latest().notice,/已保存/);
 }else if(scenario==='complex_events_read_only'){
  for(const property of [{type:1},{isAllDay:true},{isLunar:true},{recurrenceRule:{recurrenceFrequency:0}},{reminderTime:[5,10]}]){
   data=[{...clone(original),...property}];await ready(c);c.select(11,start);await c.save(...args.slice(0,5),11);await c.remove(11,true);
  }assert.equal(wgrants().length,0);assert.equal(writes().length,0);
 }else if(scenario==='delete_confirmation_rechecks_real_event'){
  await ready(c);c.select(11,start);await c.remove(11,false);assert.equal(wgrants().length,0);
  await c.remove(11,true);assert.equal(wgrants().length,1);assert.equal(calls.filter(x=>x[0]==='get').length,1);
  assert.equal(writes()[0][0],'delete');assert.equal(latest().events.length,0);assert.match(latest().notice,/已删除/);
 }else if(scenario.startsWith('delete_changed_public_')){
  const field=scenario.slice('delete_changed_public_'.length);
  const mutations={location:e=>e.location.location='Changed elsewhere',
   attendee:e=>e.attendee[0].email='changed@example.invalid',identifier:e=>e.identifier='changed-identifier',
   reminderTime:e=>e.reminderTime=[20]};
  assert.ok(mutations[field]);await ready(c);c.select(11,start);const reads=calls.filter(x=>x[0]==='query').length;
  mutations[field](data[0]);await c.remove(11,true);
  assert.equal(writes().length,0);assert.ok(latest().error);assert.equal(latest().selected,undefined);
  assert.equal(calls.filter(x=>x[0]==='query').length,reads+1);assert.equal(c.readFilter,undefined);
  assert.equal(latest().writing,false);
 }else if(scenario==='delete_all_public_nested_changes'){
  const mutations=[e=>e.title='Changed',e=>e.startTime+=1000,e=>e.endTime+=1000,
   e=>e.description='Changed note',e=>e.type=1,e=>e.isAllDay=true,e=>e.isLunar=true,
   e=>e.timeZone='Asia/Shanghai',e=>e.location.longitude=120,e=>e.location.latitude=30,
   e=>e.attendee[0].name='Another',e=>e.attendee[0].role='organizer',
   e=>e.attendee[0].type=1,e=>e.attendee[0].status=2,
   e=>e.service.type='Watching',e=>e.service.uri='calendar-audit://meeting/changed',
   e=>e.service.description='Changed service',e=>e.recurrenceRule={recurrenceFrequency:0},
   e=>delete e.location,e=>delete e.attendee,e=>delete e.reminderTime,e=>delete e.service,
   e=>e.identifier=null,e=>e.isAllDay=false,e=>e.isLunar=false];
  for(const mutate of mutations){
   data=[clone(original)];await ready(c);c.select(11,start);const reads=calls.filter(x=>x[0]==='query').length;
   mutate(data[0]);await c.remove(11,true);assert.equal(writes().length,0);
   assert.ok(latest().error);assert.equal(latest().selected,undefined);
   assert.equal(calls.filter(x=>x[0]==='query').length,reads+1);assert.equal(c.readFilter,undefined);
  }
 }else if(scenario==='delete_incomparable_types_refresh'){
  const mutations=[e=>e.type='0',e=>e.isAllDay=null,e=>e.isLunar=0,e=>e.title=3,
   e=>e.description={},e=>e.timeZone=false,e=>e.identifier=[],e=>e.reminderTime=['10'],
   e=>e.reminderTime=[NaN],e=>e.reminderTime=[Infinity],e=>e.reminderTime=new Array(1),
   e=>e.location=[],e=>e.location={location:'Office',longitude:NaN},e=>e.location.future=1,
   e=>e.attendee=[{name:'A',email:3}],e=>e.attendee=[{name:'A',email:'x',role:'future'}],
   e=>e.attendee=[{name:'A',email:'x',type:'1'}],e=>e.attendee=[{name:'A',email:'x',status:NaN}],
   e=>e.attendee=[{name:'A',email:'x',future:1}],e=>e.attendee=new Array(1),
   e=>e.service={type:'Meeting'},e=>e.service={type:'future',uri:'calendar-audit://x'},
   e=>e.service={type:'Meeting',uri:'calendar-audit://x',future:1},e=>e.service=null,
   e=>e.futureField='unknown',e=>e.instanceStartTime=start,e=>e.instanceEndTime=end,
   e=>{e.instanceStartTime=start+1;e.instanceEndTime=end+1;}];
  for(const mutate of mutations){
   data=[clone(original)];await ready(c);c.select(11,start);getMode='defer';
   const pending=c.remove(11,true);await tick();const changed=clone(original);mutate(changed);
   getPending([changed]);await pending;getMode='resolve';
   assert.equal(writes().length,0);assert.ok(latest().error);assert.equal(latest().selected,undefined);
   assert.equal(c.readFilter,undefined);assert.equal(latest().writing,false);
  }
  // Invalid displayed shapes are rejected before requesting WRITE, then reread.
  for(const mutate of mutations.slice(0,8)){
   data=[clone(original)];await ready(c);c.select(11,start);mutate(c.view.selected);
   const before=wgrants().length,reads=calls.filter(x=>x[0]==='query').length;await c.remove(11,true);
   assert.equal(wgrants().length,before);assert.equal(writes().length,0);
   assert.equal(calls.filter(x=>x[0]==='query').length,reads+1);assert.ok(latest().error);
  }
 }else if(scenario==='delete_instance_projection_and_order'){
  const query=first.queryEventInstances.bind(first);
  first.queryEventInstances=(...args)=>query(...args).then(rows=>rows.map(e=>
   ({...e,instanceStartTime:e.startTime,instanceEndTime:e.endTime})));
  await ready(c);c.select(11,start);
  // getEvents omits derived fields; equivalent public object key ordering is harmless.
  data[0]={...data[0],location:{latitude:undefined,location:'Office'},
   attendee:[{email:'a@example.invalid',name:'A'}],
   service:{uri:'calendar-audit://meeting/original',type:'Meeting'}};
  await c.remove(11,true);assert.equal(writes().length,1);assert.equal(writes()[0][0],'delete');
  assert.match(latest().notice,/已删除/);
  // The base and instance APIs may both return matching derived fields.
  data=[clone(original)];await ready(c);c.select(11,start);
  data[0].instanceStartTime=start;data[0].instanceEndTime=end;await c.remove(11,true);
  assert.equal(writes().length,2);
  // Documented nullable absence is comparable without conflating it with undefined.
  data=[{...clone(original),location:null,attendee:null,identifier:null}];await ready(c);c.select(11,start);
  await c.remove(11,true);assert.equal(writes().length,3);
 }else if(scenario==='delete_displayed_snapshot_frozen_before_permission'){
  await ready(c);c.select(11,start);grantMode='defer';const pending=c.remove(11,true);await tick();
  data[0].location.location='Changed during consent';c.view.selected.location.location='Changed during consent';
  grantPending({permissions:['ohos.permission.WRITE_WHOLE_CALENDAR'],authResults:[0]});grantMode='resolve';await pending;
  assert.equal(writes().length,0);assert.match(latest().error,/已变更/);assert.equal(latest().selected,undefined);
 }else if(scenario==='delete_lifecycle_permission_cleanup'){
  await ready(c);c.select(11,start);grantMode='defer';let pending=c.remove(11,true);await tick();
  c.background();grantPending({permissions:['ohos.permission.WRITE_WHOLE_CALENDAR'],authResults:[0]});
  grantMode='resolve';await pending;assert.equal(writes().length,0);assert.equal(c.readFilter,undefined);
  await ready(c);c.select(11,start);getMode='defer';pending=c.remove(11,true);await tick();
  c.dispose();const count=snapshots.length;getPending([clone(original)]);await pending;
  assert.equal(writes().length,0);assert.equal(c.readFilter,undefined);assert.equal(snapshots.length,count);
 }else if(scenario==='delete_changed_event_fails_closed'){
  await ready(c);c.select(11,start);data[0].title='Changed elsewhere';await c.remove(11,true);
  assert.equal(writes().length,0);assert.match(latest().error,/已变更/);
 }else if(scenario==='delete_missing_or_recurring_fails_closed'){
  await ready(c);c.select(11,start);data=[];await c.remove(11,true);assert.equal(writes().length,0);
  data=[clone(original)];await c.refresh();c.select(11,start);data[0].recurrenceRule={recurrenceFrequency:0};
  await c.remove(11,true);assert.equal(writes().length,0);assert.match(latest().error,/已变更/);
 }else if(scenario==='exit_during_permission_no_write'){
  await ready(c);grantMode='defer';const pending=c.save(...args);await tick();c.background();
  grantPending({permissions:['ohos.permission.WRITE_WHOLE_CALENDAR'],authResults:[0]});await pending;
  assert.equal(writes().length,0);assert.equal(latest().ready,false);
 }else if(scenario==='destroy_during_permission_no_write'){
  await ready(c);grantMode='defer';const pending=c.save(...args);await tick();c.dispose();const count=snapshots.length;
  grantPending({permissions:['ohos.permission.WRITE_WHOLE_CALENDAR'],authResults:[0]});await pending;
  assert.equal(writes().length,0);assert.equal(snapshots.length,count);
 }else if(scenario==='background_during_prewrite_read'){
  await ready(c);c.select(11,start);getMode='defer';const pending=c.save(...args.slice(0,5),11);await tick();
  assert.ok(c.readFilter);c.background();getPending([clone(original)]);await pending;
  assert.equal(writes().length,0);assert.equal(c.readFilter,undefined);assert.equal(latest().ready,false);
 }else if(scenario==='destroy_after_submission_does_not_cancel_provider'){
  await ready(c);writeMode='defer';const pending=c.save(...args);await tick();assert.equal(writes().length,1);
  c.dispose();const count=snapshots.length;data.push({...clone(writes()[0][2]),id:31});writePending(31);await pending;
  assert.equal(snapshots.length,count);assert.equal(data.length,2);assert.equal(writes().length,1);
 }else if(scenario==='duplicate_submission_blocked'){
  await ready(c);writeMode='defer';const pending=c.save(...args);await tick();await c.save(...args);await c.remove(11,true);
  assert.equal(writes().length,1);writePending(31);await pending;
 }else if(scenario==='api_denied_after_grant_is_error'){
  await ready(c);first.addEvent=function(){calls.push(['add']);return Promise.reject(Object.assign(new Error('revoked'),{code:201}));};
  await c.save(...args);assert.match(latest().error,/拒绝|撤回/);assert.equal(latest().notice,'');assert.equal(latest().ready,true);
 }else if(scenario==='write_success_read_failure_is_not_empty_success'){
  await ready(c);first.addEvent=function(event){calls.push(['add']);data.push({...event,id:31});readGrant=-1;return Promise.resolve(31);};
  await c.save(...args);assert.equal(latest().ready,false);assert.equal(latest().notice,'');assert.match(latest().error,/读取日历权限/);
 }else if(scenario==='unsupported_read_visible'){
  manager.getAllCalendars=function(){return Promise.reject(Object.assign(new Error('unsupported'),{code:801}));};
  c.foreground();await tick();assert.equal(latest().ready,false);assert.match(latest().error,/不支持/);
 }else if(scenario==='stale_read_never_replaces_newer_selection'){
  queryMode='defer';c.foreground();await tick();assert.equal(queryPending.length,1);queryMode='resolve';c.chooseCalendar(2);await tick();
  queryPending[0]([clone(original)]);await tick();assert.equal(latest().calendarId,2);assert.equal(latest().events[0].id,23);
 }else if(scenario==='DST_days_use_local_midnight'){
  await ready(c);for(const [day,hours] of [['2026-03-08T12:00:00-04:00',23],['2026-11-01T12:00:00-05:00',25]]){
   c.view.day=Date.parse(day);await c.refresh();const query=calls.filter(x=>x[0]==='query').at(-1);assert.equal(query[3]-query[2],hours*3600000);
  }
 }else if(scenario==='invalid_backend_data_fails_closed'){
  for(const property of [{id:0},{id:2147483648},{startTime:-1},{endTime:start},{instanceEndTime:8640000000000001}]){
   data=[{...clone(original),...property}];c.foreground();await tick();assert.equal(latest().ready,false);assert.ok(latest().error);
  }assert.equal(writes().length,0);
 }else if(scenario==='out_of_range_date_no_query'){
  c.view.day=8640000000000000;c.foreground();await tick();assert.equal(latest().ready,false);assert.match(latest().error,/超出/);
  assert.equal(calls.filter(x=>x[0]==='query').length,0);
 }else throw new Error(scenario);
 console.log('PASS host-only '+scenario);
})().catch(error=>{console.error(error);process.exitCode=1;});
