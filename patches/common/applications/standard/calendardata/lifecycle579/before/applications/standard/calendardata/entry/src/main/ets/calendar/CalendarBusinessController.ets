/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import calendarManager from '@ohos.calendarManager';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';

export class CalendarChoice {
  id: number = 0;
  label: string = '';
}

export class CalendarView {
  calendars: CalendarChoice[] = [];
  calendarId: number = 0;
  events: calendarManager.Event[] = [];
  selected: calendarManager.Event | undefined = undefined;
  day: number = Date.now();
  error: string = '';
  notice: string = '';
  loading: boolean = false;
  writing: boolean = false;
  ready: boolean = false;
}

export class CalendarBusinessController {
  private manager: calendarManager.CalendarManager | undefined = undefined;
  private context: common.UIAbilityContext;
  private calendars: calendarManager.Calendar[] = [];
  private view: CalendarView = new CalendarView();
  private active: boolean = false;
  private disposed: boolean = false;
  private generation: number = 0;
  private writing: boolean = false;
  private readFilter: calendarManager.EventFilter | undefined = undefined;
  private publish: (view: CalendarView) => void;

  constructor(context: common.UIAbilityContext, publish: (view: CalendarView) => void) {
    this.context = context;
    this.publish = publish;
  }

  private emit(): void {
    if (!this.active || this.disposed) {
      return;
    }
    const next = new CalendarView();
    next.calendars = this.view.calendars.slice();
    next.calendarId = this.view.calendarId;
    next.events = this.view.events.slice();
    next.selected = this.view.selected;
    next.day = this.view.day;
    next.error = this.view.error;
    next.notice = this.view.notice;
    next.loading = this.view.loading;
    next.writing = this.writing;
    next.ready = this.view.ready;
    this.publish(next);
  }

  private current(generation: number): boolean {
    return this.active && !this.disposed && generation === this.generation;
  }


  foreground(): void {
    if (this.disposed) {
      return;
    }
    this.active = true;
    this.refresh();
  }

  background(): void {
    this.active = false;
    this.generation++;
    this.calendars = [];
    this.view = new CalendarView();
    // No queued mutation may start after background/destroy. An already
    // submitted provider transaction cannot be cancelled by destroying a UI.
    this.publish(new CalendarView());
  }

  dispose(): void {
    this.background();
    this.disposed = true;
  }

  async refresh(): Promise<void> {
    if (!this.active || this.disposed || this.writing) {
      return;
    }
    const generation = ++this.generation;
    this.view.loading = true;
    this.view.ready = false;
    this.view.error = '';
    this.view.notice = '';
    this.view.selected = undefined;
    this.view.events = [];
    this.emit();
    try {
      const grants = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(
        this.context, ['ohos.permission.READ_WHOLE_CALENDAR']);
      if (!this.current(generation)) {
        return;
      }
      if (grants.permissions.length !== 1 || grants.permissions[0] !== 'ohos.permission.READ_WHOLE_CALENDAR' ||
        grants.authResults.length !== 1 || grants.authResults[0] !== 0) {
        throw new Error('未授予读取日历权限；可授权后重新读取');
      }
      const manager = this.manager ?? calendarManager.getCalendarManager(this.context);
      this.manager = manager;
      const calendars = await manager.getAllCalendars();
      if (!this.current(generation)) {
        return;
      }
      if (calendars.length === 0) {
        calendars.push(await manager.getCalendar());
      }
      if (!this.current(generation)) {
        return;
      }
      if (calendars.length > 100 || calendars.some((item: calendarManager.Calendar) =>
        !Number.isInteger(item.id) || item.id <= 0 || item.id > 2147483647)) {
        throw new Error('日历列表无效或超过当前显示范围');
      }
      this.calendars = calendars;
      this.view.calendars = calendars.map((item: calendarManager.Calendar) => {
        const choice = new CalendarChoice();
        choice.id = item.id;
        const account = item.getAccount();
        choice.label = account.displayName || account.name;
        return choice;
      });
      if (!calendars.some((item: calendarManager.Calendar) => item.id === this.view.calendarId)) {
        this.view.calendarId = calendars[0].id;
      }
      const calendar = this.calendar();
      const start = new Date(this.view.day);
      start.setHours(0, 0, 0, 0);
      const end = new Date(start.getTime());
      end.setDate(end.getDate() + 1);
      if (!Number.isSafeInteger(start.getTime()) || !Number.isSafeInteger(end.getTime()) ||
        start.getTime() < 0 || end.getTime() > 8640000000000000 || end.getTime() <= start.getTime()) {
        throw new Error('日期超出当前显示范围');
      }
      const events = await calendar.queryEventInstances(start.getTime(), end.getTime(), [], ['id', 'type', 'title', 'startTime', 'endTime',
  'isAllDay', 'location', 'description', 'reminderTime', 'recurrenceRule', 'attendee', 'service',
  'identifier', 'isLunar', 'timeZone', 'instanceStartTime', 'instanceEndTime']);
      if (!this.current(generation)) {
        return;
      }
      this.checkEvents(events);
      this.view.day = start.getTime();
      this.view.events = events.sort((a: calendarManager.Event, b: calendarManager.Event) =>
        (a.instanceStartTime ?? a.startTime) - (b.instanceStartTime ?? b.startTime));
      if (this.current(generation)) {
        this.view.ready = true;
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = this.failure(error as BusinessError, '日历读取失败');
        this.view.events = [];
        this.view.selected = undefined;
      }
    } finally {
      if (this.current(generation)) {
        this.view.loading = false;
        this.emit();
      }
    }
  }

