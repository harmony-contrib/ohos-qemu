/**
 * @file Describe the file
 * Copyright (c) 2023 Huawei Device Co., Ltd.
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

import data_rdb from '@ohos.data.relationalStore';
import dataSharePredicates from '@ohos.data.dataSharePredicates';
import { BusinessError } from '@ohos.base';
import { ValueType } from '@ohos.data.ValuesBucket';

import { Log } from '@ohos/common/src/main/ets/utils/Log';
import { hasNoError } from '@ohos/common/src/main/ets/utils/ErrorUtils';
import { getBundleNameByUri } from '@ohos/common/src/main/ets/utils/UrlUtils';

import { Calendars } from '@ohos/datastructure/src/main/ets/calendars/Calendars';
import { CalendarsIndexes, parseCalendarsIndexes } from '@ohos/datastructure/src/main/ets/calendars/CalendarsIndexes';
import { CalendarsColumns } from '@ohos/datastructure/src/main/ets/calendars/CalendarsColumns';
import { EventColumns, EXPAND_COLUMNS } from '@ohos/datastructure/src/main/ets/events/EventColumns';
import { Events } from '@ohos/datastructure/src/main/ets/events/Events';
import { EventIndexes, parseIndexes } from '@ohos/datastructure/src/main/ets/events/EventIndexes';
import { parseCalendars } from '@ohos/datastructure/src/main/ets/calendars/CalendarsParser';

import { ErrorCode } from '../../constants/ErrorCode';
import { DefaultProcessor } from './../DefaultProcessor';
import { initValueCreator, initPredicateCreator, deleteValueCreator, initValueUuid } from '../DatabaseProcessorHelper';
import { acquireExpandOne, isNeedRefreshInstances, acquireUpdateOne } from '../instances/InstancesProcessor';
import { filterValuesBucket } from '@ohos/common/src/main/ets/utils/ValuesUtils';
import { isEmptyStr } from '@ohos/common/src/main/ets/utils/TextUtils';
import { parseEventByIndex } from '@ohos/datastructure';
import { GlobalPackageName } from '@ohos/common';

const TAG: string = 'EventsProcessor';
const CHANNEL_ID: string = 'channel_id';

/**
 * the Events table processor
 *
 * @since 2022-06-24
 */
export class EventsProcessor extends DefaultProcessor {
  async insertByHighAuthority(rdbStore: data_rdb.RdbStore, uri: string,
                              value: data_rdb.ValuesBucket, callback: Function) {
    let values = filterValuesBucket(value, CHANNEL_ID);
    if (!this.isFromMigrate) {
      const callerName = getBundleNameByUri(uri);
      initValueCreator(values, callerName);
      this.initEventUuid(values, callerName);
    }
    const isCalendarExist = await isCalendarContainSameId(rdbStore, values);
    if (isCalendarExist) {
      await this.initCalendarUuid(values, rdbStore);
      this.insertEventWithInstanceExpand(rdbStore, uri, values, callback);
    } else {
      Log.warn(TAG, 'not support insert operation');
      const err: BusinessError = {
        code: ErrorCode.UN_SUPPORT_OPERATION,
        name: 'UnSupportedOperationException',
        message: 'The calling application cannot insert an event without its own calendar'
      };
      callback(err, -1);
    }
  }

  async insertByLowAuthority(rdbStore: data_rdb.RdbStore, uri: string,
                             value: data_rdb.ValuesBucket, callback: Function) {
    let values = filterValuesBucket(value, CHANNEL_ID);
    if (!this.isFromMigrate) {
      const callerName = getBundleNameByUri(uri);
      initValueCreator(values, callerName);
      this.initEventUuid(values, callerName);
    }
    const isCalendarCreatorExist = await isCalendarContainSameCreator(rdbStore, values);
    if (isCalendarCreatorExist) {
      await this.initCalendarUuid(values, rdbStore);
      this.insertEventWithInstanceExpand(rdbStore, uri, values, callback);
    } else {
      Log.warn(TAG, 'not support insert operation');
      const err: BusinessError = {
        code: ErrorCode.UN_SUPPORT_OPERATION,
        name: 'UnSupportedOperationException',
        message: 'The calling application cannot insert an event with different creator from calendar'
      };
      callback(err, -1);
    }
  }

