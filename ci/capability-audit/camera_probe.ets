import camera from '@ohos.multimedia.camera';
import image from '@ohos.multimedia.image';
import fs from '@ohos.file.fs';
import abilityAccessCtrl, { PermissionRequestResult } from '@ohos.abilityAccessCtrl';
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';
import nativeProbe from 'libcamerapublicprobe.so';

interface CameraRecord {
  run_id: string;
  kind: string;
  name: string;
  cycle: number;
  pass: boolean;
  value: number;
  detail: string;
}
interface NativeComplete {
  run_id: string;
  kind: string;
  exit_code: number;
  failures: number;
}

@Entry
@Component
struct Index {
  @State note: string = 'Preparing ordinary Camera permission';
  private readonly runId: string = '__CAMERA_RUN_ID__';
  private readonly controller: XComponentController = new XComponentController();
  private context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;
  private file: fs.File | undefined = undefined;
  private busy: boolean = false;
  private checks: number = 0;
  private failures: number = 0;

  private record(name: string, cycle: number, pass: boolean, value: number = 0, detail: string = ''): void {
    this.checks++;
    if (!pass) this.failures++;
    const row: CameraRecord = { run_id: this.runId, kind: 'arkts_case', name: name, cycle: cycle,
      pass: pass, value: value, detail: detail };
    if (this.file) fs.writeSync(this.file.fd, JSON.stringify(row) + '\n');
    if (!pass) throw new Error(name + ':' + value.toString() + ':' + detail);
  }
  private async pause(milliseconds: number): Promise<void> {
    await new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
  }
  private async waitNative(): Promise<void> {
    const path: string = this.context.filesDir + '/camera-native-' + this.runId + '-results.log';
    for (let attempt: number = 0; attempt < 240; attempt++) {
      await this.pause(250);
      if (!fs.accessSync(path)) continue;
      const text: string = fs.readTextSync(path);
      if (!text.endsWith('\n')) continue;
      const lines: string[] = text.trim().split('\n');
      if (lines.length === 0) continue;
      const last: NativeComplete = JSON.parse(lines[lines.length - 1]) as NativeComplete;
      if (last.kind === 'native_complete') {
        this.record('native_complete', 0, last.run_id === this.runId && last.exit_code === 0 && last.failures === 0);
        return;
      }
    }
    this.record('native_timeout', 0, false);
  }

  private profile(profiles: camera.Profile[], format: camera.CameraFormat): camera.Profile {
    let selected: camera.Profile | undefined = undefined;
    profiles.forEach((profile: camera.Profile): void => {
      if (profile.format === format && profile.size.width >= 160 && profile.size.width <= 1280 &&
          profile.size.height >= 120 && profile.size.height <= 720 &&
          (!selected || profile.size.width < selected.size.width)) selected = profile;
    });
    if (!selected) throw new Error('Required real capture profile not advertised: format=' +
      format.toString() + ', profiles=' + JSON.stringify(profiles));
    return selected;
  }

  private checkEffectSuggestionRecord(): void {
    const first: camera.EffectSuggestionStatus = new camera.EffectSuggestionStatus();
    const second: camera.EffectSuggestionStatus = new camera.EffectSuggestionStatus();
    this.record('effect_record_constructor', 0, first instanceof camera.EffectSuggestionStatus &&
      second instanceof camera.EffectSuggestionStatus && first !== second);
    this.record('effect_record_unset_fields', 0, first.type === undefined && first.status === undefined &&
      second.type === undefined && second.status === undefined);
    first.type = camera.EffectSuggestionType.EFFECT_SUGGESTION_NONE;
    first.status = true;
    second.type = camera.EffectSuggestionType.EFFECT_SUGGESTION_PORTRAIT;
    second.status = false;
    this.record('effect_record_values', 0, first.type === camera.EffectSuggestionType.EFFECT_SUGGESTION_NONE &&
      first.status === true && second.type === camera.EffectSuggestionType.EFFECT_SUGGESTION_PORTRAIT &&
      second.status === false);
    first.type = camera.EffectSuggestionType.EFFECT_SUGGESTION_PORTRAIT;
    first.status = false;
    second.status = true;
    this.record('effect_record_isolation', 0, first.status === false && second.status === true &&
      first.type === camera.EffectSuggestionType.EFFECT_SUGGESTION_PORTRAIT);
  }

