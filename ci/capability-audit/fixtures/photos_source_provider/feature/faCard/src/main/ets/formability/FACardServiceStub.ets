/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2024-2025. All rights reserved.
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

import lazy { Log } from '@ohos/common/src/main/ets/default/utils/Log';
import lazy { AlbumDefine } from '@ohos/common/src/main/ets/default/model/browser/AlbumDefine';
import lazy {
  UserFileManagerAccess,
  PhotoAsset,
  PhotoAlbum
} from '@ohos/common/src/main/ets/default/access/UserFileManagerAccess';
import lazy { photoAccessHelper } from '@kit.MediaLibraryKit';
import lazy DatabaseUtils from '@ohos/dataprovider/src/main/ets/database/DatabaseUtils';
import lazy {
  PhotoProcessHandler
} from '@ohos/dataprovider/src/main/ets/database/service/PhotoProcessHandler';
import lazy { Constants } from '@ohos/common/src/main/ets/default/model/common/Constants';
import lazy { dataSharePredicates, DataShareResultSet, ValuesBucket } from '@kit.ArkData';
import lazy formBindingData from '@ohos.app.form.formBindingData';
import lazy { formProvider } from '@kit.FormKit';
import lazy common from '@ohos.app.ability.common';
import lazy { IsShowAlbumName } from '../../../../../../feature/dataProvider/src/main/ets/database/databaseconstant/FaCardTable.ets';
import DatabaseProxy from '@ohos/dataprovider/src/main/ets/database/DatabaseProxy';
import { trash } from '@kit.CoreFileKit';
import { PipeStream } from '@ohos/dataprovider/src/main/ets/promise/PromiseStream';
import { FACardChangeTypesConstants,
  FormConstants } from '@ohos/common/src/main/ets/default/model/common/FormConstants';
import FaCardService, { FaCardInfo } from '@ohos/dataprovider/src/main/ets/database/service/FaCardService';
import ReminderService, { ImageInfo } from '@ohos/dataprovider/src/main/ets/database/service/ReminderService';
import { Task, TaskUri } from '@ohos/dataprovider/src/main/ets/database/databaseconstant/TaskInfo';
import { FormControllerManager } from '@ohos/dataprovider/src/main/ets/controller/FormControllerManager';
import ImageProxyDataService from '@ohos/dataprovider/src/main/ets/database/service/ImageProxyDataService';
import { RemindersTable } from '@ohos/dataprovider/src/main/ets/database/databaseconstant/RemindersTable';
import lazy data_rdb from '@ohos.data.relationalStore';
import { AlbumType, FaCardTable } from '@ohos/dataprovider/src/main/ets/database/databaseconstant/FaCardTable';
import { FaCardAlbumUtils } from '@ohos/dataprovider/src/main/ets/database/service/FaCardAlbumService';

/* instrument ignore file */
const TAG: string = 'FACardServiceStub';

interface updateItemI {
    formId: string,
    imageUri: string,
    isAlbumChanged: boolean,
}

export default class FACardServiceStub {
  private static instance: FACardServiceStub;
  private context: Context;
  private needRefreshForms: Set<string>;
  private initialized: boolean = false;
  private userFileManagerAccess: UserFileManagerAccess = new UserFileManagerAccess();
  private cardsUpdatedMap: Map<string, string> = new Map();
  private albumCountMap: Map<string, number> = new Map();
  private cameraAlbumUri: string = '';
  private trashAlbumUri: string = '';
  public pipeStreamInstance: PipeStream<void> = new PipeStream();

  public constructor(context: Context) {
    this.context = context;
    this.needRefreshForms = new Set<string>();

    this.userFileManagerAccess.onCreate(this.context);
  }

  public static getInstance(context: Context): FACardServiceStub {
    if (!FACardServiceStub.instance) {
      FACardServiceStub.instance = new FACardServiceStub(context);
    }
    return FACardServiceStub.instance;
  }

  private async initRdbStoreAndTrashAlbum() : Promise<void> {
    if (!this.initialized) {
      return;
    }

    await DatabaseProxy.getInstance().init();

    let trashAlbum: PhotoAlbum | undefined = undefined;
    try {
      trashAlbum = await this.userFileManagerAccess.getTrashAlbum();
      if (!trashAlbum) {
        Log.info(TAG, 'initRdbStoreAndTrashAlbum trashAlbum is undefined');
        return;
      }
      this.trashAlbumUri = trashAlbum.albumUri;
    } catch (err) {
      Log.info(TAG, 'initRdbStoreAndTrashAlbum error');
    }

    this.initialized = true;
  }

  public async submitToStream(myWant: Want): Promise<void> {
    const currentId = Date.now().toString();
    Log.info(TAG, `submitToStream pipeStream start: ${currentId}`);
    await this.pipeStreamInstance.emitAndGetStream(async () => {
      await this.handler(myWant);
    }, currentId);
    Log.info(TAG, `submitToStream pipeStream done: ${currentId}`);
  }