  private initEventUuid(values: data_rdb.ValuesBucket, callerName: string) {
    const identifier = values[EventColumns.IDENTIFIER] as string;
    if (values[EventColumns.IDENTIFIER] && !isEmptyStr(identifier)) {
      if (!values[EventColumns.UUID]) {
        values[EventColumns.UUID] = identifier + callerName;
      }
    } else {
      initValueUuid(values);
    }
  }

  private async initCalendarUuid(values: data_rdb.ValuesBucket, rdbStore: data_rdb.RdbStore) {
    const calendarId = values[EventColumns.CALENDAR_ID] as number;
    if (!values[EventColumns.CALENDAR_UUID]) {
      const calendar: Calendars | undefined = await queryCalendarById(rdbStore, calendarId);
      if (calendar) {
        values[EventColumns.CALENDAR_UUID] = calendar.uuid;
      }
    }
  }

  async deleteByLowAuthority(rdbStore: data_rdb.RdbStore, uri: string,
                             predicates: dataSharePredicates.DataSharePredicates, callback: Function) {
    const callerName = getBundleNameByUri(uri);
    initPredicateCreator(predicates, callerName);
    this.doDelete(rdbStore, uri, predicates, callback);
  }

  async updateByHighAuthority(rdbStore: data_rdb.RdbStore, uri: string, value: data_rdb.ValuesBucket,
                              predicates: dataSharePredicates.DataSharePredicates, callback: Function) {
    let values = filterValuesBucket(value, CHANNEL_ID);
    deleteValueCreator(values);
    this.updateEventWithInstance(rdbStore, uri, values, predicates, callback);
  }

  async updateByLowAuthority(rdbStore: data_rdb.RdbStore, uri: string, value: data_rdb.ValuesBucket,
                             predicates: dataSharePredicates.DataSharePredicates, callback: Function) {
    let values = filterValuesBucket(value, CHANNEL_ID);
    const callerName = getBundleNameByUri(uri);
    deleteValueCreator(values);
    initPredicateCreator(predicates, callerName);
    this.updateEventWithInstance(rdbStore, uri, values, predicates, callback);
  }

  async queryByLowAuthority(rdbStore: data_rdb.RdbStore, uri: string, columns: Array<string>,
                            predicates: dataSharePredicates.DataSharePredicates, callback: Function) {
    const callerName = getBundleNameByUri(uri);
    initPredicateCreator(predicates, callerName);
    this.doQuery(rdbStore, uri, columns, predicates, callback);
  }

  /**
   * 插入 Event 并扩展该 Event 的实例 Instance
   *
   * @param rdbStore rdb数据库
   * @param uri DataShare的uri
   * @param values 插入的数据
   * @param callback 回调方法
   */
  async insertEventWithInstanceExpand(rdbStore: data_rdb.RdbStore, uri: string,
                                      values: data_rdb.ValuesBucket, callback: Function) {
    this.doInsert(rdbStore, uri, values, (err: BusinessError, rowId: number) => {
      Log.debug(TAG, `before insert callback`);
      if (hasNoError(err)) {
        acquireExpandOne(rdbStore, rowId, values);
      }
      callback(err, rowId);
      Log.debug(TAG, `after insert callback`);
    });
  }

  /**
   * 更新 Event，并同步更新 Instance
   *
   * @param rdbStore rdb数据库
   * @param uri DataShare的uri
   * @param values 更新的数据
   * @param predicates 更新条件
   * @param callback 回调方法
   */
  async updateEventWithInstance(rdbStore: data_rdb.RdbStore, uri: string, values: data_rdb.ValuesBucket,
                                predicates: dataSharePredicates.DataSharePredicates, callback: Function) {
    let needUpdatedEventIds: Array<number>;
    if (isNeedRefreshInstances(values)) {
      needUpdatedEventIds = await queryEventIdsByPredicate(rdbStore, predicates);
    }
    this.doUpdate(rdbStore, uri, values, predicates, (err: BusinessError, count: Function) => {
      Log.debug(TAG, `before update callback`);
      if (hasNoError(err)) {
        updateInstances(rdbStore, needUpdatedEventIds);
      }
      callback(err, count);
      Log.debug(TAG, `after update callback`);
    })
  }
}

