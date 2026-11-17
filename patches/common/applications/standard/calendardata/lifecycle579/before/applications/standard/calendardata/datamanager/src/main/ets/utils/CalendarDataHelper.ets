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

import ohosDataRdb from '@ohos.data.relationalStore';
import { EventColumns } from '@ohos/datastructure/src/main/ets/events/EventColumns';
import { InstancesColumns } from '@ohos/datastructure/src/main/ets/instances/InstancesColumns';
import { CalendarsColumns } from '@ohos/datastructure/src/main/ets/calendars/CalendarsColumns';
import { ColorsColumns } from '@ohos/datastructure/src/main/ets/colors/ColorsColumns';
import { RemindersColumns } from '@ohos/datastructure/src/main/ets/reminders/RemindersColumns';
import { AttendeesColumns } from '@ohos/datastructure/src/main/ets/attendees/AttendeesColumns';
import { CalendarAlertsColumns } from '@ohos/datastructure/src/main/ets/calendaralerts/CalendarAlertsColumns';
import { CalendarCacheColumns } from '@ohos/datastructure/src/main/ets/calendarcache/CalendarCacheColumns';
import { EventsRawTimesColumns } from '@ohos/datastructure/src/main/ets/eventsrawtimes/EventsRawTimesColumns';
import {
  ExtendCalendarEventColumns
} from '@ohos/datastructure/src/main/ets/extendcalendarevent/ExtendCalendarEventColumns';
import {
  ExtendedPropertiesColumns
} from '@ohos/datastructure/src/main/ets/extendedproperties/ExtendedPropertiesColumns';
import { SyncStateColumns } from '@ohos/datastructure/src/main/ets/syncstate/SyncStateColumns';
import { MapAddressHistoryColumns } from '@ohos/datastructure/src/main/ets/location/MapAddressHistoryColumns';
import { SyncStateMetadataColumns } from '@ohos/datastructure/src/main/ets/syncstate/SyncStateMetadataColumns';
import { Constants } from '@ohos/datastructure/src/main/ets/Constants';
import { CalendarMetaDataColumns } from '@ohos/datastructure/src/main/ets/calendarmetadata/CalendarMetaDataColumns';
import { Log } from '@ohos/common/src/main/ets/utils/Log';
import { GlobalThis } from '@ohos/common/src/main/ets/utils/GlobalThis';

