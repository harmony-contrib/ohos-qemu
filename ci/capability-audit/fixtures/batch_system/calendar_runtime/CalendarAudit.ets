/* SPDX-License-Identifier: Apache-2.0; raw observations, not a pass oracle. */
import calendarManager from '@ohos.calendarManager';
import abilityAccessCtrl, { Permissions } from '@ohos.abilityAccessCtrl';
import bundleManager from '@ohos.bundle.bundleManager';
// observer-only imports BEGIN
import notificationManager from '@ohos.notificationManager';
import wantAgent from '@ohos.app.ability.wantAgent';
// observer-only imports END
import process from '@ohos.process';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';

interface Request {
  schema_version: number; run_id: string; boot_id: string; archive_sha256: string;
  operation_id: string; role: string; action: string; case_id: string;
  lead_minutes?: number; spacing_minutes?: number;
  cleanup_guard?: CleanupGuard;
}
interface CleanupGuard { calendar_id: number; events: calendarManager.Event[]; observed_ms: number; }
interface Row {
  schema_version: number; run_id: string; boot_id: string; archive_sha256: string;
  operation_id: string; role: string; action: string; case_id: string;
  sequence: number; timestamp_ms: number; uid: number; token_id: number;
  event: string; api: string; value_json: string; error_code: number; error_message: string;
}
interface State {
  run_id: string; calendar_id: number; event_ids: number[]; event_snapshots: string[];
}
interface CalendarAccountObservation { id: number; account: calendarManager.CalendarAccount; }
interface DisplayTime { id: number; start: string; end: string; }
const ROLE: string = '__ROLE__';
const RUN: string = '__RUN__';
const CASES: string[] = ['cold-deny', 'cold-allow', 'warm', 'after-restart'];
const LOW: Permissions[] = ['ohos.permission.READ_CALENDAR', 'ohos.permission.WRITE_CALENDAR'];
const WHOLE: Permissions[] = ['ohos.permission.READ_WHOLE_CALENDAR'];

export class CalendarAudit {
  private context: common.UIAbilityContext;
  private request: Request;
  private sequence: number = 0;
  private token: number;
  private path: string;
  private statePath: string;
  private accountName: string;
  private api: string = 'request';

