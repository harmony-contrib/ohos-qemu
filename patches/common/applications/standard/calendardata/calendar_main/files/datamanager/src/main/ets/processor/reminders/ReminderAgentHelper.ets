/**
 * @file Describe the file
 * Copyright (c) 2024 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import I18n from '@ohos.i18n';
import { reminderAgentManager } from '@kit.BackgroundTasksKit';
import { CustomTime, getChineseDay, getChineseMonth, Log } from '@ohos/common';
import { Reminders } from '@ohos/datastructure/src/main/ets/reminders/Reminders';
import { GlobalThis } from '@ohos/common/src/main/ets/utils/GlobalThis';
import { formatTimeChineseStyle, MILLS_PER_MINUTE } from '@ohos/common/src/main/ets/utils/TimeUtils';
import { Duration } from '@ohos/rrule/src/main/ets/Duration';
import { adaptReminderRequest } from '@ohos/rrule';
import { DateManager } from '@ohos/common/src/main/ets/date/DateManager';
import { DayData } from '@ohos/common/src/main/ets/date/Date';
import { Events } from '@ohos/datastructure/src/main/ets/events/Events';
import notificationManager from '@ohos.notificationManager';
import { systemDateTime } from '@kit.BasicServicesKit';
import { CalendarAlerts } from '@ohos/datastructure/src/main/ets/calendaralerts/CalendarAlerts';

const TAG: string = `ReminderAgentHelper`;

const SNOOZE_DELAY = 5 * 60;

const CALENDAR_BUNDLE_NAME = 'com.ohos.calendardata';

const CALENDAR_ABILITY_NAME = 'MainAbility';

const TOMORROW: number = 1;

const DAY_AFTER_TOMORROW: number = 2;

const MILLS_PER_DAY: number = 86400000;

const IMPORTANT_ALERT: number = 1; // 重要提醒

/**
 * 计算两个时间戳相隔天数，向上取整
 *
 * @param date1
 * @param date2
 * @returns 相隔天数
 */
export function diffDays(date1: number, date2: number): number {
  const msPerDay = 1000 * 60 * 60 * 24;
  const diffMs = Math.abs(date1 - date2);
  return Math.ceil(diffMs / msPerDay);
}

/**
 * 计算通知显示相关信息，如通知标题、时间等，封装到NotificationInfo结构中
 *
 * @param event 日程信息
 * @returns 通知信息
 */
export function getNotificationInfo(
        event: Events, reminder: Reminders, customTime: CustomTime, calendarAlerts: CalendarAlerts): NotificationInfo {
  const originalDtStart = event.dtStart;
  const instanceStart = calendarAlerts.begin;
  const instanceEnd = calendarAlerts.end;
  calendarAlerts.slotType = event.hwExtAlertType;

  let notificationInfo: NotificationInfo = {};
  notificationInfo.title = event.title;
  if (!notificationInfo.title) {
    notificationInfo.title = GlobalThis.getSingleInstance().getResourceStr($r('app.string.no_title_label'));
  }
  notificationInfo.eventId = event.id;
  notificationInfo.start = instanceStart;
  const duration: Duration = Duration.parse(event.duration);
  if (duration.isValid()) {
    notificationInfo.end = instanceStart + duration.getMills();
  } else if (instanceEnd && instanceEnd > instanceStart) {
    notificationInfo.end = instanceEnd;
  } else {
    notificationInfo.end = instanceStart + Duration.defaultAlertDuration();
  }
  notificationInfo.agendaDetailUri = `calendar://com.ohos.calendardata?event_id=${notificationInfo.eventId}` +
    `&start=${instanceStart}&end=${instanceEnd}`;
  let beginTime: string = formatTimeChineseStyle(new Date(notificationInfo.start), customTime.getTimeZone());
  let endTime: string = formatTimeChineseStyle(new Date(notificationInfo.end), customTime.getTimeZone());
  Log.warn(TAG, `notificationInfo:${event.id}-(${beginTime}-${endTime})-(${instanceStart},${instanceEnd})` +
    `-${event.creator}`);
  const agendaStart = new Date(notificationInfo.start);
  const agendaEnd = new Date(notificationInfo.end);
  notificationInfo.content = getNotificationContent(reminder, event,
    agendaStart, agendaEnd, beginTime, endTime, customTime);
  return notificationInfo;
}

