// Ordinary public API caller. A return value is never independent media proof.
import media from '@ohos.multimedia.media';
import window from '@ohos.window';
import fs from '@ohos.file.fs';
import common from '@ohos.app.ability.common';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import systemDateTime from '@ohos.systemDateTime';
import process from '@ohos.process';
import util from '@ohos.util';
import { BusinessError } from '@ohos.base';

interface Entry578 {
  run_id: string;
  scenario: string;
  seq: number;
  uid: number;
  pid: number;
  active_ms: number;
  event: string;
  cycle: number;
  detail: string;
}

@Entry
@Component
struct Index {
  @State note: string = 'Public screen capture and transcoding: independent verification pending';
  private readonly runId: string = '__MEDIA578_RUN__';
  private readonly scenario: string = '__MEDIA578_SCENARIO__';
  private readonly palette: number[][] = __MEDIA578_PALETTE__;
  private context: common.UIAbilityContext | undefined = undefined;
  private mainWindow: window.Window | undefined = undefined;
  private journal: fs.File | undefined = undefined;
  private capture: media.AVScreenCaptureRecorder | undefined = undefined;
  private transcoder: media.AVTranscoder | undefined = undefined;
  private destination: fs.File | undefined = undefined;
  private source: fs.File | undefined = undefined;
  private sequence: number = 0;
  private cycle: number = 0;
  private captureState: number = -1;
  private complete: boolean = false;
  private asyncError: number = 0;
  private phase: number = 0;
  private tick: number = 0;
  private canvasWidth: number = 0;
  private canvasHeight: number = 0;
  private timer: number = -1;
  private ready: boolean = false;
  private continued: boolean = false;
  private setting: RenderingContextSettings = new RenderingContextSettings(false);
  private canvas: CanvasRenderingContext2D = new CanvasRenderingContext2D(this.setting);