  private async checkPhoto(photo: camera.Photo, cycle: number, index: number,
                           previousTimestamp: number): Promise<number> {
    let source: image.ImageSource | undefined = undefined;
    let pixels: image.PixelMap | undefined = undefined;
    try {
      const timestamp: number = photo.main.timestamp;
      this.record('photo_timestamp_' + index.toString(), cycle, timestamp > previousTimestamp, timestamp);
      const component: image.Component = await photo.main.getComponent(image.ComponentType.JPEG);
      const bytes: Uint8Array = new Uint8Array(component.byteBuffer);
      this.record('photo_JPEG_' + index.toString(), cycle,
        bytes.length >= 128 && bytes.length <= 16 * 1024 * 1024 && bytes[0] === 255 && bytes[1] === 216,
        bytes.length);
      const path: string = this.context.filesDir + '/camera-' + this.runId + '-c' + cycle.toString() + '-p' + index.toString() + '.jpg';
      if (!nativeProbe.createFile(path)) throw new Error('Existing/unsafe photo evidence path');
      const output: fs.File = fs.openSync(path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
      try { fs.writeSync(output.fd, component.byteBuffer); } finally { fs.closeSync(output); }
      source = image.createImageSource(component.byteBuffer);
      pixels = await source.createPixelMap({ desiredPixelFormat: image.PixelMapFormat.RGBA_8888 });
      const info: image.ImageInfo = await pixels.getImageInfo();
      this.record('photo_dimensions_' + index.toString(), cycle,
        info.size.width >= 160 && info.size.width <= 1280 && info.size.height >= 120 && info.size.height <= 720,
        info.size.width, info.size.height.toString());
      const data: ArrayBuffer = new ArrayBuffer(info.size.width * info.size.height * 4);
      await pixels.readPixelsToBuffer(data);
      const rgba: Uint8Array = new Uint8Array(data);
      let minimum: number = 255;
      let maximum: number = 0;
      const samples: number[] = [];
      const colors: Set<string> = new Set<string>();
      for (let bar: number = 0; bar < 8; bar++) {
        const x: number = Math.floor((bar * 2 + 1) * info.size.width / 16);
        const y: number = Math.floor(info.size.height / 2);
        const offset: number = (y * info.size.width + x) * 4;
        const r: number = rgba[offset], g: number = rgba[offset + 1], b: number = rgba[offset + 2];
        minimum = Math.min(minimum, r, g, b);
        maximum = Math.max(maximum, r, g, b);
        samples.push(r, g, b);
        colors.add(Math.floor(r / 32).toString() + ':' + Math.floor(g / 32).toString() + ':' + Math.floor(b / 32).toString());
      }
      this.record('photo_real_pixels_' + index.toString(), cycle, maximum - minimum >= 60 && colors.size >= 4,
        colors.size, JSON.stringify(samples));
      return timestamp;
    } finally {
      if (pixels) await pixels.release();
      if (source) source.release();
      await photo.release();
    }
  }

  private async cycle(cycle: number, surface: string): Promise<void> {
    const manager: camera.CameraManager = camera.getCameraManager(this.context);
    const devices: camera.CameraDevice[] = manager.getSupportedCameras();
    this.record('camera_enumeration', cycle, devices.length === 1, devices.length);
    const capability: camera.CameraOutputCapability = manager.getSupportedOutputCapability(devices[0], camera.SceneMode.NORMAL_PHOTO);
    const previewProfile: camera.Profile = this.profile(capability.previewProfiles, camera.CameraFormat.CAMERA_FORMAT_YUV_420_SP);
    const photoProfile: camera.Profile = this.profile(capability.photoProfiles, camera.CameraFormat.CAMERA_FORMAT_JPEG);
    this.record('real_profiles', cycle, true, previewProfile.size.width, photoProfile.size.width.toString());
    const input: camera.CameraInput = manager.createCameraInput(devices[0]);
    let opened: boolean = false;
    let session: camera.PhotoSession | undefined = undefined;
    let preview: camera.PreviewOutput | undefined = undefined;
    let output: camera.PhotoOutput | undefined = undefined;
    let running: boolean = false;
    let starts: number = 0, ends: number = 0, errors: number = 0;
    let photoResolve: ((photo: camera.Photo) => void) | undefined = undefined;
    let photoReject: ((error: Error) => void) | undefined = undefined;
    try {
      await input.open();
      opened = true;
      this.record('input_open', cycle, true);
      preview = manager.createPreviewOutput(previewProfile, surface);
      preview.on('frameStart', (error: BusinessError): void => { if (error) errors++; else starts++; });
      preview.on('frameEnd', (error: BusinessError): void => { if (error) errors++; else ends++; });
      preview.on('error', (): void => { errors++; });
      output = manager.createPhotoOutput(photoProfile);
      output.on('photoAvailable', (error: BusinessError, photo: camera.Photo): void => {
        if (error) {
          const reject = photoReject;
          photoResolve = undefined;
          photoReject = undefined;
          if (reject) reject(new Error(error.code.toString() + ':' + error.message));
        } else if (photoResolve) {
          const resolve = photoResolve;
          photoResolve = undefined;
          photoReject = undefined;
          resolve(photo);
        } else { photo.release(); }
      });
      session = manager.createSession(camera.SceneMode.NORMAL_PHOTO) as camera.PhotoSession;
      session.beginConfig();
      session.addInput(input);
      session.addOutput(preview);
      session.addOutput(output);
      await session.commitConfig();
      this.record('session_configured', cycle, true);
      await session.start();
      running = true;
      this.note = 'ArkTS preview live cycle ' + cycle.toString();
      this.record('preview_started', cycle, true);
      await this.pause(20000); // Stable live surface interval for host compositor screenshots.
      this.record('preview_frame_start', cycle, starts > 0 && errors === 0, starts);
      let timestamp: number = 0;
      for (let index: number = 1; index <= 2; index++) {
        const pending: Promise<camera.Photo> = new Promise<camera.Photo>((resolve, reject) => {
          photoResolve = resolve;
          photoReject = reject;
        });
        // Attach rejection handling before capture() itself can reject.
        const consumed: Promise<camera.Photo> = pending.then((photo: camera.Photo): camera.Photo => photo,
          (error: Error): never => { throw error; });
        let timer: number = -1;
        const deadline: Promise<camera.Photo> = new Promise<camera.Photo>((_, reject) => {
          timer = setTimeout(() => reject(new Error('Actual photo timeout')), 20000);
        });
        const result: Promise<camera.Photo> = Promise.race<camera.Photo>([consumed, deadline]);
        // A capture failure is already a failed test; drain any pending result
        // rejection rather than manufacturing an unrelated unhandled rejection.
        result.catch((): void => {});
        // Register consumption before capture; synchronous completion cannot be lost.
        try {
          this.record('capture_requested_' + index.toString(), cycle, true);
          await output.capture();
          this.record('capture_call_returned_' + index.toString(), cycle, true);
          const photo: camera.Photo = await result;
          timestamp = await this.checkPhoto(photo, cycle, index, timestamp);
        } finally { if (timer >= 0) clearTimeout(timer); }
      }
      await session.stop();
      running = false;
      await this.pause(1000);
      this.record('preview_frame_end', cycle, ends > 0 && errors === 0, ends);
    } finally {
      photoResolve = undefined;
      photoReject = undefined;
      if (running && session) await session.stop();
      if (preview) {
        preview.off('frameStart'); preview.off('frameEnd'); preview.off('error');
        await preview.release();
      }
      if (output) { output.off('photoAvailable'); await output.release(); }
      if (session) await session.release();
      if (opened) await input.close();
    }
    this.record('release_cycle', cycle, true);
  }

  private async run(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      const results: string = this.context.filesDir + '/camera-arkts-' + this.runId + '-results.log';
      if (!nativeProbe.createFile(results)) throw new Error('Existing/unsafe Camera evidence path');
      this.file = fs.openSync(results, fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
      this.checkEffectSuggestionRecord();
      const access: abilityAccessCtrl.AtManager = abilityAccessCtrl.createAtManager();
      const permission: PermissionRequestResult = await access.requestPermissionsFromUser(this.context, ['ohos.permission.CAMERA']);
      this.record('ordinary_user_permission', 0, permission.permissions.length === 1 &&
        permission.permissions[0] === 'ohos.permission.CAMERA' && permission.authResults.length === 1 && permission.authResults[0] === 0);
      const surface: string = this.controller.getXComponentSurfaceId();
      this.record('real_ArkUI_surface', 0, /^[0-9]+$/.test(surface) && surface !== '0');
      this.note = 'C++ public Camera lifecycle running';
      this.record('native_probe_started', 0, nativeProbe.run(this.runId, surface, this.context.filesDir));
      await this.waitNative();
      for (let cycle: number = 1; cycle <= 2; cycle++) await this.cycle(cycle, surface);
      this.note = 'Camera ordinary-app probe complete';
    } catch (error) {
      this.failures++;
      if (this.file) fs.writeSync(this.file.fd, JSON.stringify({ run_id: this.runId, kind: 'probe_error', detail: String(error) }) + '\n');
      this.note = 'Camera probe failed: ' + String(error);
    } finally {
      if (this.file) {
        fs.writeSync(this.file.fd, JSON.stringify({ run_id: this.runId, kind: 'arkts_complete',
          checks: this.checks, failures: this.failures, pass: this.failures === 0 }) + '\n');
        fs.closeSync(this.file);
      }
    }
  }
  build() {
    Column({ space: 8 }) {
      Text('QEMU public Camera audit').fontSize(20)
      XComponent({ id: 'camera-audit-preview', type: XComponentType.SURFACE, controller: this.controller })
        .id('camera-audit-preview')
        .width(320).height(180).backgroundColor(Color.Black)
        .onLoad(() => { this.run(); })
      Text(this.note).fontSize(14)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