export function getNotificationContent(reminder: Reminders, event: Events, agendaStart: Date,
                                       agendaEnd: Date, beginTime: string, endTime: string, customTime: CustomTime) {
  let beginDate: string = '';
  let endDate: string = '';
  let content: string = '';
  if (agendaStart.getDate() !== agendaEnd.getDate()) { // 跨天日程
    if (event.isAllDay()) { // 全天日程
      // 全天日程end为UTC时间的24点，会被计算为下一天0点，故处理时减去1天再进行计算
      beginDate = formatEventTimeStr(event, agendaStart);
      endDate = formatEventTimeStr(event, new Date(agendaEnd.getTime() - MILLS_PER_DAY));
      const allDay = GlobalThis.getSingleInstance().getResourceStr($r('app.string.event_all_day'));
      content = getAllDayData(beginDate, endDate, allDay, agendaStart, reminder.minutes, event);
    } else { // 非全天日程
      beginDate = formatEventTimeStr(event, agendaStart);
      endDate = formatEventTimeStr(event, agendaEnd);
      content = beginDate + ' ' + beginTime + '-' + endDate + ' ' + endTime;
    }
  } else { // 不跨天日程
    beginDate = getBeginDateContent(agendaStart, reminder.minutes, event); //不跨天只需要获取开始时间的Date
    if (event.isAllDay()) {
      const allDay = GlobalThis.getSingleInstance().getResourceStr($r('app.string.event_all_day'));
      content = beginDate + ' ' + allDay;
    } else {
      content = beginDate + ' ' + beginTime + '-' + endTime;
    }
  }
  if (systemDateTime.getTimezoneSync() != customTime.getTimeZone()) {
    content += ` (${customTime.getGMTStr()})`;
  }
  return content;
}

function getAllDayData(beginDate: string, endDate: string, allDay: string,
                       agendaStart: Date, reminderMinutes: number, event: Events): string {
  if (beginDate === endDate) {
    // 单天全天日程时间展示日期
    beginDate = getBeginDateContent(agendaStart, reminderMinutes, event);
    return beginDate + ' ' + allDay;
  } else {
    // 跨天全天日程时间展示时间段
    return beginDate + '-' + endDate + ' ' + allDay;
  }
}

export function getBeginDateContent(agendaStart: Date, reminderMinutes: number, event: Events) {
  let beginDate: string = '';
  let systemLanguage = I18n.System.getSystemLanguage();
  const alertTime = agendaStart.getTime() - reminderMinutes * 1000 * 60;
  const tempStartDay = new Date(agendaStart);
  // 显示“今天”分界点
  const startDay = tempStartDay.setHours(0, 0, 0);
  // 用于区分提醒时间在开始时间后的情况（三方可写入负的提醒时间）
  const startTomorrow = startDay + MILLS_PER_DAY;
  // 显示“明天”分界点
  const startYesterday = startDay - MILLS_PER_DAY;
  // 显示“后天”分界点
  const startDayBeforeYesterday = startYesterday - MILLS_PER_DAY;
  if (alertTime >= startDay && alertTime < startTomorrow) { // 显示“今天”
    if (event.isAllDay()) {
      beginDate = GlobalThis.getSingleInstance().getResourceStr($r('app.string.today'));
    } else {
      beginDate = '';
    }
  } else if (alertTime < startDay && alertTime >= startYesterday) { // 显示“明天”
    let timeFormat = new Intl.RelativeTimeFormat(systemLanguage, { numeric: 'auto' });
    beginDate = timeFormat.format(TOMORROW, 'day');
  } else if (alertTime < startYesterday && alertTime >= startDayBeforeYesterday) { // 显示“后天”
    let timeFormat = new Intl.RelativeTimeFormat(systemLanguage, { numeric: 'auto' });
    beginDate = timeFormat.format(DAY_AFTER_TOMORROW, 'day');
  } else { // 显示“具体日期”
    beginDate = formatEventTimeStr(event, agendaStart);
  }
  return beginDate;
}