  private record(event: string, detail: string = '', generation: number = this.cycle): void {
    if (this.journal === undefined) { throw new Error('Journal is not open'); }
    const row: Entry578 = { run_id: this.runId, scenario: this.scenario, seq: this.sequence++,
      uid: process.uid, pid: process.pid, active_ms: systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE),
      event: event, cycle: generation, detail: detail };
    const bytes = new util.TextEncoder().encodeInto(JSON.stringify(row) + '\n');
    if (fs.writeSync(this.journal.fd, bytes.buffer as ArrayBuffer) !== bytes.byteLength) {
      throw new Error('Short journal write');
    }
    fs.fsyncSync(this.journal.fd);
  }

  private async delay(ms: number): Promise<void> {
    await new Promise<void>((resolve: () => void) => { setTimeout(resolve, ms); });
  }

  private path(kind: string): string {
    if (this.context === undefined) { throw new Error('No UIAbility context'); }
    return this.context.getApplicationContext().filesDir + '/media578-' + this.runId + '-' +
      this.cycle.toString() + '-' + kind;
  }

  private openFresh(kind: string): fs.File {
    const path = this.path(kind);
    if (fs.accessSync(path)) { throw new Error('Existing run evidence is preserved'); }
    const result = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.READ_WRITE);
    this.record('file.open', kind);
    return result;
  }

  private closeFiles(): void {
    if (this.source !== undefined) {
      fs.closeSync(this.source); this.source = undefined; this.record('file.close', 'source');
    }
    if (this.destination !== undefined) {
      fs.fsyncSync(this.destination.fd);
      fs.closeSync(this.destination); this.destination = undefined; this.record('file.close', 'destination');
    }
  }

  private draw(): void {
    if (!this.ready || this.canvasWidth <= 0 || this.canvasHeight <= 0) { return; }
    const values: number[] = this.palette[Math.max(0, this.cycle - 1) * 4 + this.phase];
    for (let index = 0; index < 64; index++) {
      const value: number = index < 56 ? values[index] : ((this.tick >> (index - 56)) & 1) === 0 ? 32 : 224;
      this.canvas.fillStyle = 'rgb(' + value + ',' + value + ',' + value + ')';
      const x = index % 8; const y = Math.floor(index / 8);
      this.canvas.fillRect(x * this.canvasWidth / 8, y * this.canvasHeight / 8,
        this.canvasWidth / 8 + 1, this.canvasHeight / 8 + 1);
    }
    this.tick = (this.tick + 1) % 256;
  }

  private changePhase(value: number): void {
    this.phase = value; this.draw(); this.record('canvas.phase', value.toString());
  }

  private async waitCapture(state: number): Promise<void> {
    const deadline: number = systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) + 30000;
    while (this.captureState !== state) {
      if (this.asyncError !== 0) { throw new Error('Capture asynchronous error ' + this.asyncError); }
      if (systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) > deadline) {
        throw new Error('Missing actual screen state ' + state);
      }
      await this.delay(40);
    }
  }

  private async createCapture(): Promise<void> {
    if (this.capture !== undefined || this.destination !== undefined) { throw new Error('Previous capture still owned'); }
    this.captureState = -1; this.asyncError = 0;
    this.capture = await media.createAVScreenCaptureRecorder(); this.record('screen.create');
    const instance: media.AVScreenCaptureRecorder = this.capture;
    const generation: number = this.cycle;
    this.capture.on('stateChange', (state: media.AVScreenCaptureStateCode) => {
      if (this.capture === instance) { this.captureState = state; }
      this.record('screen.state', state.toString(), generation);
    });
    this.capture.on('error', (error: BusinessError) => {
      if (this.capture === instance) { this.asyncError = error.code; }
      this.record('screen.error', JSON.stringify({ code: error.code, message: error.message }), generation);
    });
    this.destination = this.openFresh('capture.mp4');
    const config: media.AVScreenCaptureRecordConfig = {
      fd: this.destination.fd, frameWidth: 640, frameHeight: 480, videoBitrate: 2000000,
      audioSampleRate: 48000, audioChannelCount: 2, audioBitrate: 192000,
      preset: media.AVScreenCaptureRecordPreset.SCREEN_RECORD_PRESET_H264_AAC_MP4,
      fillMode: media.AVScreenCaptureFillMode.SCALE_TO_FILL,
      strategy: { privacyMaskMode: 0 }
    };
    await this.capture.init(config); this.record('screen.init', '640x480,H264,AAC,48000,2');
    await this.capture.setMicEnabled(true); this.record('screen.mic', 'true');
  }

  private async releaseCapture(): Promise<void> {
    if (this.capture !== undefined) {
      // Do not close the output FD before the service releases it.
      await this.capture.release(); this.record('screen.release');
      this.capture = undefined;
    }
    this.closeFiles();
  }

  private async recordScreen(): Promise<void> {
    await this.createCapture();
    if (this.capture === undefined || this.mainWindow === undefined) { throw new Error('Capture/window absent'); }
    this.changePhase(0); this.record('screen.start.request');
    try {
      await this.capture.startRecording(); this.record('screen.start.return');
    } catch (error) {
      const failure = error as BusinessError;
      this.record('screen.start.reject', JSON.stringify({ code: failure.code, message: failure.message }));
      if (this.scenario !== 'screen-deny') {
        throw new Error('Screen capture start rejected: ' + failure.code + ': ' + failure.message);
      }
    }
    if (this.scenario === 'screen-deny') {
      // A promise rejection alone does not prove consent denial.
      await this.waitCapture(media.AVScreenCaptureStateCode.SCREENCAPTURE_STATE_CANCELED);
      await this.releaseCapture(); return;
    }
    await this.waitCapture(media.AVScreenCaptureStateCode.SCREENCAPTURE_STATE_STARTED);
    this.record('screen.running');
    if (this.scenario === 'screen-death') {
      await this.delay(1200); this.record('owner.await-death', 'screen');
      // Only the existing Owner may terminate this ordinary application. Never
      // manufacture a death callback or stop the global media service here.
      await this.delay(30000); throw new Error('Owned death action did not arrive');
    }
    if (this.scenario === 'screen-revoke') {
      this.record('owner.await-revoke', 'system screen-recording stop control');
      await this.waitCapture(media.AVScreenCaptureStateCode.SCREENCAPTURE_STATE_STOPPED_BY_USER);
      this.record('screen.revoked'); this.changePhase(3);
      await this.delay(1200); // fresh forbidden pixels while authorization is gone
      await this.releaseCapture(); return;
    }
    this.continued = false; this.record('owner.await-continue');
    const continueDeadline: number = systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) + 20000;
    while (!this.continued) {
      if (systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) > continueDeadline) { throw new Error('Owner UI continue timed out'); }
      await this.delay(40);
    }
    this.record('owner.continued'); await this.delay(1200);
    await this.mainWindow.setWindowPrivacyMode(true); this.record('window.privacy', 'true');
    await this.delay(200); this.changePhase(1); await this.delay(1800);
    // Replace the secret while still protected, then allow compositor commit.
    this.changePhase(2); await this.delay(200);
    await this.mainWindow.setWindowPrivacyMode(false); this.record('window.privacy', 'false');
    await this.delay(1400);
    this.record('screen.stop.request'); await this.capture.stopRecording(); this.record('screen.stop.return');
    await this.releaseCapture();
    this.changePhase(3); await this.delay(400);
  }

  private async convert(): Promise<void> {
    if (this.transcoder !== undefined || this.destination !== undefined || this.source !== undefined) {
      throw new Error('Previous conversion still owned');
    }
    this.complete = false; this.asyncError = 0;
    this.transcoder = await media.createAVTranscoder(); this.record('transcode.create');
    const instance: media.AVTranscoder = this.transcoder;
    const generation: number = this.cycle;
    this.transcoder.on('complete', () => {
      if (this.transcoder === instance) { this.complete = true; }
      this.record('transcode.complete', '', generation);
    });
    this.transcoder.on('error', (error: BusinessError) => {
      if (this.transcoder === instance) { this.asyncError = error.code; }
      this.record('transcode.error', JSON.stringify({ code: error.code, message: error.message }), generation);
    });
    this.transcoder.on('progressUpdate', (value: number) => { this.record('transcode.progress', value.toString(), generation); });
    const input: string = this.path('capture.mp4');
    const size: number = fs.statSync(input).size;
    if (size <= 0 || size > 16777216) { throw new Error('Actual capture input size is invalid'); }
    this.source = fs.openSync(input, fs.OpenMode.READ_ONLY);
    this.destination = this.openFresh('transcoded.mp4');
    this.transcoder.fdSrc = { fd: this.source.fd, offset: 0, length: size };
    this.transcoder.fdDst = this.destination.fd; this.record('transcode.fds', size.toString());
    const config: media.AVTranscoderConfig = { fileFormat: media.ContainerFormatType.CFT_MPEG_4,
      audioCodec: media.CodecMimeType.AUDIO_AAC, audioBitrate: 128000,
      videoCodec: media.CodecMimeType.VIDEO_AVC, videoBitrate: 700000,
      videoFrameWidth: 320, videoFrameHeight: 240, enableBFrame: false };
    await this.transcoder.prepare(config); this.record('transcode.prepare', '320x240,H264,AAC');
    this.record('transcode.start.request'); await this.transcoder.start(); this.record('transcode.start');
    if (this.scenario === 'transcode-cancel' || this.scenario === 'transcode-death') {
      // Failure or already-complete is a real race/failure, never a cancel pass.
      await this.transcoder.pause(); this.record('transcode.pause');
      if (this.complete) { throw new Error('Conversion completed before controlled boundary'); }
      if (this.scenario === 'transcode-death') {
        this.record('owner.await-death', 'transcode');
        await this.delay(30000); throw new Error('Owned death action did not arrive');
      }
      await this.transcoder.cancel(); this.record('transcode.cancel');
      await this.delay(600);
      if (this.complete) { throw new Error('Canceled transcoder emitted completion'); }
    } else {
      const deadline: number = systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) + 30000;
      while (!this.complete) {
        if (this.asyncError !== 0) { throw new Error('Actual transcoder error ' + this.asyncError); }
        if (systemDateTime.getUptime(systemDateTime.TimeType.ACTIVE) > deadline) { throw new Error('Transcoder timed out'); }
        await this.delay(40);
      }
    }
    await this.transcoder.release(); this.record('transcode.release'); this.transcoder = undefined;
    this.closeFiles();
  }

  private async cleanup(): Promise<void> {
    const failures: string[] = [];
    if (this.mainWindow !== undefined) {
      try { await this.mainWindow.setWindowPrivacyMode(false); this.record('cleanup.privacy'); }
      catch (error) { failures.push('privacy:' + JSON.stringify(error)); }
    }
    if (this.transcoder !== undefined) {
      try { await this.transcoder.release(); this.record('cleanup.transcode'); this.transcoder = undefined; }
      catch (error) { failures.push('transcode:' + JSON.stringify(error)); }
    }
    if (this.capture !== undefined) {
      try { await this.capture.release(); this.record('cleanup.screen'); this.capture = undefined; }
      catch (error) { failures.push('screen:' + JSON.stringify(error)); }
    }
    // Keep FDs alive if release failed: the original Owner retains the failed
    // app/evidence and performs controlled cleanup. Do not claim local cleanup.
    if (this.transcoder === undefined && this.capture === undefined) {
      try { this.closeFiles(); } catch (error) { failures.push('files:' + JSON.stringify(error)); }
    }
    if (this.timer >= 0) { clearInterval(this.timer); this.timer = -1; }
    this.record('cleanup.end', JSON.stringify(failures));
    if (failures.length !== 0) { throw new Error('Actual caller cleanup failed'); }
  }

  async aboutToAppear(): Promise<void> {
    if (this.journal !== undefined) { return; }
    this.context = getContext(this) as common.UIAbilityContext;
    const path: string = this.context.getApplicationContext().filesDir + '/media578-' + this.runId + '-results.log';
    if (fs.accessSync(path)) { this.note = 'Existing journal preserved'; return; }
    this.journal = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
    this.record('identity');
    let failed: boolean = false;
    try {
      this.mainWindow = await window.getLastWindow(this.context);
      this.record('window.id', this.mainWindow.getWindowProperties().id.toString());
      const authorization = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(
        this.context, ['ohos.permission.MICROPHONE']);
      this.record('microphone.authorization', JSON.stringify({ permissions: authorization.permissions,
        auth_results: authorization.authResults, dialog_shown_results: authorization.dialogShownResults }));
      while (!this.ready) { await this.delay(40); }
      this.timer = setInterval(() => { this.draw(); }, 100);
      const cycles: number = this.scenario === 'screen-transcode' ? 2 : 1;
      for (this.cycle = 1; this.cycle <= cycles; this.cycle++) {
        await this.recordScreen();
        if (this.scenario === 'screen-transcode' || this.scenario === 'transcode-cancel' ||
            this.scenario === 'transcode-death') { await this.convert(); }
      }
    } catch (error) {
      failed = true; this.record('failure', JSON.stringify(error));
    } finally {
      try { await this.cleanup(); } catch (error) { failed = true; }
      this.record('summary', JSON.stringify({ caller_completed: !failed, independent_decode_required: true }));
      this.note = failed ? 'Actual public API case failed; evidence retained' : 'Caller complete; independent decode required';
      fs.closeSync(this.journal); this.journal = undefined;
    }
  }

  build() {
    Column() {
      Canvas(this.canvas).id('media578-canvas').width('100%').height('80%')
        .onReady(() => { this.ready = true; this.draw(); })
        .onAreaChange((_old: Area, area: Area) => {
          this.canvasWidth = Number(area.width); this.canvasHeight = Number(area.height); this.draw();
        })
      Text(this.note).fontSize(14).width('100%').height('10%')
      Button('Continue media audit').id('media578-continue').height('10%')
        .onClick(() => { this.continued = true; })
    }.width('100%').height('100%').backgroundColor(Color.White)
  }
}
