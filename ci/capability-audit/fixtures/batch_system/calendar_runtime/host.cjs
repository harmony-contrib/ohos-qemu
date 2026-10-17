// Host service doubles only. These memory rows are never guest evidence.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
const source = fs.readFileSync(process.argv[2], 'utf8').replace(/^import .*?;\n/gm, '')
  .replace(/^export /gm, '').replaceAll('__ROLE__', 'producer').replaceAll('__RUN__', 'd'.repeat(32));
let storage = new Map(), fds = new Map(), nextFd = 0, calendars = [], nextId = 400;
let removed = [], writes = [], updates = [];
const run = 'd'.repeat(32), boot = '12345678-1234-1234-1234-123456789abc';
function calendar(name, id) {
  const rows = [];
  return {id, rows, getAccount() {return {name, type: 0};}, async setConfig(c) {this.config = c;}, getConfig() {return this.config;},
    async addEvent(event) {const id = nextId++; rows.push({...event, id}); writes.push(event); return id;},
    async getEvents(ids) {return JSON.parse(JSON.stringify(rows.filter(r => !ids || ids.includes(r.id))));},
    async updateEvent(event) {updates.push(event); const i=rows.findIndex(r=>r.id===event.id); if(i>=0)rows[i]=JSON.parse(JSON.stringify(event));},
    async deleteEvent(id) {removed.push(id); const i=rows.findIndex(r=>r.id===id); if(i>=0)rows.splice(i,1);}};
}
const foreign = calendar('foreign-real-records', 9); calendars.push(foreign);
const manager = {async getAllCalendars(){return calendars;}, async createCalendar(account){const c=calendar(account.name, 10);calendars.push(c);return c;},
  async deleteCalendar(c){removed.push('calendar/'+c.id);calendars=calendars.filter(x=>x!==c);}};
const io = {OpenMode:{CREATE:1,WRITE_ONLY:2,APPEND:4,NOFOLLOW:8,TRUNC:16},
  accessSync(p){return storage.has(p);}, statSync(p){return {size:Buffer.byteLength(storage.get(p))};}, readTextSync(p){if(!storage.has(p))throw new Error('missing');return storage.get(p);},
  openSync(p, mode){if(mode&16)storage.set(p,'');if(!storage.has(p))storage.set(p,'');const fd=++nextFd;fds.set(fd,p);return {fd};},
  writeSync(fd,data){const text=typeof data==='string'?data:Buffer.from(data).toString();const p=fds.get(fd);storage.set(p,storage.get(p)+text);return Buffer.byteLength(text);},
  closeSync(){}, unlinkSync(p){storage.delete(p);}};
const sandbox = {fs:io, util:{TextEncoder:class {encodeInto(text){return new TextEncoder().encode(text);}}}, process:{uid:20015001}, bundleManager:{BundleFlag:{GET_BUNDLE_INFO_WITH_APPLICATION:1},
  getBundleInfoForSelfSync(){return {appInfo:{accessTokenId:12345}};}},
  abilityAccessCtrl:{createAtManager(){return {checkAccessTokenSync(){return 0;},async requestPermissionsFromUser(){return {authResults:[0,0]};}};}},
  calendarManager:{CalendarType:{LOCAL:0},EventType:{NORMAL:0},EventFilter:{filterById(ids){return ids;}},getCalendarManager(){return manager;}}};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\nthis.Audit=CalendarAudit;',sandbox);
let operation = 0;
function request(action,case_id='cold-allow') {
  const value={schema_version:1,run_id:run,boot_id:boot,archive_sha256:'a'.repeat(64),
    operation_id:(++operation).toString(16).padStart(32,'0'),role:'producer',action,case_id};
  if(action==='cleanup') value.cleanup_guard={calendar_id:10,events:calendars.find(c=>c.id===10)?.rows??[],observed_ms:Date.now()};
  return JSON.stringify(value);
}
function journal(){return storage.get('/private/calendar-'+run+'-'+boot+'.jsonl').trim().split('\n').map(JSON.parse);}
(async()=>{
  assert.throws(()=>new sandbox.Audit({filesDir:'/private'},request('notifications')));
  await new sandbox.Audit({filesDir:'/private'},request('create')).execute();
  assert.equal(writes.length,4);assert.ok(writes.every(e=>e.reminderTime[0]===0&&e.startTime>Date.now()+119000));
  assert.equal(journal().filter(r=>r.event==='event-created').length,4);
  const before=writes.length;await new sandbox.Audit({filesDir:'/private'},request('create')).execute();assert.equal(writes.length,before);
  await new sandbox.Audit({filesDir:'/private'},request('update')).execute();assert.equal(updates.length,1);
  await new sandbox.Audit({filesDir:'/private'},request('delete')).execute();assert.deepEqual(removed,[401]);
  const state='/private/calendar-state-'+run+'.json';const original=storage.get(state);
  const altered=JSON.parse(original);altered.calendar_id=9;storage.set(state,JSON.stringify(altered));
  await new sandbox.Audit({filesDir:'/private'},request('cleanup')).execute();assert.deepEqual(removed,[401]);
  storage.set(state,original);
  const owned=calendars.find(c=>c.id===10), beforeRows=JSON.stringify(owned.rows);
  owned.rows.push({...owned.rows[0],id:999,title:'foreign event'});
  await new sandbox.Audit({filesDir:'/private'},request('cleanup')).execute();
  assert.deepEqual(removed,[401]);assert.equal(storage.get(state),original);assert.equal(owned.rows.at(-1).id,999);
  owned.rows.pop();owned.rows[0].description='external edit';
  await new sandbox.Audit({filesDir:'/private'},request('cleanup')).execute();
  assert.deepEqual(removed,[401]);assert.equal(storage.get(state),original);assert.equal(owned.rows[0].description,'external edit');
  owned.rows.splice(0,owned.rows.length,...JSON.parse(beforeRows));
  const withoutGuard=JSON.parse(request('cleanup'));delete withoutGuard.cleanup_guard;
  await new sandbox.Audit({filesDir:'/private'},JSON.stringify(withoutGuard)).execute();
  assert.deepEqual(removed,[401]);assert.equal(storage.get(state),original);
  for(const observed_ms of [Date.now()-120001,Date.now()+60000]) {
    const expired=JSON.parse(request('cleanup'));expired.cleanup_guard.observed_ms=observed_ms;
    await new sandbox.Audit({filesDir:'/private'},JSON.stringify(expired)).execute();
    assert.deepEqual(removed,[401]);assert.equal(storage.get(state),original);assert.equal(JSON.stringify(owned.rows),beforeRows);
  }
  // A normal reader hiding a foreign row must not override the independent
  // whole-reader guard. No delete is issued when their complete views differ.
  const hidden=JSON.parse(request('cleanup'));hidden.cleanup_guard.events.push({...owned.rows[0],id:1000});
  await new sandbox.Audit({filesDir:'/private'},JSON.stringify(hidden)).execute();
  assert.deepEqual(removed,[401]);assert.equal(storage.get(state),original);assert.equal(JSON.stringify(owned.rows),beforeRows);
  storage.set(state,original);await new sandbox.Audit({filesDir:'/private'},request('cleanup')).execute();
  assert.deepEqual(removed,[401,'calendar/10']);assert.equal(calendars.length,1);assert.equal(calendars[0],foreign);
  assert.equal(storage.has(state),false);const rows=journal();rows.forEach((r,i)=>assert.equal(r.sequence,i+1));
  console.log('PASS host-only actual QA source: future timing ownership foreign/changed/hidden cleanup refusal fresh guard sequence');
})().catch(e=>{console.error(e);process.exitCode=1;});