/**
 * 构造提醒代理通知数据
 *
 * @param event 日程信息
 * @param reminder 提醒信息
 */
export async function getReminderRequestCalendar(event: Events, calendarAlerts: CalendarAlerts, customTime: CustomTime):
  Promise<reminderAgentManager.ReminderRequestCalendar | undefined> {

  if (!event) {
    Log.warn(TAG, 'getReminderRequest event is undefined');
    return undefined;
  }

  let reminder: Reminders = new Reminders();
  reminder.minutes = calendarAlerts.minutes;

  // 获取通知内容
  const notificationInfo: NotificationInfo =
    getNotificationInfo(event, reminder, customTime, calendarAlerts);
  if (!notificationInfo.start || notificationInfo.start <= 0) {
    Log.warn(TAG, `publishReminder get invalid star time ${notificationInfo.start}`);
    return undefined;
  }
  // 发送通知
  const dateTime: reminderAgentManager.LocalDateTime = getDateTime(notificationInfo.start, reminder.minutes);
  const reminderRequest = getReminderRequest(dateTime, notificationInfo, event.hwExtAlertType);
  if (notificationInfo.end && notificationInfo.end > notificationInfo.start) {
    const endDateTime: reminderAgentManager.LocalDateTime = getDateTime(notificationInfo.end, 0);
    reminderRequest['endDateTime'] = endDateTime;
  }

  // 设置重要提醒/普通提醒
  if (event.hwExtAlertType === IMPORTANT_ALERT) {
    reminderRequest.slotType = notificationManager.SlotType.SOCIAL_COMMUNICATION;
  } else {
    reminderRequest.slotType = notificationManager.SlotType.SERVICE_INFORMATION;
  }
  adaptReminderRequest(reminderRequest, event);
  return reminderRequest;
}

export function formatEventTimeStr(event: Events, agendaDate: Date): string {
  let date: string = '';
  let systemLanguage = I18n.System.getSystemLanguage() ?? 'zh-CN';
  let dateFormat = new Intl.DateTimeFormat(systemLanguage, { month: 'long', day: 'numeric' });
  // 根据日程类型显示不同形式日期
  if (event.isLunarEvent()) {
    const lunarDate: DayData = DateManager.getInstance().getDayData(agendaDate.getFullYear(),
      agendaDate.getMonth() + 1, agendaDate.getDate()) as DayData;
    date = getChineseMonth(lunarDate.lunaMonth) + getChineseDay(lunarDate.lunarDay);
  } else {
    date = dateFormat.format(agendaDate);
  }
  return date;
}

/**
 * 获取提醒的目标时间
 *
 * @param time 提醒时间
 * @param offsetMinutes 提醒偏移分钟数
 */
function getDateTime(time: number, offsetMinutes: number): reminderAgentManager.LocalDateTime {
  const reminderTime = time - offsetMinutes * MILLS_PER_MINUTE;
  const date = new Date(reminderTime);
  const dateTime: reminderAgentManager.LocalDateTime = {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
    hour: date.getHours(),
    minute: date.getMinutes(),
    second: date.getSeconds()
  }
  return dateTime;
}

/**
 * 获取 reminderRequest，需要传递给提醒代理的数据结构
 *
 * @param dateTime 提醒目标时间
 * @param notificationInfo 通知信息
 */
