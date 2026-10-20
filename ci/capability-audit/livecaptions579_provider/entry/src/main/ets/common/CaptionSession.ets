import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import audio from '@ohos.multimedia.audio';
import accessibility from '@ohos.accessibility';
import display from '@ohos.display';
import window from '@ohos.window';
import worker, { ErrorEvent, MessageEvents } from '@ohos.worker';
import util from '@ohos.util';
import { CaptionInput, CaptionOutput, SAMPLE_RATE, MAX_BUFFERED_SAMPLES } from './CaptionProtocol';
import { CaptionActions } from './CaptionActions';
import { captionTrace } from './CaptionTrace';

// No public RPC exposes this class, the worker or its input. The only source of
// waveform input is the owned, user-authorized native AudioCapturer callback.
export class CaptionSession {
  readonly storage: LocalStorage = new LocalStorage({ session: '', text: '',
    status: '正在准备本地英语字幕', fontScale: 100, fontColor: '#FFFFFFFF', backgroundColor: '#EE000000' });
  private closed: boolean = false;
  private running: boolean = false;
  private capturer: audio.AudioCapturer | undefined = undefined;
  private model: worker.ThreadWorker | undefined = undefined;
  private overlay: window.Window | undefined = undefined;
  private captions: accessibility.CaptionsManager | undefined = undefined;
  private pendingReadyReject: ((reason: Error) => void) | undefined = undefined;
  private pendingAuthorityReject: ((reason: Error) => void) | undefined = undefined;
  private workerExit: Promise<number> | undefined = undefined;
  private workerExited: boolean = false;
  private exitCode: number = -1;
  private stopPromise: Promise<void> | undefined = undefined;
  private queued: Float32Array[] = [];
  private buffered: number = 0;
  private inFlight: number = 0;
  private sequence: number = 0;
  private captured: number = 0;
  private processed: number = 0;
  private segments: number = 0;
  private lines: string[] = [];
  private readonly onStyle = (style: accessibility.CaptionsStyle): void => {
    if (this.closed) { return; }
    this.storage.setOrCreate('fontScale', Math.max(1, Math.min(200, style.fontScale)));
    this.storage.setOrCreate('fontColor', style.fontColor);
    this.storage.setOrCreate('backgroundColor', style.backgroundColor);
  };
  private readonly onState = (state: audio.AudioState): void => {
    captionTrace(this.id, 'capture_state', this.sequence, this.captured, this.segments, state);
    if (!this.closed && this.running && state !== audio.AudioState.STATE_RUNNING) {
      this.deferFailure(new Error('native capture left running state'));
    }
  };
  private readonly onRead = (buffer: ArrayBuffer): void => {
    // Capturer APIs are never called inside this real-time read callback.
    if (this.closed || !this.running) { return; }
    if (buffer.byteLength <= 0 || buffer.byteLength % 2 !== 0) {
      this.deferFailure(new Error('native capture returned invalid S16LE bytes')); return;
    }
    const count: number = buffer.byteLength / 2;
    if (this.buffered + count > MAX_BUFFERED_SAMPLES) {
      this.deferFailure(new Error('local recognizer cannot keep up with real captured audio')); return;
    }
    const data: DataView = new DataView(buffer);
    const samples: Float32Array = new Float32Array(count);
    for (let index: number = 0; index < count; ++index) {
      samples[index] = data.getInt16(index * 2, true) / 32768;
    }
    this.queued.push(samples); this.buffered += count; this.captured += count;
    Promise.resolve().then((): void => { this.pump(); });
  };