const CREATE_EVENTS_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${EventColumns.TABLE_NAME} (
    ${EventColumns.ID} INTEGER PRIMARY KEY AUTOINCREMENT,
    ${EventColumns.UUID} TEXT UNIQUE ON CONFLICT IGNORE,
    ${EventColumns.SYNC_ID} TEXT,
    ${EventColumns.DIRTY} INTEGER,
    ${EventColumns.MUTATORS} TEXT,
    ${EventColumns.EVENT_CALENDAR_TYPE} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.EVENT_IMAGE_TYPE} TEXT,
    ${EventColumns.LAST_SYNCED} INTEGER DEFAULT 0,
    ${EventColumns.CALENDAR_ID} INTEGER NOT NULL,
    ${EventColumns.TITLE} TEXT,
    ${EventColumns.EVENT_LOCATION} TEXT,
    ${EventColumns.LOCATION_LONGITUDE} TEXT,
    ${EventColumns.LOCATION_LATITUDE} TEXT,
    ${EventColumns.DESCRIPTION} TEXT,
    ${EventColumns.EVENT_COLOR} INTEGER,
    ${EventColumns.EVENT_COLOR_INDEX} TEXT,
    ${EventColumns.EVENT_STATUS} INTEGER,
    ${EventColumns.SELF_ATTENDEE_STATUS} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.DTSTART} INTEGER,
    ${EventColumns.DTEND} INTEGER,
    ${EventColumns.EVENT_TIMEZONE} TEXT,
    ${EventColumns.DURATION} TEXT,
    ${EventColumns.ALLDAY} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.ACCESS_LEVEL} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.AVAILABILITY} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.HAS_ALARM} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.HAS_EXTENDED_PROPERTIES} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.RRULE} TEXT,
    ${EventColumns.RDATE} TEXT,
    ${EventColumns.EXRULE} TEXT,
    ${EventColumns.EXDATE} TEXT,
    ${EventColumns.ORIGINAL_ID} INTEGER,
    ${EventColumns.ORIGINAL_SYNC_ID} TEXT,
    ${EventColumns.ORIGINAL_INSTANCE_TIME} INTEGER,
    ${EventColumns.ORIGINAL_ALL_DAY} INTEGER,
    ${EventColumns.LAST_DATE} INTEGER,
    ${EventColumns.EVENT_TIME_STAMP} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.HAS_ATTENDEE_DATE} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.GUESTS_CAN_MODIFY} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.GUESTS_CAN_INVITE_OTHERS} INTEGER NOT NULL DEFAULT 1,
    ${EventColumns.GUESTS_CAN_SEE_GUESTS} INTEGER NOT NULL DEFAULT 1,
    ${EventColumns.ORGANIZER} STRING,
    ${EventColumns.IS_ORGANIZER} INTEGER,
    ${EventColumns.DELETED} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.EVENT_END_TIMEZONE} TEXT,
    ${EventColumns.CUSTOM_APP_PACKAGE} TEXT,
    ${EventColumns.CUSTOM_APP_URI} TEXT,
    ${EventColumns.UID2445} TEXT,
    ${EventColumns.VERSION} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.EVENT_UUID} TEXT,
    ${EventColumns.HWEXT_ALERT_TYPE} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.IMPORTANT_EVENT_TYPE} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.SERVICE.SERVICE_VERIFIED} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.SERVICE.SERVICE_TYPE} TEXT,
    ${EventColumns.SERVICE.SERVICE_CP_BZ_URI} TEXT,
    ${EventColumns.SERVICE.SERVICE_CP_MNG_URI} TEXT,
    ${EventColumns.SERVICE.SERVICE_DESCRIPTION} TEXT,
    ${EventColumns.SERVICE.SERVICE_MIN_VERSION} INTEGER,
    ${EventColumns.SYNC_DATA1} TEXT,
    ${EventColumns.SYNC_DATA2} TEXT,
    ${EventColumns.SYNC_DATA3} TEXT,
    ${EventColumns.SYNC_DATA4} TEXT,
    ${EventColumns.SYNC_DATA5} TEXT,
    ${EventColumns.SYNC_DATA6} TEXT,
    ${EventColumns.SYNC_DATA7} TEXT,
    ${EventColumns.SYNC_DATA8} TEXT,
    ${EventColumns.SYNC_DATA9} TEXT,
    ${EventColumns.SYNC_DATA10} TEXT,
    ${EventColumns.KV_SYNC} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.KV_SYNC_TIME} INTEGER NOT NULL DEFAULT 0,
    ${EventColumns.CREATOR} TEXT NOT NULL,
    ${EventColumns.IDENTIFIER} TEXT,
    ${EventColumns.CALENDAR_UUID} TEXT
);`;

const EVENT_UUID_INDEX = `CREATE INDEX IF NOT EXISTS events_uuid_index ON ${EventColumns.TABLE_NAME} (${EventColumns.UUID})`;

/**
 * the create Calendars table sql
 */
let CREATE_CALENDARS_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${CalendarsColumns.TABLE_NAME} (`
  + `${CalendarsColumns.ID} INTEGER PRIMARY KEY, `
  + `${CalendarsColumns.ACCOUNT_NAME} TEXT, `
  + `${CalendarsColumns.ACCOUNT_TYPE} TEXT, `
  + `${CalendarsColumns.SYNC_ID} TEXT, `
  + `${CalendarsColumns.DIRTY} INTEGER, `
  + `${CalendarsColumns.MUTATORS} TEXT, `
  + `${CalendarsColumns.NAME} TEXT, `
  + `${CalendarsColumns.CALENDAR_DISPLAY_NAME} TEXT, `
  + `${CalendarsColumns.CALENDAR_COLOR} INTEGER, `
  + `${CalendarsColumns.CALENDAR_COLOR_INDEX} TEXT, `
  + `${CalendarsColumns.CALENDAR_ACCESS_LEVEL} INTEGER, `
  + `${CalendarsColumns.VISIBLE} INTEGER NOT NULL DEFAULT 1, `
  + `${CalendarsColumns.SYNC_EVENTS} INTEGER NOT NULL DEFAULT 0, `
  + `${CalendarsColumns.CALENDAR_LOCATION} TEXT, `
  + `${CalendarsColumns.CALENDAR_TIMEZONE} TEXT, `
  + `${CalendarsColumns.OWNER_ACCOUNT} TEXT, `
  + `${CalendarsColumns.IS_PRIMARY} INTEGER, `
  + `${CalendarsColumns.CAN_ORGANIZER_RESPOND} INTEGER NOT NULL DEFAULT 1, `
  + `${CalendarsColumns.CAN_MODIFY_TIMEZONE} INTEGER DEFAULT 1, `
  + `${CalendarsColumns.CAN_PARTIALLY_UPDATE} INTEGER DEFAULT 0, `
  + `${CalendarsColumns.MAX_REMINDERS} INTEGER DEFAULT 5, `
  + `${CalendarsColumns.ALLOWED_REMINDERS} TEXT DEFAULT '0,1', `
  + `${CalendarsColumns.ALLOWED_AVAILABILITY} TEXT DEFAULT '0,1', `
  + `${CalendarsColumns.ALLOWED_ATTENDEE_TYPES} TEXT DEFAULT '0,1,2', `
  + `${CalendarsColumns.DELETED} INTEGER NOT NULL DEFAULT 0, `
  + `${CalendarsColumns.CALENDAR_TIME_STAMP} INTEGER NOT NULL DEFAULT 0, `
  + `${CalendarsColumns.CAL_SYNC1} TEXT, `
  + `${CalendarsColumns.CAL_SYNC2} TEXT, `
  + `${CalendarsColumns.CAL_SYNC3} TEXT, `
  + `${CalendarsColumns.CAL_SYNC4} TEXT, `
  + `${CalendarsColumns.CAL_SYNC5} TEXT, `
  + `${CalendarsColumns.CAL_SYNC6} TEXT, `
  + `${CalendarsColumns.CAL_SYNC7} TEXT, `
  + `${CalendarsColumns.CAL_SYNC8} TEXT, `
  + `${CalendarsColumns.CAL_SYNC9} TEXT, `
  + `${CalendarsColumns.CAL_SYNC10} TEXT, `
  + `${CalendarsColumns.CAN_REMINDER} INTEGER NOT NULL DEFAULT 1, `
  + `${CalendarsColumns.CREATOR} TEXT NOT NULL, `
  + `${CalendarsColumns.UUID} TEXT NOT NULL UNIQUE)`;

