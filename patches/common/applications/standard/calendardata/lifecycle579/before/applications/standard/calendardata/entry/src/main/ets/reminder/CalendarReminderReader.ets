/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import calendarManager from '@ohos.calendarManager';
import common from '@ohos.app.ability.common';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';

// Accept the existing provider's URI contract, including persisted reminders.
// Query times are untrusted routing hints; display only the persisted event.
export function parseCalendarReminder(uri: string): number {
  if (typeof uri !== 'string' || uri.length > 512) {
    throw new Error('无效的日程链接');
  }
  const match: RegExpMatchArray | null = uri.match(
    /^calendar:\/\/com\.ohos\.calendar\?event_id=([1-9][0-9]*)&start=(0|[1-9][0-9]*)&end=(0|[1-9][0-9]*)$/);
  if (match === null) {
    throw new Error('无效的日程链接');
  }
  const id: number = Number(match[1]);
  const start: number = Number(match[2]);
  const end: number = Number(match[3]);
  if (!Number.isSafeInteger(id) || id > 2147483647 || !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) || end > 8640000000000000 || end < start) {
    throw new Error('无效的日程链接');
  }
  return id;
}

export class CalendarReminderReader {
  public event: calendarManager.Event | undefined = undefined;
  public status: string = '';
  private context: common.UIAbilityContext;
  private generation: number = 0;
  private active: boolean = true;

  constructor(context: common.UIAbilityContext) {
    this.context = context;
  }

  public dispose(): void {
    this.active = false;
    this.generation++;
    this.event = undefined;
  }

  public async open(uri: string): Promise<void> {
    if (!this.active) {
      return;
    }
    const generation: number = ++this.generation;
    this.event = undefined;
    this.status = '正在读取日程';
    try {
      if (uri === '') {
        this.status = '请从日程提醒打开对应日程';
        return;
      }
      const id: number = parseCalendarReminder(uri);
      // The exported Ability grants no read result to its caller. The user
      // grants the existing whole-calendar permission before UI-only reading.
      const grants = await abilityAccessCtrl.createAtManager()
        .requestPermissionsFromUser(this.context, ['ohos.permission.READ_WHOLE_CALENDAR']);
      if (!this.current(generation)) {
        return;
      }
      if (grants.authResults.length !== 1 || grants.authResults[0] !== 0) {
        throw new Error('未授予读取日历权限');
      }
      const manager: calendarManager.CalendarManager = calendarManager.getCalendarManager(this.context);
      const calendars: calendarManager.Calendar[] = await manager.getAllCalendars();
      if (!this.current(generation)) {
        return;
      }
      for (const calendar of calendars) {
        const events: calendarManager.Event[] = await calendar.getEvents(calendarManager.EventFilter.filterById([id]));
        if (!this.current(generation)) {
          return;
        }
        const matches: calendarManager.Event[] = events.filter((event: calendarManager.Event) => event.id === id);
        if (matches.length === 1) {
          this.event = matches[0];
          this.status = '';
          return;
        }
        if (matches.length > 1) {
          throw new Error('日历服务返回重复日程');
        }
      }
      this.status = '日程已删除或当前帐号不可见';
    } catch (error) {
      if (this.current(generation)) {
        this.event = undefined;
        this.status = '无法读取日程，请检查日历权限后重试';
      }
    }
  }

  private current(generation: number): boolean {
    return this.active && this.generation === generation;
  }
}