  constructor(readonly id: string, private readonly context: common.ServiceExtensionContext,
    private readonly closeRequested: () => void, private readonly becameVisible: () => void,
    private readonly failed: (reason: Error) => void) {
    this.storage.setOrCreate('session', id);
  }
  private active(): void { if (this.closed) { throw new Error('caption session was cancelled'); } }
  private deferFailure(reason: Error): void {
    Promise.resolve().then((): void => { if (!this.closed) { this.failed(reason); } });
  }
  cancel(): void {
    if (this.closed) { return; }
    this.closed = true; this.running = false;
    CaptionActions.unregister(this.id);
    captionTrace(this.id, 'cancel', this.sequence, this.captured, this.segments);
    const reason: Error = new Error('caption session was cancelled');
    if (this.pendingReadyReject !== undefined) { this.pendingReadyReject(reason); this.pendingReadyReject = undefined; }
    if (this.pendingAuthorityReject !== undefined) { this.pendingAuthorityReject(reason); this.pendingAuthorityReject = undefined; }
  }
  async start(): Promise<void> {
    this.active();
    const noticeBytes: Uint8Array = await this.context.resourceManager.getRawFileContent('LIVE_CAPTIONS_NOTICES.txt');
    this.active();
    if (noticeBytes.byteLength < 100 || noticeBytes.byteLength > 2 * 1024 * 1024) { throw new Error('full admitted model/software notices are absent'); }
    this.storage.setOrCreate('notices', new util.TextDecoder('utf-8', { fatal: true }).decodeToString(noticeBytes));
    CaptionActions.register(this.id, (): void => { if (!this.closed) { this.closeRequested(); } });
    this.captions = accessibility.getCaptionsManager();
    this.onStyle(this.captions.style); this.captions.on('styleChange', this.onStyle);
    const screen: display.Display = display.getDefaultDisplaySync();
    const width: number = Math.min(screen.width - 24, 1000);
    const height: number = Math.min(260, Math.floor(screen.height / 3));
    if (width < 200 || height < 100) { throw new Error('default display cannot contain caption controls'); }
    const overlay = await window.createWindow({ name: 'LiveCaptions_' + this.id,
      windowType: window.WindowType.TYPE_FLOAT, ctx: this.context });
    this.overlay = overlay; this.active();
    await overlay.resize(width, height); this.active();
    await overlay.moveWindowTo(Math.floor((screen.width - width) / 2), screen.height - height - 16); this.active();
    await overlay.setWindowFocusable(false); this.active();
    await overlay.loadContent('pages/Captions', this.storage); this.active();
    await overlay.showWindow(); this.active();
    captionTrace(this.id, 'window_visible', 0, 0, 0);
    this.becameVisible(); this.active();
    await this.withDeadline(this.loadModel(), 180000, 'local model initialization deadline'); this.active();
    this.storage.setOrCreate('status', '请在系统授权窗口确认捕获播放音频');
    const capturer = await audio.createAudioCapturer({
      streamInfo: { samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000,
        channels: audio.AudioChannel.CHANNEL_1, sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW },
      capturerInfo: { source: audio.SourceType.SOURCE_TYPE_PLAYBACK_CAPTURE, capturerFlags: 0 },
      playbackCaptureMode: audio.AudioPlaybackCaptureMode.MODE_MEDIA | audio.AudioPlaybackCaptureMode.MODE_EXCLUDING_SELF });
    this.capturer = capturer; this.active();
    const format: audio.AudioStreamInfo = await capturer.getStreamInfo(); this.active();
    if (format.samplingRate !== SAMPLE_RATE || format.channels !== audio.AudioChannel.CHANNEL_1 ||
      format.sampleFormat !== audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE ||
      format.encodingType !== audio.AudioEncodingType.ENCODING_TYPE_RAW) {
      throw new Error('native capture negotiated incompatible audio format');
    }
    capturer.on('readData', this.onRead); capturer.on('stateChange', this.onState);
    captionTrace(this.id, 'capture_created', 0, 0, 0, await capturer.getAudioStreamId()); this.active();
    await this.requestAuthority(capturer); this.active();
    // Native requestPlaybackCaptureStart SUCCESS already calls AudioCapturer::Start.
    // Calling legacy .start() here would violate the modern capture contract.
    if (capturer.state !== audio.AudioState.STATE_RUNNING) { throw new Error('authorized stream is not actually running'); }
    this.running = true;
    this.storage.setOrCreate('status', '正在本地识别英语播放音频');
    captionTrace(this.id, 'capture_running', 0, 0, 0, capturer.state);
  }
  private requestAuthority(capturer: audio.AudioCapturer): Promise<void> {
    return new Promise<void>((resolve, reject): void => {
      this.pendingAuthorityReject = reject;
      try {
        captionTrace(this.id, 'authority_requested', 0, 0, 0);
        capturer.requestPlaybackCaptureStart((state: audio.PlaybackCaptureStartState): void => {
          // Always record the actual native status, even if cancellation won.
          captionTrace(this.id, 'authority_callback', this.sequence, this.captured, this.segments, state);
          this.pendingAuthorityReject = undefined;
          if (this.closed) { reject(new Error('cancelled before native authority callback')); return; }
          if (state === audio.PlaybackCaptureStartState.STATE_SUCCESS) { resolve(); }
          else { reject(new Error('native playback capture authorization/start status ' + state.toString())); }
        });
      } catch (error) { this.pendingAuthorityReject = undefined; reject(error as BusinessError); }
    });
  }
  private loadModel(): Promise<void> {
    return new Promise<void>((resolve, reject): void => {
      this.pendingReadyReject = reject;
      const model = new worker.ThreadWorker('entry/ets/workers/CaptionWorker.ets', { name: 'LiveCaptionsLocalASR' });
      this.model = model;
      this.workerExit = new Promise<number>((exited): void => {
        model.onexit = (code: number): void => {
          this.workerExited = true; this.exitCode = code; exited(code);
          captionTrace(this.id, 'worker_exit', this.sequence, this.captured, this.segments, code);
          if (this.pendingReadyReject !== undefined) { this.pendingReadyReject(new Error('native worker exited during model load')); }
          this.pendingReadyReject = undefined;
          if (!this.closed) { this.deferFailure(new Error('local recognizer worker exited')); }
        };
      });
      model.onerror = (event: ErrorEvent): void => {
        const reason: Error = new Error('local recognizer worker error: ' + event.message);
        if (this.pendingReadyReject !== undefined) { this.pendingReadyReject(reason); }
        this.pendingReadyReject = undefined; this.deferFailure(reason);
      };
      model.onmessageerror = (): void => { this.deferFailure(new Error('local recognizer message failed')); };
      model.onmessage = (event: MessageEvents): void => {
        const output = event.data as CaptionOutput;
        if (this.closed) { return; }
        if (output.session !== this.id || !Number.isInteger(output.sequence) ||
          !Number.isInteger(output.samples) || output.samples < this.processed || output.samples > this.captured ||
          !Number.isInteger(output.segments) || output.segments < this.segments) {
          this.deferFailure(new Error('local worker session/counter mismatch')); return;
        }
        if (output.kind === 'ready') {
          if (output.sequence !== 0 || this.sequence !== 0 || this.pendingReadyReject === undefined) {
            this.deferFailure(new Error('unexpected model-ready event')); return;
          }
          this.pendingReadyReject = undefined;
          captionTrace(this.id, 'model_ready', 0, 0, 0); resolve();
        } else if (output.kind === 'error') {
          const reason: Error = new Error(output.message);
          if (this.pendingReadyReject !== undefined) { this.pendingReadyReject(reason); }
          this.pendingReadyReject = undefined; this.deferFailure(reason);
        } else if ((output.kind === 'result' || output.kind === 'ack') && output.sequence === this.sequence && this.inFlight > 0) {
          this.processed = output.samples; this.segments = output.segments;
          if (output.kind === 'result') {
            if (typeof output.text !== 'string' || output.text.length === 0) { this.deferFailure(new Error('empty native result')); return; }
            // Keep a bounded visible transcript. It is never journalled or sent remotely.
            this.lines.push(output.text); if (this.lines.length > 12) { this.lines.shift(); }
            this.storage.setOrCreate('text', this.lines.join('\n'));
            captionTrace(this.id, 'caption_rendered', this.sequence, this.processed, this.segments);
          } else {
            this.buffered -= this.inFlight; this.inFlight = 0;
            captionTrace(this.id, 'pcm_ack', this.sequence, this.processed, this.segments); this.pump();
          }
        } else { this.deferFailure(new Error('unexpected recognizer event order')); }
      };
      const input: CaptionInput = { kind: 'init', session: this.id, sequence: 0, context: this.context };
      model.postMessage(input);
    });
  }
  private withDeadline<T>(operation: Promise<T>, milliseconds: number, message: string): Promise<T> {
    // A deadline reports failure; it never manufactures worker completion.
    return new Promise<T>((resolve, reject): void => {
      const timer: number = setTimeout((): void => { reject(new Error(message)); }, milliseconds);
      operation.then((value: T): void => { clearTimeout(timer); resolve(value); },
        (reason: Error): void => { clearTimeout(timer); reject(reason); });
    });
  }
  private pump(): void {
    if (this.closed || !this.running || this.model === undefined || this.inFlight !== 0 || this.queued.length === 0) { return; }
    const samples = this.queued.shift();
    if (samples === undefined) { return; }
    this.inFlight = samples.length; ++this.sequence;
    const input: CaptionInput = { kind: 'pcm', session: this.id, sequence: this.sequence, samples };
    this.model.postMessage(input);
  }
  stop(): Promise<void> {
    this.cancel();
    if (this.stopPromise === undefined) { this.stopPromise = this.release(); }
    return this.stopPromise;
  }
  private async release(): Promise<void> {
    const errors: Error[] = [];
    this.queued = []; this.buffered = 0;
    const capturer = this.capturer; this.capturer = undefined;
    if (capturer !== undefined) {
      try { capturer.off('readData', this.onRead); } catch (error) { errors.push(error as Error); }
      try { capturer.off('stateChange', this.onState); } catch (error) { errors.push(error as Error); }
      if (capturer.state === audio.AudioState.STATE_RUNNING || capturer.state === audio.AudioState.STATE_PAUSED) {
        try { await capturer.stop(); captionTrace(this.id, 'capture_stopped', this.sequence, this.captured, this.segments, capturer.state); }
        catch (error) { errors.push(error as Error); }
      }
      try { await capturer.release(); captionTrace(this.id, 'capture_released', this.sequence, this.captured, this.segments, capturer.state); }
      catch (error) { errors.push(error as Error); }
    }
    const model = this.model; this.model = undefined;
    if (model !== undefined) {
      try {
        if (!this.workerExited) { model.terminate(); }
        const exit = this.workerExit;
        if (exit === undefined) { throw new Error('worker lacks actual exit observer'); }
        const code: number = await this.withDeadline(exit, 15000, 'actual worker exit deadline');
        if (code !== 0) { throw new Error('actual recognizer worker exited abnormally ' + code.toString()); }
      } catch (error) { errors.push(error as Error); }
    }
    if (this.captions !== undefined) {
      try { this.captions.off('styleChange', this.onStyle); } catch (error) { errors.push(error as Error); }
      this.captions = undefined;
    }
    const overlay = this.overlay; this.overlay = undefined;
    if (overlay !== undefined) {
      try { await overlay.destroyWindow(); captionTrace(this.id, 'window_destroyed', this.sequence, this.captured, this.segments); }
      catch (error) { errors.push(error as Error); }
    }
    if (errors.length > 0) {
      captionTrace(this.id, 'cleanup_error', this.sequence, this.captured, this.segments,
        (errors[0] as BusinessError).code || -1);
      throw errors[0];
    }
    captionTrace(this.id, 'resources_released', this.sequence, this.captured, this.segments, this.exitCode);
  }
}