/**
 * 检查待插入的 event 与 calendar 表中相同 calendar_id 的元组是否拥有相同的 creator
 *
 * @param rdbStore rdb数据库
 * @param values 插入操作的数据
 * @return true 相同 false 不相同
 */
async function isCalendarContainSameCreator(rdbStore: data_rdb.RdbStore,
                                            values: data_rdb.ValuesBucket): Promise<boolean> {
  Log.debug(TAG, 'isCalendarContainSameCreator start');
  const eventCreator = values[EventColumns.CREATOR];
  let resultSet = await queryCalendarIdAndCreatorByEvent(rdbStore, values);
  if (resultSet === null || resultSet === undefined) {
    return false;
  }
  const calendarsIndexes: CalendarsIndexes | undefined = parseCalendarsIndexes(resultSet);
  if (resultSet.goToFirstRow()) {
    let calendars: Calendars | undefined = parseCalendars(resultSet, calendarsIndexes);
    if (calendars === null || calendars === undefined) {
      return false;
    }
    if (calendars.creator === eventCreator || calendars.creator === GlobalPackageName.CALENDAR_DATA) {
      return true;
    }
  }
  return false;
}

/**
 * 检查待插入的 event 与 calendar 表中是否存在相同 calendar_id 的元组
 *
 * @param rdbStore rdb数据库
 * @param values 插入操作的数据
 * @return true 相同 false 不相同
 */
async function isCalendarContainSameId(rdbStore: data_rdb.RdbStore,
                                       values: data_rdb.ValuesBucket): Promise<boolean> {
  Log.debug(TAG, 'isCalendarContainSameId start');
  let resultSet = await queryCalendarIdAndCreatorByEvent(rdbStore, values);
  if (resultSet === null || resultSet === undefined) {
    return false;
  }
  if (resultSet.rowCount > 0) {
    return true;
  }
  return false;
}

/**
 * 查询待插入的 event 数据中 calendar_id 与 calendar 表相同的结果
 *
 * @param rdbStore rdb数据库
 * @param values 插入操作的数据
 * @return DataShareResultSet
 */
async function queryCalendarIdAndCreatorByEvent(rdbStore: data_rdb.RdbStore,
                                                values: data_rdb.ValuesBucket): Promise<data_rdb.ResultSet> {
  const calendarId = values[EventColumns.CALENDAR_ID] as ValueType;
  const columns = [CalendarsColumns.ID, CalendarsColumns.CREATOR];
  let predicates = new dataSharePredicates.DataSharePredicates();
  predicates.equalTo(CalendarsColumns.ID, calendarId);
  let resultSet: data_rdb.ResultSet = {} as data_rdb.ResultSet;
  try {
    resultSet = await rdbStore.query(CalendarsColumns.TABLE_NAME, predicates, columns);
  } catch (err) {
    Log.error(TAG, 'Calendars query data error');
  }
  return resultSet;
}

/**
 * 根据Predicate查出待刷新的Events ID列表，用于后续刷新Instances的依据
 *
 * @param rdbStore rdb数据库
 * @param predicates update条件，用于定位需要刷新Instances对应eventId的范围
 */
async function queryEventIdsByPredicate(rdbStore: data_rdb.RdbStore,
                                        predicates: dataSharePredicates.DataSharePredicates): Promise<number[]> {
  const resultArray: number[] = [];
  const columns = [EventColumns.ID];
  try {
    const resultSet = await rdbStore.query(EventColumns.TABLE_NAME, predicates, columns);
    if (resultSet === null || resultSet === undefined) {
      Log.error(TAG, 'queryEventIdsByPredicate get invalid resultSet');
      return resultArray;
    }
    if (resultSet.rowCount === 0 || !resultSet.goToFirstRow()) {
      Log.info(TAG, `queryEventIdsByPredicate row count:${resultSet?.rowCount}`);
      return resultArray;
    }
    do {
      const eventId = resultSet.getLong(resultSet.getColumnIndex(EventColumns.ID));
      resultArray.push(eventId);
    } while (resultSet.goToNextRow());
  } catch (err) {
    Log.error(TAG, `queryEventIdsByPredicate get err: ${err?.message}`);
  }
  return resultArray;
}

/**
 * 批量刷新Instances
 *
 * @param rdbStore rdb数据库
 * @param updatedIds 待刷新的eventId列表
 */
