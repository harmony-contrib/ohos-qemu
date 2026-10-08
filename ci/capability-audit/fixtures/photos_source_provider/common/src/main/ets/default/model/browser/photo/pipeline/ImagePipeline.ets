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

import lazy { DecodeProcessor } from './DecodeProcessor';
import type { RequestProcessor } from './RequestProcessor';
import type { Thumbnail } from '../Thumbnail';
import type { ImageRequest } from './ImageRequest';
import lazy { RequestContext } from './RequestContext';
import type { RequestListener } from './RequestListener';
import lazy { AssetFetchProcessor } from './AssetFetchProcessor';
import type common from '@ohos.app.ability.common';
import lazy { VideoThumbnailWrapper } from './VideoThumbnailWrapper';
import lazy photoAccessHelper from '@ohos.file.photoAccessHelper';
import lazy { Log } from '../../../../utils/Log';
import lazy { TAG } from '@ohos/hypium/src/main/Constant';

/**
 * 大图解码流水线
 *
 * @since 2023-10-16
 */
export class ImagePipeline {
  private readonly imagePipeline: RequestProcessor<Thumbnail | undefined> | undefined = undefined;
  private readonly videoPipeline: RequestProcessor<Thumbnail> | undefined = undefined;

  private constructor() {
    let decodeProcessor: DecodeProcessor = new DecodeProcessor();
    let fileFetchProcessor: AssetFetchProcessor = new AssetFetchProcessor(decodeProcessor);
    this.imagePipeline = fileFetchProcessor;

    this.videoPipeline = new VideoThumbnailWrapper();
  }

  /**w
   * 获取单例实例
   *
   * @returns 单例实例
   */
  public static getInstance(): ImagePipeline {
    if (!ImagePipeline.instance) {
      ImagePipeline.instance = new ImagePipeline();
    }
    return ImagePipeline.instance;
  }

  public static instance: ImagePipeline | undefined = undefined;

  /**
   * 提交任务
   *
   * @param appCtx app上下文
   * @param request 请求
   * @param listeners 监听
   * @param params 参数
   * @returns context
   */
  public submit(appCtx: common.Context, request: ImageRequest, listeners?: RequestListener<Thumbnail>[],
    params?: Map<string, Object>): RequestContext<Thumbnail | undefined> | undefined {
    let context: RequestContext<Thumbnail | undefined> | undefined = this.create(appCtx, request, listeners, params);
    if (request?.item !== undefined) {
      let pipeline: RequestProcessor<Thumbnail | undefined> | undefined =
        request.item.mediaType === photoAccessHelper.PhotoType.IMAGE ? this.imagePipeline : this.videoPipeline;
      pipeline?.process(context);
    }

    return context;
  }

  /**
   * 只提交任务
   *
   * @param context 创建的RequestContext
   */
  public submitContext(context: RequestContext<Thumbnail | undefined> | undefined) {
    if (context && context.request && context.request.item) {
      let pipeline: RequestProcessor<Thumbnail | undefined> | undefined =
        context.request.item.mediaType === photoAccessHelper.PhotoType.IMAGE ? this.imagePipeline : this.videoPipeline;
      pipeline?.process(context);
    } else {
      Log.warn(TAG, `submitContext failed`);
    }
  }

  /**
   * 创建RequestContext
   *
   * @param appCtx app上下文
   * @param request 请求
   * @param listeners 监听
   * @param params 参数
   * @returns context
   */
  public create(appCtx: common.Context, request: ImageRequest, listeners?: RequestListener<Thumbnail>[],
    params?: Map<string, Object>, onDeCodeFinishCb?: Function): RequestContext<Thumbnail> | undefined {
    if (!request || !request.item) {
      return undefined;
    }

    let context: RequestContext<Thumbnail> = new RequestContext(appCtx, request, onDeCodeFinishCb);
    if (listeners) {
      for (let listener of listeners) {
        context.addListener(listener);
      }
    }

    if (params) {
      for (let key of params.keys()) {
        let value: Object | undefined = params.get(key);
        Log.info(TAG, `create ==== :${value}`);
        if (value === undefined) {
          continue;
        } else {
          context.params.set(key, value);
        }

      }
    }
    context.submitTime = new Date().getTime();
    return context;
  }
}