/**
 * the create Reminders table sql
 */
let CREATE_REMINDERS_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${RemindersColumns.TABLE_NAME} (`
  + `${RemindersColumns.ID} INTEGER PRIMARY KEY AUTOINCREMENT, `
  + `${RemindersColumns.EVENT_ID} INTEGER, `
  + `${RemindersColumns.MINUTES} INTEGER, `
  + `${RemindersColumns.METHOD} INTEGER NOT NULL DEFAULT 0, `
  + `${RemindersColumns.CREATOR} TEXT NOT NULL, `
  + `${RemindersColumns.REMINDER_UUID} TEXT, `
  + `${RemindersColumns.EVENT_UUID} TEXT, `
  + `UNIQUE (${RemindersColumns.REMINDER_UUID}))`;

/**
 * the create Instances table sql
 */
let CREATE_INSTANCES_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${InstancesColumns.TABLE_NAME} (`
  + `${InstancesColumns.ID} INTEGER PRIMARY KEY AUTOINCREMENT, `
  + `${InstancesColumns.EVENT_ID} INTEGER, `
  + `${InstancesColumns.BEGIN} INTEGER, `
  + `${InstancesColumns.END} INTEGER, `
  + `${InstancesColumns.START_DAY} INTEGER, `
  + `${InstancesColumns.END_DAY} INTEGER, `
  + `${InstancesColumns.START_MINUTE} INTEGER, `
  + `${InstancesColumns.END_MINUTE} INTEGER, `
  + `${InstancesColumns.CREATOR} TEXT NOT NULL, `
  + `${InstancesColumns.UUID} TEXT, `
  + `${InstancesColumns.EVENT_UUID} TEXT, `
  + `UNIQUE (${InstancesColumns.UUID}) ON CONFLICT REPLACE)`;

/**
 * the create Colors table sql
 */