  private checkEvents(events: calendarManager.Event[]): void {
    if (events.length > 4096 || events.some((event: calendarManager.Event) => {
      const start = event.instanceStartTime ?? event.startTime;
      const end = event.instanceEndTime ?? event.endTime;
      return !Number.isInteger(event.id) || (event.id ?? 0) <= 0 || (event.id ?? 0) > 2147483647 ||
        !Number.isSafeInteger(event.startTime) || !Number.isSafeInteger(event.endTime) ||
        event.startTime < 0 || event.endTime > 8640000000000000 || event.endTime <= event.startTime ||
        !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 ||
        end > 8640000000000000 || end <= start;
    })) {
      throw new Error('日程数据无效或超过当前显示范围');
    }
  }


  private calendar(): calendarManager.Calendar {
    const calendar = this.calendars.find((item: calendarManager.Calendar) => item.id === this.view.calendarId);
    if (calendar === undefined) {
      throw new Error('请先选择可访问的日历');
    }
    return calendar;
  }

  chooseCalendar(id: number): void {
    if (!this.active || this.writing || !this.calendars.some((item: calendarManager.Calendar) => item.id === id)) {
      return;
    }
    this.view.calendarId = id;
    this.refresh();
  }

  moveDay(offset: number): void {
    if (!this.active || this.writing || !Number.isInteger(offset) || Math.abs(offset) > 1) {
      return;
    }
    const day = new Date(this.view.day);
    day.setDate(day.getDate() + offset);
    this.view.day = offset === 0 ? Date.now() : day.getTime();
    this.refresh();
  }

  select(id: number, start: number): void {
    const event = this.view.events.find((item: calendarManager.Event) => item.id === id &&
      (item.instanceStartTime ?? item.startTime) === start);
    if (this.active && !this.writing && this.view.ready && event !== undefined) {
      this.view.selected = event;
      this.emit();
    }
  }

  cancel(): void {
    if (this.active && !this.writing) {
      this.view.selected = undefined;
      this.view.error = '';
      this.emit();
    }
  }

  private editable(event: calendarManager.Event): boolean {
    // Recurring/all-day/lunar/important events remain visible; this small UI
    // must not silently rewrite their richer series or instance semantics.
    return event.type === calendarManager.EventType.NORMAL && event.recurrenceRule === undefined &&
      !event.isAllDay && !event.isLunar && (event.reminderTime?.length ?? 0) <= 1;
  }

