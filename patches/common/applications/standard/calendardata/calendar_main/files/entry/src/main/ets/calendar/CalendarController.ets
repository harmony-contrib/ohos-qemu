/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import calendarManager from '@ohos.calendarManager';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@ohos.base';
import { CalendarRoute, parseCalendarRoute } from './CalendarRoute';

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

const EVENT_KEYS: (keyof calendarManager.Event)[] = ['id', 'type', 'title', 'startTime', 'endTime',
  'isAllDay', 'location', 'description', 'reminderTime', 'recurrenceRule', 'attendee', 'service',
  'identifier', 'isLunar', 'timeZone', 'instanceStartTime', 'instanceEndTime'];

export class CalendarController {
  private manager: calendarManager.CalendarManager;
  private calendars: calendarManager.Calendar[] = [];
  private view: CalendarView = new CalendarView();
  private route: CalendarRoute = new CalendarRoute();
  private routeError: string = '';
  private active: boolean = false;
  private disposed: boolean = false;
  private generation: number = 0;
  private writing: boolean = false;
  private readFilter: calendarManager.EventFilter | undefined = undefined;
  private publish: (view: CalendarView) => void;

  constructor(context: common.UIAbilityContext, publish: (view: CalendarView) => void) {
    this.manager = calendarManager.getCalendarManager(context);
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

  setUri(uri: string): void {
    this.generation++;
    this.route = new CalendarRoute();
    this.routeError = '';
    this.view.selected = undefined;
    this.view.events = [];
    this.view.ready = false;
    try {
      this.route = parseCalendarRoute(uri);
    } catch (error) {
      this.routeError = (error as BusinessError).message;
    }
    if (this.active && !this.writing) {
      this.refresh();
    }
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
    this.view.error = this.routeError;
    this.view.selected = undefined;
    this.view.events = [];
    this.emit();
    try {
      if (this.routeError.length > 0) {
        throw new Error(this.routeError);
      }
      const calendars = await this.manager.getAllCalendars();
      if (!this.current(generation)) {
        return;
      }
      if (calendars.length === 0) {
        calendars.push(await this.manager.getCalendar());
      }
      if (!this.current(generation)) {
        return;
      }
      if (calendars.length > 100 || calendars.some((item: calendarManager.Calendar) =>
        !Number.isInteger(item.id) || item.id <= 0)) {
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
      if (this.route.eventId > 0) {
        await this.findReminder(generation);
      } else {
        if (!calendars.some((item: calendarManager.Calendar) => item.id === this.view.calendarId)) {
          this.view.calendarId = calendars[0].id;
        }
        const calendar = this.calendar();
        const start = new Date(this.view.day);
        start.setHours(0, 0, 0, 0);
        const end = new Date(start.getTime());
        end.setDate(end.getDate() + 1);
        const events = await calendar.queryEventInstances(start.getTime(), end.getTime(), [], EVENT_KEYS);
        if (!this.current(generation)) {
          return;
        }
        this.checkEvents(events);
        this.view.day = start.getTime();
        this.view.events = events.sort((a: calendarManager.Event, b: calendarManager.Event) =>
          (a.instanceStartTime ?? a.startTime) - (b.instanceStartTime ?? b.startTime));
      }
      if (this.current(generation)) {
        this.view.ready = true;
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = (error as BusinessError).message || '日历读取失败';
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

  private async findReminder(generation: number): Promise<void> {
    const route = this.route;
    for (const calendar of this.calendars) {
      const events = await calendar.queryEventInstances(route.start, route.end, [route.eventId], EVENT_KEYS);
      if (!this.current(generation)) {
        return;
      }
      this.checkEvents(events);
      const event = events.find((item: calendarManager.Event) => item.id === route.eventId &&
        (item.instanceStartTime ?? item.startTime) === route.start &&
        (item.instanceEndTime ?? item.endTime) === route.end);
      if (event !== undefined) {
        this.view.calendarId = calendar.id;
        this.view.day = route.start;
        this.view.events = [event];
        this.view.selected = event;
        return;
      }
    }
    throw new Error('提醒对应的日程已删除、已变更或当前账号不可访问');
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
    this.route = new CalendarRoute();
    this.routeError = '';
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
    this.route = new CalendarRoute();
    this.routeError = '';
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
      this.route = new CalendarRoute();
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
        (reminder !== undefined && (!/^(0|[1-9][0-9]{0,4})$/.test(reminderText) || reminder > 10080))) {
        throw new Error('请检查标题、开始和结束时间、提醒分钟数（0–10080）');
      }
      let event: calendarManager.Event = { type: calendarManager.EventType.NORMAL,
        title: title, startTime: start, endTime: end, description: description };
      if (existingId > 0) {
        if (this.view.selected?.id !== existingId || !this.editable(this.view.selected)) {
          throw new Error('该日程仅支持查看，不能在此编辑');
        }
        // Keep the native filter wrapper strongly owned across the async read,
        // including background/dispose, until the actual promise settles.
        this.readFilter = calendarManager.EventFilter.filterById([existingId]);
        const current = await calendar.getEvents(this.readFilter, EVENT_KEYS);
        if (!this.current(generation)) {
          return;
        }
        if (current.length !== 1 || current[0].id !== existingId || !this.editable(current[0])) {
          throw new Error('日程已变更，请刷新后重试');
        }
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
      this.view.notice = '日程已保存';
      // A deep link must not continue selecting a deleted/changed instance.
      if (this.current(generation)) {
        this.route = new CalendarRoute();
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = (error as BusinessError).message || '日程保存失败';
      }
    } finally {
      this.readFilter = undefined;
      this.writing = false;
      if (submitted || generation !== this.generation) {
        if (this.active && !this.disposed) {
          // Read again after a submitted transaction, including when its UI
          // was backgrounded. Never pretend that a submitted write was undone.
          const error = this.view.error;
          await this.refresh();
          if (error.length > 0) {
            this.view.error = error;
          }
        }
      }
      this.emit();
    }
  }

  async remove(id: number, confirmed: boolean): Promise<void> {
    if (!confirmed || !this.active || this.disposed || this.writing || !this.view.ready ||
      this.view.selected?.id !== id || !this.editable(this.view.selected)) {
      return;
    }
    const generation = this.generation;
    const calendar = this.calendar();
    this.writing = true;
    this.view.error = '';
    this.emit();
    try {
      await calendar.deleteEvent(id);
      this.view.notice = '日程已删除';
      if (this.current(generation)) {
        this.route = new CalendarRoute();
      }
    } catch (error) {
      if (this.current(generation)) {
        this.view.error = (error as BusinessError).message || '删除失败';
      }
    } finally {
      this.writing = false;
      if (this.active && !this.disposed) {
        const error = this.view.error;
        await this.refresh();
        if (error.length > 0) {
          this.view.error = error;
        }
      }
      this.emit();
    }
  }
}