let CREATE_COLORS_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${ColorsColumns.TABLE_NAME} (`
  + `${ColorsColumns.ID} INTEGER PRIMARY KEY, `
  + `${ColorsColumns.ACCOUNT_NAME} TEXT NOT NULL, `
  + `${ColorsColumns.ACCOUNT_TYPE} TEXT NOT NULL, `
  + `${ColorsColumns.DATA} TEXT, `
  + `${ColorsColumns.COLOR_TYPE} INTEGER NOT NULL, `
  + `${ColorsColumns.COLOR_INDEX} TEXT NOT NULL, `
  + `${ColorsColumns.COLOR} INTEGER NOT NULL)`;

/**
 * the create Attendees table sql
 */
let CREATE_ATTENDEES_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${AttendeesColumns.TABLE_NAME} (`
  + `${AttendeesColumns.ID} INTEGER PRIMARY KEY, `
  + `${AttendeesColumns.EVENT_ID} INTEGER, `
  + `${AttendeesColumns.ATTENDEE_NAME} TEXT, `
  + `${AttendeesColumns.ATTENDEE_EMAIL} TEXT, `
  + `${AttendeesColumns.ATTENDEE_STATUS} INTEGER, `
  + `${AttendeesColumns.ATTENDEE_RELATIONSHIP} INTEGER, `
  + `${AttendeesColumns.ATTENDEE_TYPE} INTEGER, `
  + `${AttendeesColumns.ATTENDEE_IDENTITY} TEXT, `
  + `${AttendeesColumns.ATTENDEE_ID_NAMESPACE} TEXT)`;

/**
 * the create CalendarAlerts table sql
 */
const CREATE_CALENDAR_ALERTS_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${CalendarAlertsColumns.TABLE_NAME} (` +
  `${CalendarAlertsColumns.ID} INTEGER PRIMARY KEY AUTOINCREMENT, ` +
  `${CalendarAlertsColumns.EVENT_ID} INTEGER, ` +
  `${CalendarAlertsColumns.EVENT_UUID} TEXT, ` +
  `${CalendarAlertsColumns.BEGIN} INTEGER NOT NULL, ` +
  `${CalendarAlertsColumns.END} INTEGER NOT NULL, ` +
  `${CalendarAlertsColumns.ALARM_TIME} INTEGER NOT NULL, ` +
  `${CalendarAlertsColumns.CREATION_TIME} INTEGER NOT NULL DEFAULT 0, ` +
  `${CalendarAlertsColumns.RECEIVED_TIME} INTEGER NOT NULL DEFAULT 0, ` +
  `${CalendarAlertsColumns.NOTIFY_TIME} INTEGER NOT NULL DEFAULT 0, ` +
  `${CalendarAlertsColumns.STATE} INTEGER NOT NULL, ` +
  `${CalendarAlertsColumns.MINUTES} INTEGER, ` +
  `${CalendarAlertsColumns.CREATOR} TEXT NOT NULL,` +
  `${CalendarAlertsColumns.TITLE} TEXT,` +
  `${CalendarAlertsColumns.CONTENT} TEXT,` +
  `${CalendarAlertsColumns.WANT_AGENT} TEXT,` +
  `${CalendarAlertsColumns.BUTTONS} TEXT,` +
  `${CalendarAlertsColumns.SLOT_TYPE} INTEGER,` +
  `${CalendarAlertsColumns.KEEP_HEADSUP} INTEGER,` +
  `${CalendarAlertsColumns.TYPE} INTEGER NOT NULL DEFAULT 0,` +
  `${CalendarAlertsColumns.IDENTIFIER} TEXT NOT NULL,` +
  `${CalendarAlertsColumns.RING_DURATION} INTEGER,` +
  `${CalendarAlertsColumns.CUSTOM_RING_URI} TEXT,` +
  `${CalendarAlertsColumns.TIME_INTERVAL} INTEGER,` +
  `${CalendarAlertsColumns.SNOOZE_TIMES} INTEGER,` +
  `${CalendarAlertsColumns.SNOOZE_SLOT_TYPE} INTEGER,` +
  `${CalendarAlertsColumns.SNOOZE_CONTENT} TEXT,` +
  `${CalendarAlertsColumns.EXPIRED_CONTENT} TEXT,` +
  `${CalendarAlertsColumns.MAX_SCREEN_WANT_AGENT} TEXT,` +
  `${CalendarAlertsColumns.NEED_AGENT} INTEGER DEFAULT 1,` +
  `${CalendarAlertsColumns.UUID} TEXT,` +
  `UNIQUE (${CalendarAlertsColumns.ALARM_TIME},${CalendarAlertsColumns.BEGIN},` +
  `${CalendarAlertsColumns.EVENT_ID}))`;

/**
 * the create CalendarCache table sql
 */
let CREATE_CALENDAR_CACHE_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${CalendarCacheColumns.TABLE_NAME} (`
  + `${CalendarCacheColumns.ID} INTEGER PRIMARY KEY, `
  + `${CalendarCacheColumns.KEY} TEXT NOT NULL, `
  + `${CalendarCacheColumns.VALUE} TEXT)`;