  async save(title: string, startText: string, endText: string, description: string,
    reminderText: string, existingId: number): Promise<void> {
    if (!this.active || this.disposed || this.writing || !this.view.ready) {
      return;
    }
    const generation = this.generation;
    let submitted = false;
    this.writing = true;
    this.view.error = '';
    this.view.notice = '';
    this.emit();
    try {
      const calendar = this.calendar();
      const start = Date.parse(startText);
      const end = Date.parse(endText);
      const reminder = reminderText.length === 0 ? undefined : Number(reminderText);
      if (title.trim().length === 0 || title.length > 5000 || description.length > 5000 ||
        !Number.isInteger(existingId) || existingId < 0 || existingId > 2147483647 ||
        !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 ||
        end <= start || end > 8640000000000000 ||
        new Date(start).toISOString() !== startText || new Date(end).toISOString() !== endText ||
        (reminder !== undefined && (!/^(0|[1-9][0-9]{0,4})$/.test(reminderText) || reminder > 10080))) {
        throw new Error('请检查标题、开始和结束时间、提醒分钟数（0–10080）');
      }
      if (existingId > 0 && (this.view.selected?.id !== existingId || !this.editable(this.view.selected))) {
        throw new Error('该日程仅支持查看，不能在此编辑');
      }
      if (!await this.requestWrite(generation)) {
        return;
      }
      let event: calendarManager.Event = { type: calendarManager.EventType.NORMAL,
        title: title, startTime: start, endTime: end, description: description, timeZone: 'UTC' };
      if (existingId > 0) {
        // Keep the native filter wrapper strongly owned across the async read,
        // including background/dispose, until the actual promise settles.
        this.readFilter = calendarManager.EventFilter.filterById([existingId]);
        const current = await calendar.getEvents(this.readFilter, ['id', 'type', 'title', 'startTime', 'endTime',
  'isAllDay', 'location', 'description', 'reminderTime', 'recurrenceRule', 'attendee', 'service',
  'identifier', 'isLunar', 'timeZone', 'instanceStartTime', 'instanceEndTime']);
        if (!this.current(generation)) {
          return;
        }
        if (current.length !== 1 || current[0].id !== existingId || !this.editable(current[0])) {
          throw new Error('日程已变更，请刷新后重试');
        }
        this.checkEvents(current);
        // Preserve every untouched public field; do not replace the event
        // with a reduced title/time object and erase attendees or services.
        event = current[0];
        event.title = title;
        event.startTime = start;
        event.endTime = end;
        event.description = description;
        event.instanceStartTime = undefined;
        event.instanceEndTime = undefined;
      }
      event.reminderTime = reminder === undefined ? [] : [reminder];
      if (!this.current(generation)) {
        return;
      }
      submitted = true;
      if (existingId > 0) {
        await calendar.updateEvent(event);
      } else {
        const id = await calendar.addEvent(event);
        if (!Number.isInteger(id) || id <= 0 || id > 2147483647) {
          throw new Error('日程保存未返回有效编号；请先刷新确认，勿重复提交');
        }
      }
      if (this.current(generation)) {
        this.view.notice = '日程已保存';
        this.view.day = start;
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = this.failure(error as BusinessError, '日程保存失败') +
          (submitted ? '；已请求重新读取，请确认结果后再操作' : '');
      }
    } finally {
      this.readFilter = undefined;
      this.writing = false;
      if (submitted || generation !== this.generation) {
        if (this.active && !this.disposed) {
          // Read again after a submitted transaction, including when its UI
          // was backgrounded. Never pretend that a submitted write was undone.
          const error = this.current(generation) ? this.view.error : '';
          const notice = this.current(generation) ? this.view.notice : '';
          const refreshGeneration = this.generation + 1;
          await this.refresh();
          if (this.current(refreshGeneration)) {
            if (this.view.ready) {
              this.view.notice = notice;
            }
            if (error.length > 0) {
              this.view.error = error + (this.view.ready ? '' : '；重新读取也失败，请稍后确认');
            }
          }
        }
      }
      this.emit();
    }
  }

  private async requestWrite(generation: number): Promise<boolean> {
    const grants = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(
      this.context, ['ohos.permission.WRITE_WHOLE_CALENDAR']);
    if (!this.current(generation)) {
      return false;
    }
    if (grants.permissions.length !== 1 || grants.permissions[0] !== 'ohos.permission.WRITE_WHOLE_CALENDAR' ||
      grants.authResults.length !== 1 || grants.authResults[0] !== 0) {
      throw new Error('未授予修改日历权限；本次操作未提交');
    }
    return true;
  }

  private failure(error: BusinessError, fallback: string): string {
    if (error.code === 201) {
      return '日历权限已被拒绝或撤回，请检查权限后重试';
    }
    if (error.code === 801) {
      return '当前设备不支持此日历操作';
    }
    if (error.code === 23900003) {
      return '日历账号已不可用，请重新读取';
    }
    return (error.message || fallback) + (error.code ? `（${error.code}）` : '');
  }

