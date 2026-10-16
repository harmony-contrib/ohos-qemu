/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import fs from '@ohos.file.fs';
import image from '@ohos.multimedia.image';
import wallpaper from '@ohos.wallpaper';
import { BusinessError } from '@ohos.base';
import { SystemParamUtil } from '@ohos/settings.common/src/main/ets/utils/SystemParamUtil';
import { LogUtil } from '@ohos/settings.common/src/main/ets/utils/LogUtil';

export enum WallpaperSelectionPhase {
  IDLE, SELECTING, PREVIEW, APPLYING, SAVED, RESTORING, RESTORED, CANCELLED, ERROR
}

export interface WallpaperSelectionState {
  phase: WallpaperSelectionPhase;
  busy: boolean;
  preview?: image.PixelMap;
  errorCode: number;
  errorMessage: string;
}

class WallpaperSettingsError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

const TAG: string = 'WallpaperSelection';
const MAX_FILE_BYTES: number = 32 * 1024 * 1024;
const MAX_PIXELS: number = 16 * 1024 * 1024;
const MAX_DIMENSION: number = 8192;

// This controller consumes only the real picker result. It never requests broad
// media access, grants a permission, accepts an arbitrary caller-supplied path,
// or treats a service return value as evidence of rendered pixels.
export class WallpaperSelectionController {
  private session: number = 0;
  private active: boolean = false;
  private closed: boolean = false;
  private committing: boolean = false;
  private preview?: image.PixelMap;
  private phase: WallpaperSelectionPhase = WallpaperSelectionPhase.IDLE;
  private errorCode: number = 0;
  private errorMessage: string = '';
  private readonly observer: (state: WallpaperSelectionState) => void;

  constructor(observer: (state: WallpaperSelectionState) => void) {
    this.observer = observer;
  }

  isCommitting(): boolean { return this.committing; }

  private publish(): void {
    if (!this.closed) {
      this.observer({ phase: this.phase, busy: this.active, preview: this.preview,
        errorCode: this.errorCode, errorMessage: this.errorMessage });
    }
  }

  private fail(error: BusinessError): void {
    this.errorCode = typeof error.code === 'number' ? error.code : 0;
    this.errorMessage = error.message || 'Wallpaper operation failed';
    this.phase = WallpaperSelectionPhase.ERROR;
    LogUtil.error(`${TAG}: code=${this.errorCode}, message=${this.errorMessage}`);
  }

  private current(session: number): boolean { return !this.closed && this.session === session; }

  private async allowed(): Promise<void> {
    if (await SystemParamUtil.isModifyWallpaperDisable()) {
      throw new WallpaperSettingsError(0, 'Wallpaper modification is disabled by your organization');
    }
  }

  private async releasePreview(): Promise<void> {
    const pixel = this.preview;
    this.preview = undefined;
    this.publish();
    if (pixel !== undefined) {
      await pixel.release();
    }
  }