/**
 * the create CalendarMetaData table sql
 */
let CREATE_CALENDAR_METADATA_TABLE_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${CalendarMetaDataColumns.TABLE_NAME} (`
  + `${CalendarMetaDataColumns.ID} INTEGER PRIMARY KEY, `
  + `${CalendarMetaDataColumns.LOCAL_TIME_ZONE} TEXT, `
  + `${CalendarMetaDataColumns.MIN_INSTANCE} INTEGER, `
  + `${CalendarMetaDataColumns.MAX_INSTANCE} INTEGER)`;

/**
 * the create EventsRawTimes table sql
 */
let CREATE_EVENTS_RAW_TIMES_TABLE_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${EventsRawTimesColumns.TABLE_NAME} (`
  + `${EventsRawTimesColumns.ID} INTEGER PRIMARY KEY, `
  + `${EventsRawTimesColumns.EVENT_ID} INTEGER NOT NULL, `
  + `${EventsRawTimesColumns.DT_START_2445} TEXT, `
  + `${EventsRawTimesColumns.DT_END_2445} TEXT, `
  + `${EventsRawTimesColumns.ORIGINAL_INSTANCE_TIME2445} TEXT, `
  + `${EventsRawTimesColumns.LAST_DATE2445} TEXT, `
  + `UNIQUE (${EventsRawTimesColumns.EVENT_ID}))`;

/**
 * the create map_address_history table sql
 */
let CREATE_MAP_ADDRESS_HISTORY_TABLE_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${MapAddressHistoryColumns.TABLE_NAME} (`
  + `${MapAddressHistoryColumns.ID} INTEGER PRIMARY KEY AUTOINCREMENT, `
  + `${MapAddressHistoryColumns.ADDRESS} TEXT, `
  + `${MapAddressHistoryColumns.NAME} TEXT, `
  + `${MapAddressHistoryColumns.LAT} TEXT, `
  + `${MapAddressHistoryColumns.LON} TEXT, `
  + `${MapAddressHistoryColumns.TIME} TEXT, `
  + `${MapAddressHistoryColumns.DATA1} TEXT, `
  + `${MapAddressHistoryColumns.DATA2} TEXT)`;

/**
 * the create ExtendedProperties table sql
 */
let CREATE_EXTENDED_PROPERTIES_TABLE_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${ExtendedPropertiesColumns.TABLE_NAME} (`
  + `${ExtendedPropertiesColumns.ID} INTEGER PRIMARY KEY, `
  + `${ExtendedPropertiesColumns.EVENT_ID} INTEGER, `
  + `${ExtendedPropertiesColumns.NAME} TEXT, `
  + `${ExtendedPropertiesColumns.VALUE} TEXT)`;

/**
 * the create _sync_state table sql
 */
let CREATE_SYNC_STATE_TABLE_SQL = `CREATE TABLE IF NOT EXISTS ${SyncStateColumns.TABLE_NAME} (`
  + `${SyncStateColumns.ID} INTEGER PRIMARY KEY, `
  + `${SyncStateColumns.ACCOUNT_NAME} TEXT NOT NULL, `
  + `${SyncStateColumns.ACCOUNT_TYPE} TEXT NOT NULL, `
  + `${SyncStateColumns.DATA} TEXT NOT NULL, `
  + `UNIQUE (${SyncStateColumns.ACCOUNT_NAME},${SyncStateColumns.ACCOUNT_TYPE}))`;

/**
 * the create _sync_state_metadata table sql
 */