  public async handler(want: Want): Promise<void> {
    await this.initRdbStoreAndTrashAlbum();

    const param = want.parameters;
    if (!param) {
      Log.info(TAG, 'handle error without param');
      return;
    }
    Log.info(TAG, `FA handler param ${JSON.stringify(param)}`);
    const changeType = param.assetChangeType as number;
    const changeTypes = param.assetChangeTypes as number[];
    const changeUris = param.assetChangeUris as string[];

    this.needRefreshForms = new Set<string>();
    const imageUpdateUris: Set<string> = new Set();
    this.cardsUpdatedMap.clear();
    this.albumCountMap.clear();
    for (let i = 0; i < changeTypes.length; i++) {
      const changeType = changeTypes[i];
      const changeUri = changeUris[i];
      const albumMatchResult: RegExpMatchArray | null = changeUri.match(/file:\/\/media\/PhotoAlbum/);
      if (albumMatchResult) {
        if (changeUri === this.trashAlbumUri) {

        } else {
          await this.handleAlbumChange(changeType, changeUri);
        }
      }
      if (changeType === FACardChangeTypesConstants.IMAGE_UPDATE_TYPE) {
        imageUpdateUris.add(changeUri);
      }
    }
    if (imageUpdateUris.size) {
      await this.handleUpdate(Array.from(imageUpdateUris));
    }

    await this.refreshForms();
  }

  private async refreshForms() {
    if (!this.needRefreshForms.size) {
      return;
    }
    let faCardResult: data_rdb.ResultSet | undefined = undefined;
    try {
      const formIds: string[] = Array.from(this.needRefreshForms);
      const faCardPredicates: dataSharePredicates.DataSharePredicates = new dataSharePredicates.DataSharePredicates();
      faCardPredicates.in(FaCardTable.FORM_ID, formIds);

      faCardResult = await DatabaseProxy.getInstance().queryWithOutCallback(
        FormConstants.FACARD_TABLE_URI,
        faCardPredicates,
        [FaCardTable.FORM_ID, FaCardTable.PLAYBACK_INTERVAL, FaCardTable.ALBUM_TYPE]);

      let faCardType: number = AlbumType.ALBUM;
      while (faCardResult && faCardResult.goToNextRow()) {
        faCardType = Number(faCardResult.getString(2));
        await FaCardAlbumUtils.updateScheduler(faCardResult.getString(0), Number(faCardResult.getString(1)),
          true, this.context);
      }
    } catch (error) {
      Log.error(TAG, `refreshForms error`)
    } finally {
      faCardResult?.close();
    }
  }

  private async checkInTrash() : Promise<void> {
  }

  private async handleAlbumChange(changeType: number, changeUri: string): Promise<void> {
    if (changeType !== FACardChangeTypesConstants.IMAGE_ADD_TYPE) {
      return;
    }
    const faCardService: FaCardService = new FaCardService(this.context as Context);
    const faCardInfos: FaCardInfo[] = await faCardService.queryFaCardsByAlbumUri(changeUri);
    for (let i = 0; i < faCardInfos.length; i++) {
      const reminderService = new ReminderService(this.context);
      const reminderResultSet = await reminderService.queryByFormId(faCardInfos[i].formId, true);
      const reminderImageNO = reminderResultSet?.rowCount ?? 0;
      if (reminderImageNO < FormConstants.LIMIT_COUNT) {
        const nowTask: Task = {
          formId: faCardInfos[i].formId,
          taskUri: TaskUri.TASK_MEDIA_UPDATE_ALBUM_URI,
          faCardInfo: faCardInfos[i],
        }
        await FormControllerManager.getInstance(this.context).doTask(nowTask);
      }
      reminderResultSet?.close();
    }
  }