  constructor(context: common.UIAbilityContext, serialized: string) {
    if (serialized.length === 0 || serialized.length > 8192) { throw new Error('Invalid request'); }
    const r: Request = JSON.parse(serialized) as Request;
    if (r.schema_version !== 1 || r.run_id !== RUN || r.role !== ROLE ||
      !/^[a-f0-9]{32}$/.test(r.operation_id) || !/^[a-f0-9-]{36}$/.test(r.boot_id) ||
      !/^[a-f0-9]{64}$/.test(r.archive_sha256) || !/^[a-z][a-z0-9-]{0,39}$/.test(r.case_id) ||
      !['permission', 'access', 'create', 'read', 'notifications', 'update', 'delete', 'cleanup', 'routes'].includes(r.action) ||
      (ROLE !== 'producer' && ['create', 'update', 'delete', 'cleanup', 'routes'].includes(r.action)) ||
      (ROLE !== 'observer' && r.action === 'notifications')) { throw new Error('Unexpected owned operation'); }
    this.context = context; this.request = r;
    this.accountName = 'qcal_' + RUN;
    this.path = context.filesDir + '/calendar-' + RUN + '-' + r.boot_id + '.jsonl';
    this.statePath = context.filesDir + '/calendar-state-' + RUN + '.json';
    if (fs.accessSync(this.path)) {
      if (fs.statSync(this.path).size > 4194304) { throw new Error('Oversized journal'); }
      const raw: string = fs.readTextSync(this.path);
      if (!raw.endsWith('\n')) { throw new Error('Truncated prior journal'); }
      for (const line of raw.trimEnd().split('\n')) {
        const row: Row = JSON.parse(line) as Row;
        if (row.run_id !== RUN || row.role !== ROLE || row.boot_id !== r.boot_id ||
          row.archive_sha256 !== r.archive_sha256 || row.sequence !== ++this.sequence ||
          row.operation_id === r.operation_id) { throw new Error('Reused or foreign journal'); }
      }
    }
    const self = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION);
    this.token = self.appInfo.accessTokenId;
    if (this.token <= 0 || Math.floor(process.uid / 200000) !== 100) { throw new Error('Actual account100 identity required'); }
    this.record('begin', 'request', JSON.stringify(r));
  }

  private record(event: string, api: string, value: string, code: number = 0, message: string = ''): void {
    const r: Request = this.request;
    const row: Row = { schema_version: 1, run_id: RUN, boot_id: r.boot_id, archive_sha256: r.archive_sha256,
      operation_id: r.operation_id, role: ROLE, action: r.action, case_id: r.case_id,
      sequence: ++this.sequence, timestamp_ms: Date.now(), uid: process.uid, token_id: this.token,
      event: event, api: api, value_json: value, error_code: code, error_message: message };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      let done: number = 0;
      while (done < bytes.byteLength) {
        const amount = fs.writeSync(file.fd, bytes.slice(done).buffer);
        if (amount <= 0 || amount > bytes.byteLength - done) { throw new Error('Short journal write'); }
        done += amount;
      }
    } finally { fs.closeSync(file); }
  }

  private state(): State {
    const state: State = JSON.parse(fs.readTextSync(this.statePath)) as State;
    if (state.run_id !== RUN || state.calendar_id <= 0 || state.event_ids.length > 4 ||
      !state.event_ids.every((id: number) => Number.isSafeInteger(id) && id > 0) ||
      new Set(state.event_ids).size !== state.event_ids.length || state.event_snapshots.length !== state.event_ids.length ||
      !state.event_snapshots.every((value: string) => value.length <= 65536)) { throw new Error('Invalid owned state'); }
    return state;
  }

  private saveState(state: State): void {
    const file = fs.openSync(this.statePath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC | fs.OpenMode.NOFOLLOW);
    try {
      const value: string = JSON.stringify(state);
      if (fs.writeSync(file.fd, value) !== new util.TextEncoder().encodeInto(value).byteLength) {
        throw new Error('Short state write; require public recovery audit');
      }
    } finally { fs.closeSync(file); }
  }

  private access(): void {
    const manager = abilityAccessCtrl.createAtManager();
    for (const permission of [...LOW, ...WHOLE]) {
      this.record('access', 'abilityAccessCtrl.checkAccessTokenSync', JSON.stringify({ permission: permission,
        grant: manager.checkAccessTokenSync(this.token, permission) }));
    }
  }

  private async calendars(): Promise<calendarManager.Calendar[]> {
    this.api = 'CalendarManager.getAllCalendars';
    const calendars = await calendarManager.getCalendarManager(this.context).getAllCalendars();
    return calendars.filter((item: calendarManager.Calendar) => item.getAccount().name === this.accountName &&
      item.getAccount().type === calendarManager.CalendarType.LOCAL);
  }

  private async owned(): Promise<calendarManager.Calendar> {
    const state = this.state();
    const calendars = await this.calendars();
    if (calendars.length !== 1 || calendars[0].id !== state.calendar_id) { throw new Error('Owned account identity differs'); }
    return calendars[0];
  }

  private async create(): Promise<void> {
    if (fs.accessSync(this.statePath) || (await this.calendars()).length !== 0) { throw new Error('Run account already exists'); }
    const manager = calendarManager.getCalendarManager(this.context);
    this.api = 'CalendarManager.createCalendar';
    const calendar = await manager.createCalendar({ name: this.accountName, type: calendarManager.CalendarType.LOCAL,
      displayName: 'Calendar QA ' + RUN.substring(0, 8) });
    const state: State = { run_id: RUN, calendar_id: calendar.id, event_ids: [], event_snapshots: [] };
    this.saveState(state);
    this.record('calendar-created', this.api, JSON.stringify({ id: calendar.id, account: calendar.getAccount() }));
    this.api = 'Calendar.setConfig'; await calendar.setConfig({ enableReminder: true });
    this.record('calendar-config', 'Calendar.getConfig', JSON.stringify(calendar.getConfig()));
    // Never set the guest clock. Align a real future wall-clock deadline to
    // provider minute granularity, leaving at least two minutes for setup.
    const lead: number = this.request.lead_minutes ?? 2;
    const spacing: number = this.request.spacing_minutes ?? 2;
    if (!Number.isInteger(lead) || !Number.isInteger(spacing) || lead < 2 || lead > 30 || spacing < 2 || spacing > 30) {
      throw new Error('Bounded real future schedule required');
    }
    const base: number = Math.ceil(Date.now() / 60000) * 60000 + lead * 60000;
    for (let index = 0; index < CASES.length; index++) {
      const event: calendarManager.Event = { type: calendarManager.EventType.NORMAL,
        title: 'QCAL_' + RUN + '_' + CASES[index], description: 'QNOTE_' + RUN + '_' + CASES[index],
        startTime: base + index * spacing * 60000, endTime: base + index * spacing * 60000 + 1800000,
        isAllDay: false, reminderTime: [0] };
      this.api = 'Calendar.addEvent';
      const id: number = await calendar.addEvent(event);
      if (!Number.isSafeInteger(id) || id <= 0) { throw new Error('Invalid public event ID'); }
      state.event_ids.push(id); state.event_snapshots.push(''); this.saveState(state);
      this.api = 'Calendar.getEvents';
      const stored = await calendar.getEvents(calendarManager.EventFilter.filterById([id]));
      if (stored.length !== 1 || stored[0].id !== id || stored[0].title !== event.title ||
        stored[0].description !== event.description || stored[0].startTime !== event.startTime ||
        stored[0].endTime !== event.endTime) { throw new Error('Created event readback uncertain; preserve account and state'); }
      state.event_snapshots[index] = JSON.stringify(stored[0]); this.saveState(state);
      this.record('event-created', 'Calendar.addEvent', JSON.stringify({ case_id: CASES[index], id: id, event: event }));
      this.record('event-snapshot', 'Calendar.getEvents', JSON.stringify({ case_id: CASES[index], id: id, event: stored[0] }));
    }
  }

  private async read(): Promise<void> {
    const values = await this.calendars();
    this.record('accounts', 'CalendarManager.getAllCalendars+Calendar.getAccount', JSON.stringify(values.map(
      (calendar: calendarManager.Calendar): CalendarAccountObservation => ({ id: calendar.id, account: calendar.getAccount() }))));
    for (const calendar of values) {
      this.api = 'Calendar.getEvents'; const events = await calendar.getEvents();
      const display: DisplayTime[] = events.map((event: calendarManager.Event): DisplayTime => ({
        id: event.id ?? -1, start: new Date(event.startTime).toLocaleString(), end: new Date(event.endTime).toLocaleString()
      }));
      this.record('events', this.api, JSON.stringify({ calendar_id: calendar.id, events: events, display: display }));
    }
  }

  private async change(remove: boolean): Promise<void> {
    const state = this.state(); const calendar = await this.owned();
    const index: number = CASES.indexOf(this.request.case_id);
    if (index < 0 || state.event_ids[index] <= 0) { throw new Error('No owned case ID'); }
    const id: number = state.event_ids[index];
    const events = await calendar.getEvents(calendarManager.EventFilter.filterById([id]));
    if (events.length !== 1 || events[0].id !== id ||
      !events[0].title?.startsWith('QCAL_' + RUN + '_') || !state.event_snapshots[index] ||
      state.event_snapshots[index] !== JSON.stringify(events[0])) { throw new Error('Refuse foreign, externally changed or missing event'); }
    if (remove) {
      this.api = 'Calendar.deleteEvent'; await calendar.deleteEvent(id);
    } else {
      events[0].title = 'QCAL_' + RUN + '_' + this.request.case_id + '_updated';
      events[0].description = 'QNOTE_' + RUN + '_updated';
      this.api = 'Calendar.updateEvent'; await calendar.updateEvent(events[0]);
      this.api = 'Calendar.getEvents';
      const current = await calendar.getEvents(calendarManager.EventFilter.filterById([id]));
      if (current.length !== 1 || JSON.stringify(current[0]) !== JSON.stringify(events[0])) {
        throw new Error('Updated event readback uncertain; preserve account and state');
      }
      state.event_snapshots[index] = JSON.stringify(current[0]); this.saveState(state);
      this.record('event-snapshot', 'Calendar.getEvents', JSON.stringify({ case_id: this.request.case_id, id: id, event: current[0] }));
    }
    this.record(remove ? 'event-deleted' : 'event-updated', remove ? 'Calendar.deleteEvent' : 'Calendar.updateEvent',
      JSON.stringify({ id: id, case_id: this.request.case_id }));
  }

  private async notifications(): Promise<void> {
    // observer-only observation BEGIN
    this.api = 'notificationManager.getAllActiveNotifications';
    const notifications = await notificationManager.getAllActiveNotifications();
    for (const item of notifications) {
      const title: string = item.content.normal?.title ?? item.content.longText?.title ?? '';
      if (!title.startsWith('QCAL_' + RUN + '_')) { continue; }
      this.record('notification', this.api, JSON.stringify(item));
      if (item.wantAgent === undefined) { throw new Error('Actual notification has no WantAgent'); }
      this.api = 'wantAgent.getWant'; const want = await wantAgent.getWant(item.wantAgent);
      const bundle: string = await wantAgent.getBundleName(item.wantAgent);
      const uid: number = await wantAgent.getUid(item.wantAgent);
      this.record('notification-want', 'wantAgent.getWant+getBundleName+getUid',
        JSON.stringify({ notification_id: item.id, title: title, want: want, bundle: bundle, uid: uid }));
    }
    this.record('notification-scan', 'notificationManager.getAllActiveNotifications', JSON.stringify({ observed: true }));
    // observer-only observation END
  }

  public async execute(): Promise<void> {
    try {
      this.access();
      const action: string = this.request.action;
      if (action === 'permission') {
        this.api = 'abilityAccessCtrl.requestPermissionsFromUser';
        const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(this.context,
          ROLE === 'producer' ? LOW : WHOLE);
        this.record('permission', this.api, JSON.stringify(result)); this.access();
      } else if (action === 'create') { await this.create(); await this.read(); }
      else if (action === 'read') { await this.read(); }
      else if (action === 'notifications') { await this.notifications(); }
      else if (action === 'update') { await this.change(false); await this.read(); }
      else if (action === 'delete') { await this.change(true); await this.read(); }
      else if (action === 'cleanup') {
        const calendar = await this.owned(); const state = this.state();
        const guard = this.request.cleanup_guard;
        if (guard === undefined || guard.calendar_id !== state.calendar_id || !Number.isSafeInteger(guard.observed_ms) ||
          guard.observed_ms > Date.now() || Date.now() - guard.observed_ms > 120000) {
          throw new Error('Fresh independent whole-calendar cleanup guard unavailable; preserve all data');
        }
        this.api = 'Calendar.getEvents'; const current = await calendar.getEvents();
        this.record('cleanup-inspection', this.api, JSON.stringify({ calendar_id: state.calendar_id, events: current }));
        if (current.length !== guard.events.length || new Set(current.map((event: calendarManager.Event): number => event.id ?? -1)).size !== current.length) {
          throw new Error('Foreign or incompletely visible calendar content; preserve all data');
        }
        for (const event of current) {
          const index: number = state.event_ids.indexOf(event.id ?? -1);
          const whole = guard.events.filter((item: calendarManager.Event) => item.id === event.id);
          if (index < 0 || !state.event_snapshots[index] || JSON.stringify(event) !== state.event_snapshots[index] ||
            whole.length !== 1 || JSON.stringify(whole[0]) !== JSON.stringify(event) ||
            !event.title?.startsWith('QCAL_' + RUN + '_')) {
            throw new Error('Foreign or externally changed event; preserve account and state');
          }
        }
        this.api = 'CalendarManager.deleteCalendar';
        await calendarManager.getCalendarManager(this.context).deleteCalendar(calendar);
        this.record('calendar-deleted', this.api, JSON.stringify({ id: state.calendar_id, account_name: this.accountName }));
        await this.read(); fs.unlinkSync(this.statePath);
      } else if (action === 'routes') {
        const state = this.state(); const calendar = await this.owned();
        for (const id of state.event_ids.slice(0, 2)) {
          const events = await calendar.getEvents(calendarManager.EventFilter.filterById([id]));
          if (events.length !== 1) { throw new Error('Owned event missing'); }
          const uri: string = `calendar://com.ohos.calendar?event_id=${id}&start=${events[0].startTime}&end=${events[0].endTime}`;
          this.api = 'UIAbilityContext.startAbility';
          await this.context.startAbility({ bundleName: 'com.ohos.calendardata', abilityName: 'MainAbility', uri: uri });
          this.record('route-request', this.api, JSON.stringify({ id: id, uri: uri }));
        }
      }
      this.record('complete', 'request', '{}');
    } catch (error) {
      const actual = error as BusinessError;
      this.record('error', this.api, '{}', actual.code ?? -1, actual.message ?? String(error));
      this.record('complete', 'request', '{}');
    }
  }
}
