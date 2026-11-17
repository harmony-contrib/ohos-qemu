/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';
import calendarManager from '@ohos.calendarManager';
import { CalendarReminderReader } from '../reminder/CalendarReminderReader';
import { CalendarChoice, CalendarBusinessController, CalendarView } from '../calendar/CalendarBusinessController';

@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('calendarRoute') route: string = '';
  @LocalStorageLink('calendarRevision') @Watch('routeChanged') revision: number = 0;
  @LocalStorageLink('calendarForeground') foreground: boolean = false;
  @State private browsing: boolean = false;
  @State private view: CalendarView = new CalendarView();
  @State private form: boolean = false;
  @State private deleteConfirm: boolean = false;
  @State private editingId: number = 0;
  @State private title: string = '';
  @State private start: string = '';
  @State private end: string = '';
  @State private description: string = '';
  @State private reminder: string = '';
  @State private reminderTitle: string = '';
  @State private reminderStart: string = '';
  @State private reminderEnd: string = '';
  @State private reminderDescription: string = '';
  @State private reminderStatus: string = '';
  private reader: CalendarReminderReader | undefined = undefined;
  private controller: CalendarBusinessController | undefined = undefined;
  private generation: number = 0;
  private appearing: boolean = false;

  aboutToAppear(): void {
    this.appearing = true;
    this.routeChanged();
  }

  aboutToDisappear(): void {
    this.appearing = false;
    this.generation++;
    this.reader?.dispose();
    this.reader = undefined;
    this.controller?.dispose();
    this.controller = undefined;
    this.form = false;
    this.deleteConfirm = false;
  }

  private async routeChanged(): Promise<void> {
    const generation = ++this.generation;
    this.reader?.dispose();
    this.reader = undefined;
    this.controller?.background();
    this.form = false;
    this.deleteConfirm = false;
    this.reminderTitle = '';
    this.reminderStart = '';
    this.reminderEnd = '';
    this.reminderDescription = '';
    this.reminderStatus = '';
    if (!this.appearing || !this.foreground) {
      return;
    }
    // An exported Want can open a read-only reminder. Only the user's browse
    // control reaches mutation controls; no Want field supplies write data.
    this.browsing = this.route === '';
    if (this.browsing) {
      this.startBusiness();
      return;
    }
    this.reminderStatus = '正在读取日程';
    try {
      const reader = new CalendarReminderReader(getContext(this) as common.UIAbilityContext);
      this.reader = reader;
      await reader.open(this.route);
      if (generation !== this.generation || this.reader !== reader || !this.foreground || !this.appearing) {
        return;
      }
      this.reminderStatus = reader.status;
      if (reader.event !== undefined) {
        this.reminderTitle = reader.event.title ?? '无标题日程';
        this.reminderStart = new Date(reader.event.startTime).toLocaleString();
        this.reminderEnd = new Date(reader.event.endTime).toLocaleString();
        this.reminderDescription = reader.event.description ?? '';
      }
    } catch (error) {
      if (generation === this.generation && this.foreground && this.appearing) {
        this.reminderStatus = '日历初始化失败：' + (error as BusinessError).message;
      }
    }
  }

  private startBusiness(): void {
    if (!this.appearing || !this.foreground) {
      return;
    }
    try {
      if (this.controller === undefined) {
        const controller = new CalendarBusinessController(getContext(this) as common.UIAbilityContext,
          (view: CalendarView) => {
            if (this.controller === controller) {
              this.view = view;
              this.viewChanged();
            }
          });
        this.controller = controller;
      }
      this.controller.foreground();
    } catch (error) {
      this.view = new CalendarView();
      this.view.error = '日历初始化失败：' + (error as BusinessError).message;
    }
  }

  private openBrowser(): void {
    this.generation++;
    this.reader?.dispose();
    this.reader = undefined;
    this.browsing = true;
    this.form = false;
    this.deleteConfirm = false;
    this.startBusiness();
  }

  private openReminder(): void {
    this.routeChanged();
  }

  private viewChanged(): void {
    if (!this.view.ready) {
      this.form = false;
      this.deleteConfirm = false;
    }
  }

  private editable(event: calendarManager.Event): boolean {
    return event.type === calendarManager.EventType.NORMAL && event.recurrenceRule === undefined &&
      !event.isAllDay && !event.isLunar && (event.reminderTime?.length ?? 0) <= 1;
  }

  private openForm(edit: boolean): void {
    const event = edit ? this.view.selected : undefined;
    if (!this.view.ready || this.view.writing || (edit && (event === undefined || !this.editable(event)))) {
      return;
    }
    const start = new Date(this.view.day);
    start.setHours(9, 0, 0, 0);
    this.editingId = event?.id ?? 0;
    this.title = event?.title ?? '';
    this.start = new Date(event?.startTime ?? start.getTime()).toISOString();
    this.end = new Date(event?.endTime ?? start.getTime() + 3600000).toISOString();
    this.description = event?.description ?? '';
    this.reminder = event?.reminderTime?.[0]?.toString() ?? '';
    this.deleteConfirm = false;
    this.form = true;
  }

  private cancel(): void {
    if (!this.view.writing) {
      this.form = false;
      this.deleteConfirm = false;
      this.controller?.cancel();
    }
  }

  onBackPress(): boolean {
    if (this.view.writing) {
      // Leaving a UI cannot roll back an already submitted provider operation.
      return false;
    }
    if (this.form || this.deleteConfirm || this.view.selected !== undefined) {
      this.cancel();
      return true;
    }
    if (this.browsing && this.route.length > 0) {
      this.openReminder();
      return true;
    }
    return false;
  }

  @Builder
  private reminderPage() {
    Scroll() {
      Column({ space: 16 }) {
        Text('日程详情').fontSize(28).id('calendar-main-heading')
        Text(this.reminderStatus).fontSize(18).id('calendar-main-status')
        Text(this.reminderTitle).fontSize(24).id('calendar-main-title')
        Text(this.reminderStart).fontSize(18).id('calendar-main-start')
        Text(this.reminderEnd).fontSize(18).id('calendar-main-end')
        Text(this.reminderDescription).fontSize(18).id('calendar-main-description')
        Button('重新读取').id('calendar-main-refresh').onClick(() => this.routeChanged())
        Button('浏览日历').id('calendar-business-browse').onClick(() => this.openBrowser())
      }.width('100%').padding(24)
    }.height('100%').width('100%')
  }

  @Builder
  private businessPage() {
    Scroll() {
      Column({ space: 12 }) {
        Text('日历').fontSize(26).fontWeight(FontWeight.Bold).id('calendar-business-heading');
        if (this.route.length > 0) {
          Button('返回提醒详情').id('calendar-business-reminder').enabled(!this.view.writing)
            .onClick(() => this.openReminder());
        }
        Text('使用当前系统账号与已授予权限可访问的日历。').fontSize(14);
        if (this.view.writing) {
          Text('正在提交日程操作；离开页面后已提交的操作仍可能完成。').id('calendar-business-writing');
        }
        if (this.controller === undefined) {
          Text('日历服务未初始化').fontColor(Color.Red).id('calendar-main-unavailable');
        }
        if (this.view.loading) {
          Text('正在读取日历…').id('calendar-main-loading');
        }
        if (this.view.error.length > 0) {
          Text(this.view.error).fontColor(Color.Red).id('calendar-main-error');
        }
        if (this.view.notice.length > 0) {
          Text(this.view.notice).id('calendar-main-notice');
        }
        Button('刷新').id('calendar-main-refresh').enabled(!this.view.writing)
          .onClick(() => this.controller?.refresh());
        ForEach(this.view.calendars, (choice: CalendarChoice) => {
          Button(`${choice.id === this.view.calendarId ? '✓ ' : ''}${choice.label}`)
            .id(`calendar-main-calendar-${choice.id}`).enabled(!this.view.writing)
            .onClick(() => this.controller?.chooseCalendar(choice.id));
        }, (choice: CalendarChoice) => choice.id.toString());
        Row({ space: 12 }) {
          Button('前一天').id('calendar-main-prev').enabled(!this.view.writing)
            .onClick(() => this.controller?.moveDay(-1));
          Button('今天').id('calendar-main-today').enabled(!this.view.writing)
            .onClick(() => this.controller?.moveDay(0));
          Button('后一天').id('calendar-main-next').enabled(!this.view.writing)
            .onClick(() => this.controller?.moveDay(1));
        }
        Text(new Date(this.view.day).toLocaleDateString()).id('calendar-main-day');
        Button('新建日程').id('calendar-main-new').enabled(this.view.ready && !this.view.writing)
          .onClick(() => this.openForm(false));
        if (this.form) {
          Text(this.editingId > 0 ? '编辑日程' : '新建日程').fontSize(22);
          TextInput({ text: this.title, placeholder: '标题' }).id('calendar-main-event-title')
            .maxLength(5000).enabled(!this.view.writing).onChange((value: string) => this.title = value);
          Text('开始时间（UTC，ISO 8601）');
          TextInput({ text: this.start }).id('calendar-main-start').enabled(!this.view.writing)
            .onChange((value: string) => this.start = value);
          Text('结束时间（UTC，ISO 8601）');
          TextInput({ text: this.end }).id('calendar-main-end').enabled(!this.view.writing)
            .onChange((value: string) => this.end = value);
          TextArea({ text: this.description, placeholder: '备注' }).id('calendar-main-description')
            .maxLength(5000).enabled(!this.view.writing).onChange((value: string) => this.description = value);
          TextInput({ text: this.reminder, placeholder: '提前提醒分钟数；留空则不提醒' })
            .id('calendar-main-reminder').enabled(!this.view.writing)
            .onChange((value: string) => this.reminder = value);
          Text('提醒会交给现有系统提醒服务；保存日程不代表通知已经发出。').fontSize(14);
          Row({ space: 12 }) {
            Button('保存').id('calendar-main-save').enabled(!this.view.writing)
              .onClick(() => this.controller?.save(this.title, this.start, this.end,
                this.description, this.reminder, this.editingId));
            Button('取消').id('calendar-main-cancel').enabled(!this.view.writing).onClick(() => this.cancel());
          }
        } else if (this.view.selected !== undefined) {
          Text(this.view.selected.title ?? '').fontSize(22).id('calendar-main-detail-title');
          Text(`编号：${this.view.selected.id}`).id('calendar-main-detail-id');
          Text(new Date(this.view.selected.instanceStartTime ?? this.view.selected.startTime).toLocaleString())
            .id('calendar-main-detail-start');
          Text(new Date(this.view.selected.instanceEndTime ?? this.view.selected.endTime).toLocaleString())
            .id('calendar-main-detail-end');
          Text(this.view.selected.description ?? '').id('calendar-main-detail-description');
          Text(`事件时区：${this.view.selected.timeZone ?? '系统时区'}`);
          Text(`地点：${this.view.selected.location?.location ?? ''}`);
          Text(`提醒（提前分钟）：${this.view.selected.reminderTime?.join(', ') ?? '无'}`);
          if (this.editable(this.view.selected)) {
            Row({ space: 12 }) {
              Button('编辑').id('calendar-main-edit').enabled(!this.view.writing).onClick(() => this.openForm(true));
              Button('删除').id('calendar-main-delete').enabled(!this.view.writing)
                .onClick(() => this.deleteConfirm = true);
            }
            if (this.deleteConfirm) {
              Text('确定删除此日程？').id('calendar-main-delete-question');
              Button('确认删除').id('calendar-main-confirm-delete').enabled(!this.view.writing)
                .onClick(() => this.controller?.remove(this.view.selected?.id ?? 0, true));
              Button('取消删除').id('calendar-main-cancel-delete').enabled(!this.view.writing)
                .onClick(() => this.deleteConfirm = false);
            }
          } else {
            Text('全天、农历、重复、重要及多次提醒日程在此仅查看。');
          }
          Button('返回').id('calendar-main-detail-back').enabled(!this.view.writing).onClick(() => this.cancel());
        } else {
          if (this.view.ready && this.view.events.length === 0) {
            Text('当天没有日程').id('calendar-main-empty');
          }
          ForEach(this.view.events, (event: calendarManager.Event) => {
            Button(`${event.title ?? ''}  ${new Date(event.instanceStartTime ?? event.startTime).toLocaleTimeString()}`)
              .id(`calendar-main-event-${event.id}`).enabled(!this.view.writing)
              .onClick(() => this.controller?.select(event.id ?? 0, event.instanceStartTime ?? event.startTime));
          }, (event: calendarManager.Event) => `${event.id}:${event.instanceStartTime ?? event.startTime}`);
        }
      }.padding(20).width('100%').alignItems(HorizontalAlign.Start);
    }.width('100%').height('100%').backgroundColor(Color.White);
  }

  build() {
    if (this.browsing) {
      this.businessPage()
    } else {
      this.reminderPage()
    }
  }
}