  private async handleUpdate(uris: string[]): Promise<void> {
    const imageProxyDataService: ImageProxyDataService = new ImageProxyDataService(this.context);
    const reminderService: ReminderService = new ReminderService(this.context);
    let reminderResultSet: DataShareResultSet | undefined = undefined;
    try {
      reminderResultSet = await reminderService.queryImageByImageUriId(uris, false);
      const updateItems: Record<string, updateItemI[]> = {'undefined' : []};
      if (!reminderResultSet || reminderResultSet.rowCount <= 0) {
        return;
      }

      const albumUriIndex: number = reminderResultSet.getColumnIndex(RemindersTable.ALBUM_URI);
      const formIdIndex: number = reminderResultSet.getColumnIndex(RemindersTable.FORM_ID);
      const index: number = reminderResultSet.getColumnIndex(RemindersTable.IMAGE_URI);
      reminderResultSet.goToFirstRow();
      for (let i = 0; i < reminderResultSet.rowCount; i++) {
        const albumUri = reminderResultSet.getString(albumUriIndex);
        const formId = reminderResultSet.getString(formIdIndex);
        const uri = reminderResultSet.getString(index);
        const item: updateItemI = {
          formId: formId,
          imageUri: uri,
          isAlbumChanged: false,
        }
        if (!albumUri) {
          updateItems['undefined'].push(item);
        } else if (updateItems[albumUri]) {
          updateItems[albumUri].push(item);
        } else {
          updateItems[albumUri] = [item];
        }
        reminderResultSet.goToNextRow();
      }
      const albums = Object.keys(updateItems);
      for (let i = 0; i < albums.length; i++) {
        const albumUri = albums[i];
        if (albumUri !== 'undefined') {
          const uris: string[] = updateItems[albumUri].map((item: updateItemI) => item.imageUri);
          const result: Record<string, boolean> = await this.checkIsAlbumChanged(uris, albumUri);
          updateItems[albumUri].forEach(item => item.isAlbumChanged = result[item.imageUri]);
        }
      }
      const updateItemsArray: updateItemI[] = Object.values(updateItems).flat();
      await this.updateImage(reminderService, imageProxyDataService, updateItemsArray);
    } catch (error) {
      Log.error(TAG, `handleUpdate error: ${JSON.stringify(error)}`);
    } finally {
      reminderResultSet?.close();
    }
  }

  private async checkIsAlbumChanged(uris:string[], albumUri: string): Promise<Record<string, boolean>> {
    const result: Record<string, boolean> = {};
    uris.forEach(item => {
      result[item] = false;
    })
    let fetchResult: photoAccessHelper.FetchResult<PhotoAsset> | undefined = undefined;
    try {
      const album = await this.userFileManagerAccess.getAlbumByUri(albumUri);
      if (!album) {
        return result;
      }
      let assets: PhotoAsset[] = [];
      let predicates = new dataSharePredicates.DataSharePredicates();
      predicates.beginWrap();
      for (let i = 0; i < uris.length; i++) {
        predicates.equalTo(photoAccessHelper.PhotoKeys.URI.toString(), uris[i]);
        if (i < uris.length - 1) {
          predicates.or();
        }
      }
      predicates.endWrap();
      let fetchOpt: photoAccessHelper.FetchOptions = {
        predicates: predicates,
        fetchColumns: [],
      };
      fetchResult = await album.getAssets(fetchOpt);
      assets = await fetchResult.getAllObjects();
      uris.forEach(uri => {
        result[uri] = assets.find(item => item.uri === uri) ? false : true;
      });
      return result;
    } catch (error) {
      Log.error(TAG, `checkIsAlbumChanged error: ${JSON.stringify(error)}`);
      return result;
    } finally {
      fetchResult?.close();
      Log.info(TAG, `checkIsAlbumChanged fetchResult is close`)
    }
  }

  private async updateImage(reminderService: ReminderService, imageProxyDataService: ImageProxyDataService,
    updateItems: updateItemI[]) : Promise<void> {
    try {
      const changeAlbumUris: Record<string, Set<string>> = {};
      for (let i = 0; i < updateItems.length; i++) {
        const item = updateItems[i];
        if (!item.isAlbumChanged) {
          await imageProxyDataService.updateImageBlobByUri(item.imageUri);
          // 图片被编辑并覆盖原图时，即便所属相册未发生变化，也需要刷新对应卡片，
          // 否则卡片仍然展示更新前的缩略图。
          this.needRefreshForms.add(item.formId);
        } else {
          if (!changeAlbumUris[item.formId]) {
            changeAlbumUris[item.formId] = new Set();
          }
          changeAlbumUris[item.formId].add(item.imageUri);
        }
      }
      const formIds = Object.keys(changeAlbumUris);
      for (let i = 0; i < formIds.length; i++) {
        const formId = formIds[i];

        const lastCarouseImageInfo: ImageInfo | undefined = await reminderService.queryLastImageInfo(formId, true);
        if (lastCarouseImageInfo && changeAlbumUris[formId].has(lastCarouseImageInfo.imageUri)) {
          this.needRefreshForms.add(formId);
        }

        await reminderService.hiddenRecordByImageUris(Array.from(changeAlbumUris[formId]), formId);
      }
    } catch (error) {
      Log.error(TAG, `updateImage error ${error}`);
    }
  }

  private async handleAddImage(uris: string[]): Promise<void> {
    Log.info(TAG, `handleAddImage uris: ${JSON.stringify(uris)}`);
  }

  private async handleDelete(uris: string[]): Promise<void> {
    Log.info(TAG, `handleDeleteImage uris: ${JSON.stringify(uris)}`);
  }
}