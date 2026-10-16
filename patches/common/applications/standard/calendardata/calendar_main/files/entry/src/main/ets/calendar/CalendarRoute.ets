/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
// A reminder URI selects an existing visible instance. It never authorizes a write.
export class CalendarRoute {
  eventId: number = 0;
  start: number = 0;
  end: number = 0;
}

export function parseCalendarRoute(uri: string): CalendarRoute {
  const route = new CalendarRoute();
  if (uri.length === 0) {
    return route;
  }
  if (uri.length > 512) {
    throw new Error('日历链接过长');
  }
  const match = /^calendar:\/\/(?:com\.ohos\.calendar|com\.ohos\.calendardata)\?event_id=([1-9][0-9]*)&start=([0-9]+)&end=([0-9]+)$/.exec(uri);
  if (match === null) {
    throw new Error('无效的日历链接');
  }
  route.eventId = Number(match[1]);
  route.start = Number(match[2]);
  route.end = Number(match[3]);
  if (!Number.isSafeInteger(route.eventId) || route.eventId > 2147483647 ||
    !Number.isSafeInteger(route.start) || !Number.isSafeInteger(route.end) ||
    route.start < 0 || route.end > 8640000000000000 || route.end <= route.start ||
    route.end - route.start > 366 * 86400000) {
    throw new Error('日历链接的日程或时间无效');
  }
  return route;
}