async function updateInstances(rdbStore: data_rdb.RdbStore, updatedIds: Array<number>) {
  if (updatedIds === null || updatedIds === undefined || updatedIds.length === 0) {
    return;
  }

  // 1.先批量查询出全部Events数据
  const eventsMap: Map<number, Events> = await queryEventsByIds(rdbStore, updatedIds);

  if (eventsMap === null || eventsMap === undefined || eventsMap.size === 0) {
    Log.warn(TAG, 'updateInstances with invalid eventsMap');
    return;
  }

  // 2.再遍历生成Instances
  for (let eventId of updatedIds) {
    // 基于eventId单条刷新Instances，需传入events字段值数据
    acquireUpdateOne(rdbStore, eventId, eventsMap.get(eventId));
  }
}

/**
 * 根据EventIds查询出Events数据，用于生成Instances，先批量查询避免在for循环中查询
 *
 * @param rdbStore rdb数据库
 * @param eventIds 需查询的eventIds集合
 * @return Map<number, Events> eventId-Events的map
 */
async function queryEventsByIds(rdbStore: data_rdb.RdbStore,
                                eventIds: Array<number>): Promise<Map<number, Events>> {
  const resultMap: Map<number, Events> = new Map();
  const predicate = new dataSharePredicates.DataSharePredicates();
  predicate.in(EventColumns.ID, eventIds);
  try {
    const resultSet = await rdbStore.query(EventColumns.TABLE_NAME, predicate, EXPAND_COLUMNS);
    if (resultSet === null || resultSet === undefined) {
      Log.error(TAG, 'queryEventsByIds get invalid resultSet');
      return resultMap;
    }
    if (!resultSet.goToFirstRow()) {
      Log.error(TAG, `queryEventsByIds goto first row failed ${resultSet?.rowCount}`);
      return resultMap;
    }
    const indexes: EventIndexes | undefined = parseIndexes(resultSet);
    do {
      const event: Events | undefined = parseEventByIndex(resultSet, indexes);
      if (event != undefined) {
        resultMap.set(event.id, event);
      }
    } while (resultSet.goToNextRow());
  } catch (err) {
    Log.error(TAG, `queryEventsByIds get err ${err?.message}`);
  }
  return resultMap;
}

/**
 * 根据eventId查询日程
 *
 * @param rdbStore rdb数据库
 * @param eventId 参数
 * @returns 结果
 */
export async function queryEventsById(rdbStore: data_rdb.RdbStore, eventId: number): Promise<Events | undefined> {
  const predicate = new dataSharePredicates.DataSharePredicates();
  predicate.equalTo(EventColumns.ID, eventId);
  let resultSet: data_rdb.ResultSet | null = null;
  try {
    resultSet = await rdbStore.query(EventColumns.TABLE_NAME, predicate);
    if (!resultSet || !(resultSet?.rowCount > 0)) {
      return undefined;
    }
    resultSet.goToFirstRow();
    const indexes: EventIndexes | undefined = parseIndexes(resultSet);
    return parseEventByIndex(resultSet, indexes);
  } catch (err) {
    Log.error(TAG, `queryEventsById get err ${err?.message}`);
  } finally {
    if (resultSet) {
      resultSet.close();
    }
  }
  return undefined;
}

/**
 * 根据calendarId查询calendar
 *
 * @param rdbStore rdb数据库
 * @param calendarId 参数
 * @returns 结果
 */
async function queryCalendarById(rdbStore: data_rdb.RdbStore, calendarId: number): Promise<Calendars | undefined> {
  const predicate = new dataSharePredicates.DataSharePredicates();
  predicate.equalTo(CalendarsColumns.ID, calendarId);
  let resultSet: data_rdb.ResultSet | null = null;
  try {
    resultSet = await rdbStore.query(CalendarsColumns.TABLE_NAME, predicate);
    if (!resultSet || !(resultSet?.rowCount > 0)) {
      return undefined;
    }
    resultSet.goToFirstRow();
    const calendarsIndexes: CalendarsIndexes | undefined = parseCalendarsIndexes(resultSet);
    return parseCalendars(resultSet, calendarsIndexes);
  } catch (err) {
    Log.error(TAG, `queryCalendarById get err ${err?.message}`);
  } finally {
    if (resultSet) {
      resultSet.close();
    }
  }
  return undefined;
}