let CREATE_SYNC_STATE_METADATA_TABLE_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${SyncStateMetadataColumns.TABLE_NAME} (`
  + `${SyncStateMetadataColumns.VERSION} INTEGER)`;

/**
 * the create ExtendCalendarEvent table sql
 */
let CREATE_EXTEND_CALENDAR_EVENT_TABLE_NAME_SQL = `CREATE TABLE IF NOT EXISTS `
  + `${ExtendCalendarEventColumns.TABLE_NAME} (`
  + `${ExtendCalendarEventColumns.ID} INTEGER PRIMARY KEY, `
  + `${ExtendCalendarEventColumns.HWEXT_EVENT_ID} INTEGER, `
  + `${ExtendCalendarEventColumns.HWEXT_TYPE} INTEGER, `
  + `${ExtendCalendarEventColumns.HWEXT_APP_URI} TEXT, `
  + `${ExtendCalendarEventColumns.HWEXT_APP_NAME} TEXT, `
  + `${ExtendCalendarEventColumns.HWEXT_ACTION} TEXT, `
  + `${ExtendCalendarEventColumns.HWEXT_METHOD} INTEGER, `
  + `${ExtendCalendarEventColumns.HWEXT_SUPPORT_MIN_VERSION} INTEGER, `
  + `${ExtendCalendarEventColumns.HWEXT_STATUS} INTEGER, `
  + `${ExtendCalendarEventColumns.HWEXT_DESCRIPTION} TEXT)`;

let TAG = 'CalendarDataHelper';

/**
 * the class to initialize the calendar database
 *
 * @since 2022-04-06
 */
class CalendarDataHelper {
  private static instance: CalendarDataHelper;

  private rdbStore: ohosDataRdb.RdbStore | undefined = undefined;

  private constructor() {
  }

  /**
   * get the instance of CalendarDataHelper class
   */
  public static getInstance() {
    if (!CalendarDataHelper.instance) {
      Log.log(TAG, 'call getInstance init');
      CalendarDataHelper.instance = new CalendarDataHelper();
    }
    return CalendarDataHelper.instance;
  }

  /**
   * get the instance of rdbStore
   */
  public async getRdbStore() {
    if (this.rdbStore === null || this.rdbStore === undefined) {
      await CalendarDataHelper.getInstance().initRdbStore();
    }
    return this.rdbStore;
  }

  private async initRdbStore() {
    Log.log(TAG, 'call initRdbStore start');
    this.rdbStore = await ohosDataRdb.getRdbStore(GlobalThis.getInstance().getBasicContext(), {
      name: Constants.DB_NAME,
      securityLevel: ohosDataRdb.SecurityLevel.S1,
    }).then();
    if (this.rdbStore == null || this.rdbStore == undefined) {
      Log.error(TAG, 'initRdbStore rdbStore is null');
      return;
    }
    try {
      await this.createEventsTable();
      Log.log(TAG, 'initRdbStore createEventsTable succeed');
    } catch (err) {
      Log.error(TAG, `initRdbStore createEventsTable get err:${err.message}`);
    }
    Log.log(TAG, 'initRdbStore executeSql start');
    try {
      await this.rdbStore?.executeSql(CREATE_CALENDARS_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore createCalendarsTable succeed');
      await this.rdbStore?.executeSql(CREATE_REMINDERS_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_REMINDERS_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_INSTANCES_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_INSTANCES_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_COLORS_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_COLORS_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_ATTENDEES_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_ATTENDEES_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_CALENDAR_ALERTS_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_CALENDAR_ALERTS_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_CALENDAR_CACHE_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_CALENDAR_CACHE_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_CALENDAR_METADATA_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_CALENDAR_METADATA_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_EVENTS_RAW_TIMES_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_EVENTS_RAW_TIMES_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_MAP_ADDRESS_HISTORY_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_MAP_ADDRESS_HISTORY_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_EXTENDED_PROPERTIES_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_EXTENDED_PROPERTIES_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_SYNC_STATE_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_SYNC_STATE_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_SYNC_STATE_METADATA_TABLE_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_SYNC_STATE_METADATA_TABLE_SQL succeed');
      await this.rdbStore?.executeSql(CREATE_EXTEND_CALENDAR_EVENT_TABLE_NAME_SQL, []);
      Log.log(TAG, 'initRdbStore CREATE_EXTEND_CALENDAR_EVENT_TABLE_NAME_SQL succeed');

      this.createSyncIdUpdateTrigger();
      Log.log(TAG, 'initRdbStore createSyncIdUpdateTrigger succeed');
      this.createDeleteEventTriggers();
      Log.log(TAG, 'initRdbStore createDeleteEventTriggers succeed');
      this.createColorsTriggers();
      Log.log(TAG, 'initRdbStore createColorsTriggers succeed');
      this.createCalendarCleanupTrigger();
      Log.log(TAG, 'initRdbStore createCalendarCleanupTrigger succeed');
      Log.log(TAG, 'initRdbStore executeSql end');
    } catch (err) {
      Log.error(TAG, `initRdbStore err:${err.message}`);
    }
  }

  private async createEventsTable() {
    try {
      Log.log(TAG, 'call createEventsTable start');
      await this.rdbStore?.executeSql(CREATE_EVENTS_TABLE_SQL, []);
      await this.rdbStore?.executeSql(EVENT_UUID_INDEX, []);
      Log.log(TAG, 'call createEventsTable end');
    } catch (err) {
      Log.error(TAG, `createEventsTable err:${err.message}`);
    }
  }

  private async createDeleteEventTriggers() {
    Log.log(TAG, 'call createDeleteEventTriggers start');
    let EVENTS_CLEANUP_TRIGGER_SQL =
      `DELETE FROM ${InstancesColumns.TABLE_NAME}` +
      ` WHERE ${InstancesColumns.EVENT_ID} = old.${EventColumns.ID};` +
      `DELETE FROM ${EventsRawTimesColumns.TABLE_NAME}` +
      ` WHERE ${EventsRawTimesColumns.EVENT_ID} = old.${EventColumns.ID};` +
      `DELETE FROM ${AttendeesColumns.TABLE_NAME}` +
      ` WHERE ${AttendeesColumns.EVENT_ID} = old.${EventColumns.ID};` +
      `DELETE FROM ${ExtendCalendarEventColumns.TABLE_NAME}` +
      ` WHERE ${ExtendCalendarEventColumns.HWEXT_EVENT_ID} = ` +
      `old.${EventColumns.ID};` +
      `DELETE FROM ${RemindersColumns.TABLE_NAME}` +
      ` WHERE ${RemindersColumns.EVENT_ID} = old.${EventColumns.ID};` +
      `DELETE FROM ${CalendarAlertsColumns.TABLE_NAME}` +
      ` WHERE ${CalendarAlertsColumns.EVENT_ID} = old.${EventColumns.ID};` +
      `DELETE FROM ${ExtendedPropertiesColumns.TABLE_NAME}` +
      ` WHERE ${ExtendedPropertiesColumns.EVENT_ID} = old.${EventColumns.ID};`

    let EVENTS_CLEANUP_TRIGGER = `CREATE TRIGGER events_cleanup_delete DELETE ON ` +
      `${EventColumns.TABLE_NAME} BEGIN ${EVENTS_CLEANUP_TRIGGER_SQL} END`;
    try {
      await this.rdbStore?.executeSql(EVENTS_CLEANUP_TRIGGER, []);
      Log.log(TAG, 'call createDeleteEventTriggers end');
    } catch (err) {
      Log.error(TAG, `createDeleteEventTriggers err:${err?.message}`);
    }
  }

  private async createColorsTriggers() {
    Log.log(TAG, 'call createColorsTriggers start');
    let EVENT_UPDATE_COLOR_TRIGGER_SQL = `UPDATE ${EventColumns.TABLE_NAME}` +
      ` SET eventColor=(SELECT ${ColorsColumns.COLOR} FROM ` +
      `${ColorsColumns.TABLE_NAME}` +
      ` WHERE ${ColorsColumns.ACCOUNT_NAME} = (SELECT ` +
      `${CalendarsColumns.ACCOUNT_NAME}` +
      ` FROM ${CalendarsColumns.TABLE_NAME} WHERE ${CalendarsColumns.ID} =` +
      ` new.${EventColumns.CALENDAR_ID}) AND ${ColorsColumns.ACCOUNT_TYPE}` +
      ` = (SELECT ${CalendarsColumns.ACCOUNT_TYPE} FROM ` +
      `${CalendarsColumns.TABLE_NAME}` +
      ` WHERE ${CalendarsColumns.ID} = new.${EventColumns.CALENDAR_ID})` +
      ` AND ${ColorsColumns.COLOR_INDEX} = ` +
      `new.${EventColumns.EVENT_COLOR_INDEX}` +
      ` AND ${ColorsColumns.COLOR_TYPE} = 1)` +
      ` WHERE ${EventColumns.ID} = old.${EventColumns.ID};`;
    let CREATE_EVENT_COLOR_UPDATE_TRIGGER = `CREATE TRIGGER ` +
      `event_color_update UPDATE OF ${EventColumns.EVENT_COLOR_INDEX} ON ` +
      `${EventColumns.TABLE_NAME} WHEN new.${EventColumns.EVENT_COLOR_INDEX} ` +
      `NOT NULL BEGIN ${EVENT_UPDATE_COLOR_TRIGGER_SQL} END`;

    let CALENDAR_UPDATE_COLOR_TRIGGER_SQL = `UPDATE ${CalendarsColumns.TABLE_NAME} ` +
      `SET ${CalendarsColumns.CALENDAR_COLOR} = (SELECT ` +
      `${ColorsColumns.COLOR} FROM ${ColorsColumns.TABLE_NAME} WHERE ` +
      `${ColorsColumns.ACCOUNT_NAME} = ` +
      `new.${CalendarsColumns.ACCOUNT_NAME} AND ` +
      `${ColorsColumns.ACCOUNT_TYPE} = ` +
      `new.${CalendarsColumns.ACCOUNT_TYPE} AND ` +
      `${ColorsColumns.COLOR_INDEX} = ` +
      `new.${CalendarsColumns.CALENDAR_COLOR_INDEX} AND ` +
      `${ColorsColumns.COLOR_TYPE} = 0) ` +
      ` WHERE ${CalendarsColumns.ID} = old.${CalendarsColumns.ID};`;
    let CREATE_CALENDAR_COLOR_UPDATE_TRIGGER = `CREATE TRIGGER ` +
      `calendar_color_update UPDATE OF ${CalendarsColumns.CALENDAR_COLOR_INDEX}` +
      ` ON ${CalendarsColumns.TABLE_NAME} WHEN` +
      ` new.${CalendarsColumns.CALENDAR_COLOR_INDEX} NOT NULL` +
      ` BEGIN ${CALENDAR_UPDATE_COLOR_TRIGGER_SQL} END`;

    try {
      Log.log(TAG, 'call CREATE_EVENT_COLOR_UPDATE_TRIGGER');
      await this.rdbStore?.executeSql(CREATE_EVENT_COLOR_UPDATE_TRIGGER, []);
      Log.log(TAG, 'call CREATE_CALENDAR_COLOR_UPDATE_TRIGGER');
      await this.rdbStore?.executeSql(CREATE_CALENDAR_COLOR_UPDATE_TRIGGER, []);
      Log.log(TAG, 'call createColorsTriggers end');
    } catch (err) {
      Log.error(TAG, `createColorsTriggers err:${err?.message}`);
    }

  }

  private async createCalendarCleanupTrigger() {
    Log.log(TAG, 'call createCalendarCleanupTrigger start');
    let CALENDAR_CLEANUP_TRIGGER_SQL = `DELETE FROM ` +
      `${EventColumns.TABLE_NAME} WHERE ` +
      `${EventColumns.CALENDAR_ID} = old.${EventColumns.ID};`;
    let CALENDAR_CLEANUP_TRIGGER = `CREATE TRIGGER calendar_cleanup DELETE ON ` +
      `${CalendarsColumns.TABLE_NAME} ` +
      `BEGIN ${CALENDAR_CLEANUP_TRIGGER_SQL} END`;
    try {
      await this.rdbStore?.executeSql(CALENDAR_CLEANUP_TRIGGER, []);
      Log.log(TAG, 'call createCalendarCleanupTrigger end');
    } catch (err) {
      Log.error(TAG, `createCalendarCleanupTrigger err:${err?.message}`);
    }
  }

  private async createSyncIdUpdateTrigger() {
    let EVENTS_ORIGINAL_SYNC_TRIGGER_SQL = `UPDATE ${EventColumns.TABLE_NAME}` +
      ` SET ${EventColumns.ORIGINAL_SYNC_ID} = ` +
      `new.${EventColumns.SYNC_ID}` +
      ` WHERE ${EventColumns.ORIGINAL_ID} =old.${EventColumns.ID};`;
    let CREATE_SYNC_ID_UPDATE_TRIGGER = `CREATE TRIGGER original_sync_update` +
      ` UPDATE OF ${EventColumns.SYNC_ID}` +
      ` ON ${EventColumns.TABLE_NAME}` +
      ` BEGIN ${EVENTS_ORIGINAL_SYNC_TRIGGER_SQL} END`;
    try {
      Log.log(TAG, 'call createSyncIdUpdateTrigger start');
      await this.rdbStore?.executeSql(CREATE_SYNC_ID_UPDATE_TRIGGER, []);
      Log.log(TAG, 'call createSyncIdUpdateTrigger end');
    } catch (err) {
      Log.error(TAG, `createSyncIdUpdateTrigger err:${err?.message}`);
    }
  }
}

export default CalendarDataHelper;