  private deleteString(value: string | undefined): string {
    if (value === undefined) {
      return 'undefined';
    }
    if (typeof value !== 'string' || value.length > 5000) {
      throw new Error('日程数据无法安全比较，请刷新后重试');
    }
    return JSON.stringify(value);
  }

  private deleteNumber(value: number | undefined): string {
    if (value === undefined) {
      return 'undefined';
    }
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new Error('日程数据无法安全比较，请刷新后重试');
    }
    return JSON.stringify(value);
  }

  private deleteBoolean(value: boolean | undefined): string {
    if (value === undefined) {
      return 'undefined';
    }
    if (typeof value !== 'boolean') {
      throw new Error('日程数据无法安全比较，请刷新后重试');
    }
    return value ? 'true' : 'false';
  }

  private deleteSnapshot(event: calendarManager.Event): string {
    // Explicit SDK Event projection: no object/key order or JSON coercion can
    // hide a changed public field. Unknown shapes cannot authorize deletion.
    if (event === null || typeof event !== 'object' || Array.isArray(event) ||
      Object.keys(event).some((key: string) => !['id', 'type', 'title', 'startTime', 'endTime',
        'isAllDay', 'location', 'description', 'reminderTime', 'recurrenceRule', 'attendee', 'service',
        'identifier', 'isLunar', 'timeZone', 'instanceStartTime', 'instanceEndTime'].includes(key))) {
      throw new Error('日程数据无法安全比较，请刷新后重试');
    }
    this.checkEvents([event]);
    const fields: string[] = [this.deleteNumber(event.id), this.deleteNumber(event.type),
      this.deleteString(event.title), this.deleteNumber(event.startTime), this.deleteNumber(event.endTime),
      this.deleteBoolean(event.isAllDay), this.deleteString(event.description),
      event.identifier === null ? 'null' : this.deleteString(event.identifier),
      this.deleteBoolean(event.isLunar), this.deleteString(event.timeZone)];
    if (!this.editable(event)) {
      throw new Error('日程无法安全比较或已变更为只读类型，请刷新后重试');
    }
    // Instances are query-derived, not independent base Event fields. Only the
    // non-recurring ordinary event can be edited: its instance must equal base
    // times, or both derived fields may be omitted by getEvents().
    if (!((event.instanceStartTime === undefined && event.instanceEndTime === undefined) ||
      (event.instanceStartTime === event.startTime && event.instanceEndTime === event.endTime))) {
      throw new Error('日程实例与原始时间不一致，请刷新后重试');
    }
    fields.push('recurrenceRule:undefined');
    if (event.location === undefined || event.location === null) {
      fields.push(event.location === undefined ? 'undefined' : 'null');
    } else {
      const location = event.location;
      if (typeof location !== 'object' || Array.isArray(location) ||
        Object.keys(location).some((key: string) => !['location', 'longitude', 'latitude'].includes(key))) {
        throw new Error('日程地点无法安全比较，请刷新后重试');
      }
      fields.push(JSON.stringify([this.deleteString(location.location),
        this.deleteNumber(location.longitude), this.deleteNumber(location.latitude)]));
    }
    if (event.reminderTime === undefined) {
      fields.push('undefined');
    } else {
      if (!Array.isArray(event.reminderTime) || Object.keys(event.reminderTime).length !== event.reminderTime.length) {
        throw new Error('日程提醒无法安全比较，请刷新后重试');
      }
      const reminders: string[] = [];
      for (const value of event.reminderTime) {
        if (typeof value !== 'number') {
          throw new Error('日程提醒无法安全比较，请刷新后重试');
        }
        reminders.push(this.deleteNumber(value));
      }
      fields.push(JSON.stringify(reminders));
    }
    if (event.attendee === undefined || event.attendee === null) {
      fields.push(event.attendee === undefined ? 'undefined' : 'null');
    } else {
      if (!Array.isArray(event.attendee) || Object.keys(event.attendee).length !== event.attendee.length) {
        throw new Error('日程参与者无法安全比较，请刷新后重试');
      }
      const attendees: string[] = [];
      for (const attendee of event.attendee) {
        if (attendee === null || typeof attendee !== 'object' || Array.isArray(attendee) ||
          Object.keys(attendee).some((key: string) => !['name', 'email', 'role', 'type', 'status'].includes(key)) ||
          typeof attendee.name !== 'string' || typeof attendee.email !== 'string' ||
          (attendee.role !== undefined && attendee.role !== 'organizer' && attendee.role !== 'participant') ||
          (attendee.type !== undefined && (!Number.isInteger(attendee.type) || attendee.type < 1 || attendee.type > 3)) ||
          (attendee.status !== undefined && (!Number.isInteger(attendee.status) || attendee.status < 0 || attendee.status > 4))) {
          throw new Error('日程参与者无法安全比较，请刷新后重试');
        }
        attendees.push(JSON.stringify([this.deleteString(attendee.name), this.deleteString(attendee.email),
          this.deleteString(attendee.role), this.deleteNumber(attendee.type), this.deleteNumber(attendee.status)]));
      }
      fields.push(JSON.stringify(attendees));
    }
    if (event.service === undefined) {
      fields.push('undefined');
    } else {
      const service = event.service;
      if (service === null || typeof service !== 'object' || Array.isArray(service) ||
        Object.keys(service).some((key: string) => !['type', 'uri', 'description'].includes(key)) ||
        !['Meeting', 'Watching', 'Repayment', 'Live', 'Shopping', 'Trip', 'Class', 'SportsEvents',
          'SportsExercise'].includes(service.type) || typeof service.uri !== 'string') {
        throw new Error('日程服务无法安全比较，请刷新后重试');
      }
      fields.push(JSON.stringify([this.deleteString(service.type), this.deleteString(service.uri),
        this.deleteString(service.description)]));
    }
    return JSON.stringify(fields);
  }

  async remove(id: number, confirmed: boolean): Promise<void> {
    const selected = this.view.selected;
    if (!confirmed || !this.active || this.disposed || this.writing || !this.view.ready ||
      !Number.isInteger(id) || id <= 0 || id > 2147483647 ||
      selected === undefined || selected.id !== id) {
      return;
    }
    const generation = this.generation;
    let submitted = false;
    let refreshRequired = false;
    this.writing = true;
    this.view.error = '';
    this.view.notice = '';
    this.emit();
    try {
      refreshRequired = true;
      const displayedSnapshot = this.deleteSnapshot(selected);
      refreshRequired = false;
      const calendar = this.calendar();
      if (!await this.requestWrite(generation)) {
        return;
      }
      // Re-read after the user grants WRITE: the displayed item may have
      // been removed or changed into a recurring/read-only event meanwhile.
      this.readFilter = calendarManager.EventFilter.filterById([id]);
      const current = await calendar.getEvents(this.readFilter, ['id', 'type', 'title', 'startTime', 'endTime',
  'isAllDay', 'location', 'description', 'reminderTime', 'recurrenceRule', 'attendee', 'service',
  'identifier', 'isLunar', 'timeZone', 'instanceStartTime', 'instanceEndTime']);
      if (!this.current(generation)) {
        return;
      }
      refreshRequired = true;
      this.checkEvents(current);
      if (current.length !== 1 || current[0].id !== id ||
        this.deleteSnapshot(current[0]) !== displayedSnapshot) {
        throw new Error('日程已变更，请刷新后重试');
      }
      // This read/compare/delete is still not an atomic CAS: the public API
      // accepts only the ID, with no expected-version transaction argument.
      refreshRequired = false;
      submitted = true;
      await calendar.deleteEvent(id);
      if (this.current(generation)) {
        this.view.notice = '日程已删除';
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = this.failure(error as BusinessError, '删除失败') +
          (submitted ? '；已请求重新读取，请确认结果后再操作' : '');
      }
    } finally {
      this.readFilter = undefined;
      this.writing = false;
      if ((submitted || refreshRequired || generation !== this.generation) && this.active && !this.disposed) {
        const error = this.current(generation) ? this.view.error : '';
        const notice = this.current(generation) ? this.view.notice : '';
        const refreshGeneration = this.generation + 1;
        await this.refresh();
        if (this.current(refreshGeneration)) {
          if (this.view.ready) {
            this.view.notice = notice;
          }
          if (error.length > 0) {
            this.view.error = error + (this.view.ready ? '' : '；重新读取也失败，请稍后确认');
          }
        }
      }
      this.emit();
    }
  }
}