  private async decode(uri: string): Promise<image.PixelMap> {
    let file: fs.File | undefined = undefined;
    let source: image.ImageSource | undefined = undefined;
    let pixel: image.PixelMap | undefined = undefined;
    let failure: BusinessError | undefined = undefined;
    try {
      // The Photos picker grants read access to the selected URI. Keep it in
      // this process: pass decoded pixels, not a private URI, to WallpaperService.
      file = await fs.open(uri, fs.OpenMode.READ_ONLY);
      const stat = await fs.stat(file.fd);
      if (!stat.isFile() || stat.size <= 0 || stat.size > MAX_FILE_BYTES) {
        throw new WallpaperSettingsError(0, 'Selected image exceeds the supported file limit');
      }
      source = image.createImageSource(file.fd);
      const info = await source.getImageInfo();
      const width = info.size.width;
      const height = info.size.height;
      if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0 ||
        width > MAX_DIMENSION || height > MAX_DIMENSION || width > MAX_PIXELS / height) {
        throw new WallpaperSettingsError(0, 'Selected image exceeds the supported pixel limit');
      }
      pixel = await source.createPixelMap();
    } catch (error) {
      failure = error as BusinessError;
    }
    // Try both cleanup actions even if either fails. A failed decoder must not
    // retain an FD; cleanup failure must not silently publish a usable preview.
    if (source !== undefined) {
      try { await source.release(); } catch (error) {
        if (failure === undefined) { failure = error as BusinessError; }
        else { LogUtil.error(`${TAG}: image source cleanup failed ${JSON.stringify(error)}`); }
      }
    }
    if (file !== undefined) {
      try { await fs.close(file); } catch (error) {
        if (failure === undefined) { failure = error as BusinessError; }
        else { LogUtil.error(`${TAG}: selected FD cleanup failed ${JSON.stringify(error)}`); }
      }
    }
    if (failure !== undefined || pixel === undefined) {
      if (pixel !== undefined) {
        try { await pixel.release(); } catch (error) {
          LogUtil.error(`${TAG}: failed decode pixel cleanup ${JSON.stringify(error)}`);
        }
      }
      throw new WallpaperSettingsError(failure?.code ?? 0, failure?.message ?? 'Image decoding returned no pixels');
    }
    return pixel;
  }

  async choose(): Promise<void> {
    if (this.closed || this.active) { return; }
    const session = ++this.session;
    this.active = true;
    this.phase = WallpaperSelectionPhase.SELECTING;
    this.errorCode = 0;
    this.errorMessage = '';
    this.publish();
    let decoded: image.PixelMap | undefined = undefined;
    try {
      await this.releasePreview();
      await this.allowed();
      if (!this.current(session)) { return; }
      const options = new photoAccessHelper.PhotoSelectOptions();
      options.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
      options.maxSelectNumber = 1;
      const picker = new photoAccessHelper.PhotoViewPicker();
      const result = await picker.select(options);
      if (!this.current(session)) { return; }
      if (result.photoUris.length === 0) {
        this.phase = WallpaperSelectionPhase.CANCELLED;
        return;
      }
      const uri = result.photoUris[0];
      if (result.photoUris.length !== 1 || uri.length === 0 || uri.length > 4096 || uri.indexOf('\u0000') >= 0) {
        throw new WallpaperSettingsError(0, 'Picker returned an invalid single-image selection');
      }
      decoded = await this.decode(uri);
      if (!this.current(session)) { return; }
      this.preview = decoded;
      decoded = undefined;
      this.phase = WallpaperSelectionPhase.PREVIEW;
    } catch (error) {
      if (this.current(session)) { this.fail(error as BusinessError); }
      else { LogUtil.error(`${TAG}: cancelled selection failed ${JSON.stringify(error)}`); }
    } finally {
      if (decoded !== undefined) {
        try { await decoded.release(); } catch (error) { this.fail(error as BusinessError); }
      }
      this.active = false;
      this.publish();
    }
  }

  async apply(type: wallpaper.WallpaperType): Promise<boolean> {
    if (this.closed || this.active || this.preview === undefined) { return false; }
    if (type !== wallpaper.WallpaperType.WALLPAPER_SYSTEM && type !== wallpaper.WallpaperType.WALLPAPER_LOCKSCREEN) {
      this.fail(new WallpaperSettingsError(401, 'Invalid wallpaper target'));
      this.publish();
      return false;
    }
    const session = this.session;
    this.active = true;
    this.phase = WallpaperSelectionPhase.APPLYING;
    this.publish();
    try {
      await this.allowed();
      if (!this.current(session) || this.preview === undefined) { return false; }
      // Once explicitly authorized Apply has entered the real service, the UI
      // blocks Back/Cancel. On forced destruction, retain pixels until it exits.
      this.committing = true;
      await wallpaper.setImage(this.preview, type);
      LogUtil.info(`${TAG}: service saved type=${type}; renderer pixels require independent verification`);
      if (!this.current(session)) { return false; }
      this.errorCode = 0;
      this.errorMessage = '';
      this.phase = WallpaperSelectionPhase.SAVED;
      return true;
    } catch (error) {
      this.fail(error as BusinessError);
      return false;
    } finally {
      this.committing = false;
      this.active = false;
      if (this.closed) {
        try { await this.releasePreview(); } catch (error) { this.fail(error as BusinessError); }
      }
      this.publish();
    }
  }

  async restore(type: wallpaper.WallpaperType): Promise<boolean> {
    if (this.closed || this.active) { return false; }
    if (type !== wallpaper.WallpaperType.WALLPAPER_SYSTEM && type !== wallpaper.WallpaperType.WALLPAPER_LOCKSCREEN) {
      this.fail(new WallpaperSettingsError(401, 'Invalid wallpaper target'));
      this.publish();
      return false;
    }
    const session = this.session;
    this.active = true;
    this.phase = WallpaperSelectionPhase.RESTORING;
    this.publish();
    try {
      await this.allowed();
      if (!this.current(session)) { return false; }
      this.committing = true;
      await wallpaper.restore(type);
      await this.releasePreview();
      if (!this.current(session)) { return false; }
      this.errorCode = 0;
      this.errorMessage = '';
      this.phase = WallpaperSelectionPhase.RESTORED;
      return true;
    } catch (error) {
      this.fail(error as BusinessError);
      return false;
    } finally {
      this.committing = false;
      this.active = false;
      if (this.closed) {
        try { await this.releasePreview(); } catch (error) { this.fail(error as BusinessError); }
      }
      this.publish();
    }
  }

  async cancel(): Promise<boolean> {
    if (this.closed || this.committing) { return false; }
    ++this.session;
    this.phase = WallpaperSelectionPhase.CANCELLED;
    try { await this.releasePreview(); } catch (error) {
      this.fail(error as BusinessError);
      this.publish();
      return false;
    }
    this.publish();
    return true;
  }

  async dispose(): Promise<void> {
    if (this.closed) { return; }
    this.closed = true;
    ++this.session;
    if (!this.committing) {
      try { await this.releasePreview(); } catch (error) { this.fail(error as BusinessError); }
    }
  }
}