function getReminderRequest(dateTime: reminderAgentManager.LocalDateTime,
                            notificationInfo: NotificationInfo, alertType: number):
  reminderAgentManager.ReminderRequestCalendar {
  let reminderRequest: reminderAgentManager.ReminderRequestCalendar | undefined = undefined;
  // 重要提醒需要添加extraInfo字段，日程通知栏重要提醒5s后不会自动消失
  if (alertType === IMPORTANT_ALERT) {
    reminderRequest = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,
      dateTime: dateTime,
      ringDuration: 0,
      wantAgent: {
        pkgName: CALENDAR_BUNDLE_NAME,
        abilityName: CALENDAR_ABILITY_NAME,
        uri: notificationInfo.agendaDetailUri,
        parameters: '{"NotificationRequest_extraInfo":{"101":{"hw_keep_headsup_sticky":{"1":"true"}}}}' as ESObject,
      },
      notificationId: notificationInfo.eventId,
      title: notificationInfo.title,
      content: notificationInfo.content,
      snoozeTimes: 0,
      timeInterval: SNOOZE_DELAY,
      autoDeletedTime: notificationInfo.end,
      snoozeSlotType: notificationManager.SlotType.CONTENT_INFORMATION
    }
  } else {
    reminderRequest = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,
      dateTime: dateTime,
      ringDuration: 0,
      wantAgent: {
        pkgName: CALENDAR_BUNDLE_NAME,
        abilityName: CALENDAR_ABILITY_NAME,
        uri: notificationInfo.agendaDetailUri
      },
      notificationId: notificationInfo.eventId,
      title: notificationInfo.title,
      content: notificationInfo.content,
      snoozeTimes: 0,
      timeInterval: SNOOZE_DELAY,
      autoDeletedTime: notificationInfo.end,
      snoozeSlotType: notificationManager.SlotType.CONTENT_INFORMATION
    };
  }
  setActionButton(reminderRequest, notificationInfo);
  return reminderRequest;
}

/**
 * 设置提醒代理通知 actionButton，含：稍后提醒、不再提醒、一键入会
 *
 * @param reminderRequest 提醒代理request
 * @param notificationInfo 通知信息
 */
function setActionButton(reminderRequest: reminderAgentManager.ReminderRequestCalendar,
                         notificationInfo: NotificationInfo): void {
  reminderRequest.actionButton = [
    {
      titleResource: 'snooze',
      title: GlobalThis.getSingleInstance().getResourceStr($r('app.string.snooze')),
      type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_SNOOZE
    },
    {
      titleResource: 'close',
      title: GlobalThis.getSingleInstance().getResourceStr($r('app.string.close')),
      type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_CLOSE
    }
  ];
}

/**
 * 全天日程使用
 * 计算不同时区9点提醒需要偏移的提醒时间
 * 日程写入时间为UTC时间+时区偏移
 * 例：东八时区写入重要日24/1/20，写入日程时间为24/1/20日早上8点-24/1/21日早上7点59分59秒
 * 提醒时间为对应时区当天9点，默认写入提醒时间为0
 * 例：上述日程提醒时间为默认提醒时间 + ((东八时区-9小时) / 1分钟)，即-60分钟
 * @returns (用户时区-9小时) / 1分钟
 */
export function getAllDayReminderMinutes(): number {
  const nineHours = 1000 * 60 * 60 * 9;
  const oneMinute = 1000 * 60;
  return (new CustomTime().getTimeZoneOffset() - nineHours) / oneMinute;
}

/**
 * 通知信息
 *
 * @since 2023-5-31
 */
export interface NotificationInfo {
  // 通知标题
  title?: string;

  // 通知内容
  content?: string;

  // 日程id
  eventId?: number;

  // 日程开始时间
  start?: number;

  // 日程结束时间
  end?: number;

  // 日程 一键服务的uri
  uri?: string
  // 通知uri是否合法
  serviceVerified?: number;

  // 日程 一键服务的类型
  serviceType?: string;

  // 日程 详情的Uri
  agendaDetailUri?: string
}