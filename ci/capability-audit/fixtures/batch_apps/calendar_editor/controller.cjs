const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
const code = stripTypeScriptTypes(fs.readFileSync(process.argv[2], 'utf8').replace(/^import .*?;\n/gm, '').replace('export class', 'class'), {mode:'transform'});
const original = {type:0,title:'Requested event',startTime:1800000000000,endTime:1800003600000,description:'Original note',reminderTime:[10],recurrenceRule:{recurrenceFrequency:1}};
let managerCalls=0, adds=[], results=[], getMode='resolve', addMode='resolve', resultMode='resolve', nextId=73, getPending, addPending;
const calendar={addEvent(event) {adds.push(event);if(addMode==='reject')return Promise.reject(new Error('permission denied'));if(addMode==='defer')return new Promise(r=>addPending=r);return Promise.resolve(nextId);}};
const sandbox={calendarManager:{EventType:{NORMAL:0},getCalendarManager(){managerCalls++;return {getCalendar(){if(getMode==='reject')return Promise.reject(new Error('not permitted'));if(getMode==='defer')return new Promise(r=>getPending=r);return Promise.resolve(calendar);}};}}};
vm.createContext(sandbox);vm.runInContext(code+'\nthis.Controller=EventEditorController;',sandbox);
function create(event=original){return new sandbox.Controller({}, {terminateSelfWithResult(result){results.push(result);return resultMode==='reject'?Promise.reject(new Error('host unavailable')):Promise.resolve();}},JSON.stringify(event));}
const args=['Edited title',new Date(original.startTime).toISOString(),new Date(original.endTime).toISOString(),'Edited note'];
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const scenario=process.argv[3];
 if(scenario==='validation'){
  for(const mutation of [{id:7},{type:1},{instanceStartTime:4},{instanceEndTime:5},{identifier:'x'},{attendee:[]},{service:{}},{isLunar:false},{timeZone:'UTC'},{startTime:NaN},{endTime:original.startTime},{title:4},{description:'x'.repeat(5001)}])assert.throws(()=>create({...original,...mutation}));
  for(const text of ['null','[]','false','{','x'.repeat(65537)])assert.throws(()=>new sandbox.Controller({}, {},text));
  assert.equal(managerCalls,0);assert.equal(adds.length,0);
 } else if(scenario==='cancel'){
  const c=create();assert.equal(managerCalls,0);await c.cancel();await c.cancel();assert.equal(results.length,1);assert.equal(results[0].want.parameters.eventId,-1);assert.equal(adds.length,0);
 } else if(scenario==='save'){
  addMode='defer';const c=create();const saving=c.save(...args);await tick();assert.equal(results.length,0);assert.equal(c.eventId,-1);assert.equal(adds.length,1);assert.equal(adds[0].title,'Edited title');assert.equal(adds[0].description,'Edited note');assert.equal(JSON.stringify(adds[0].recurrenceRule),JSON.stringify(original.recurrenceRule));await c.save(...args);await c.cancel();assert.equal(adds.length,1);addPending(84);await saving;assert.equal(results[0].want.parameters.eventId,84);assert.equal(c.eventId,84);await c.save(...args);assert.equal(adds.length,1);
 } else if(scenario==='write_failure'){
  addMode='reject';const c=create();await c.save(...args);assert.match(c.error,/permission denied/);assert.equal(results.length,0);assert.equal(c.eventId,-1);addMode='resolve';await c.save(...args);assert.equal(results[0].want.parameters.eventId,73);
 } else if(scenario==='read_failure'){
  getMode='reject';const c=create();await c.save(...args);assert.match(c.error,/not permitted/);assert.equal(adds.length,0);assert.equal(results.length,0);
 } else if(scenario==='delivery_retry'){
  resultMode='reject';const c=create();await c.save(...args);assert.equal(adds.length,1);assert.equal(c.eventId,73);assert.match(c.error,/host unavailable/);resultMode='resolve';await c.save(...args);assert.equal(adds.length,1);assert.equal(results.length,2);assert.equal(results[1].want.parameters.eventId,73);
 } else if(scenario==='invalid_backend_id'){
  for(const id of [0,-1,3.5,2147483648]){nextId=id;const c=create();await c.save(...args);assert.equal(c.eventId,-1);assert.equal(results.length,0);assert.ok(c.error.length>0);}
 } else if(scenario==='invalid_edited_fields'){
  const c=create();for(const values of [['x','invalid',args[2],''],['x',args[1],args[1],''],['x'.repeat(5001),args[1],args[2],'']]){await c.save(...values);assert.ok(c.error.length>0);}assert.equal(managerCalls,0);assert.equal(adds.length,0);
 } else if(scenario==='destroy_before_write'){
  getMode='defer';const c=create();const saving=c.save(...args);c.dispose();getPending(calendar);await saving;assert.equal(adds.length,0);assert.equal(results.length,0);await c.save(...args);await c.cancel();assert.equal(results.length,0);
 } else if(scenario==='destroy_during_write'){
  addMode='defer';const c=create();const saving=c.save(...args);await tick();c.dispose();addPending(91);await saving;assert.equal(adds.length,1);assert.equal(c.eventId,91);assert.equal(results.length,0);
 } else if(scenario==='isolated_sessions'){
  const first=create(),second=create({...original,title:'other session'});first.dispose();await first.save(...args);await second.save(...args);assert.equal(adds.length,1);assert.equal(results.length,1);
 } else throw new Error(scenario);
 console.log('PASS '+scenario);
})().catch(error=>{console.error(error);process.exitCode=1;});
