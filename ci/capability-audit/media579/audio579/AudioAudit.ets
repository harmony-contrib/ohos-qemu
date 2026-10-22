// Real public audio/media calls only. Observations never assert capability pass.
import audio from '@ohos.multimedia.audio';
import media from '@ohos.multimedia.media';
import voice from '@ohos.ai.intelligentVoice';
import fs from '@ohos.file.fs';
import process from '@ohos.process';
import util from '@ohos.util';
import systemDateTime from '@ohos.systemDateTime';
import common from '@ohos.app.ability.common';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { BusinessError } from '@ohos.base';
import midi from 'libaudio579midi.so';

interface Request { run: string; boot: string; operation: string; action: string; phrase?: string; }

export class AudioAudit {
  private readonly run: string = '__AUDIO579_RUN__';
  private readonly role: string = '__AUDIO579_ROLE__';
  private serial: Promise<void> = Promise.resolve();
  private used: string[] = [];
  private sequence: number = 0;
  private capturer: audio.AudioCapturer | undefined = undefined;
  private samples: number = 0;
  private captured: number = 0;
  private captureOperation: string = '';
  private captureRequest: Request | undefined = undefined;
  private captureCallback: (value: ArrayBuffer) => void = (_value: ArrayBuffer): void => {};
  private playerState: string = '';
  private waveform: string = '';

  constructor(private context: common.UIAbilityContext) {
    // A real process rebuild appends to the same private journal. Preserve its
    // sequence and used nonces; the external raw replay checks the full prefix.
    const path = context.filesDir + '/audio579-' + this.run + '.jsonl';
    if (fs.accessSync(path)) {
      const text = fs.readTextSync(path);
      if (text.length > 4 * 1024 * 1024 || !text.endsWith('\n')) { throw new Error('Existing journal incomplete'); }
      const lines = text.trimEnd().split('\n');
      this.sequence = lines.length;
      for (let i: number = 0; i < lines.length; ++i) {
        const previous = JSON.parse(lines[i]) as Request;
        if (!this.used.includes(previous.operation)) { this.used.push(previous.operation); }
      }
    }
  }

  private now(): number { return systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, false); }
  private wait(ms: number): Promise<void> { return new Promise<void>((resolve): void => { setTimeout(resolve, ms); }); }
  private append(c: Request, event: string, value: string = 'null', code: number = 0): void {
    const line = JSON.stringify({ run: this.run, role: this.role, boot: c.boot, operation: c.operation,
      action: c.action, event: event, value: value, code: code, seq: ++this.sequence,
      uid: process.uid, pid: process.pid, uptimeMs: this.now(), filesDir: this.context.filesDir }) + '\n';
    const file = fs.openSync(this.context.filesDir + '/audio579-' + this.run + '.jsonl',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
    try {
      const bytes = new util.TextEncoder().encodeInto(line);
      let offset: number = 0;
      while (offset < bytes.byteLength) {
        const count = fs.writeSync(file.fd, bytes.slice(offset).buffer);
        if (count <= 0) { throw new Error('Journal short write'); }
        offset += count;
      }
    } finally { fs.closeSync(file); }
  }
  accept(text: string): void {
    const c = JSON.parse(text) as Request;
    if (text.length > 2048 || c.run !== this.run || !/^[a-f0-9-]{36}$/.test(c.boot) ||
      !/^[a-f0-9]{32}$/.test(c.operation) || this.used.includes(c.operation) || this.used.length > 256 ||
      !['permission', 'identity', 'capture-start', 'capture-stop', 'communication', 'tone', 'spatial',
        'voice', 'player', 'recorder', 'soundpool', 'midi', 'state', 'cleanup', 'quiet'].includes(c.action)) {
      throw new Error('Fixed fresh original request required');
    }
    if (c.phrase !== undefined && (c.action !== 'voice' || !/^[\u3400-\u9fff]{2,32}$/.test(c.phrase))) { throw new Error('Actual public CJK phrase configuration required'); }
    this.used.push(c.operation);
    this.serial = this.serial.then((): Promise<void> => this.execute(c));
  }
  private info(usage: audio.StreamUsage): audio.AudioRendererInfo {
    return { content: audio.ContentType.CONTENT_TYPE_MUSIC, usage: usage, rendererFlags: 0 };
  }
  private stream(): audio.AudioStreamInfo {
    return { samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_48000, channels: audio.AudioChannel.CHANNEL_2,
      sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE, encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW };
  }
  private pcm(): ArrayBuffer {
    const frames: number = 76800;
    const data = new ArrayBuffer(frames * 4);
    const view = new DataView(data);
    for (let frame: number = 0; frame < frames; frame++) {
      const segment: number = Math.floor(frame / 4800);
      const frequency: number = 360 + (parseInt(this.run.substring(segment * 2, segment * 2 + 2), 16) % 40) * 40;
      const value: number = Math.round(6000 * Math.sin(2 * Math.PI * frequency * (frame % 4800) / 48000));
      view.setInt16(frame * 4, value, true); view.setInt16(frame * 4 + 2, value, true);
    }
    return data;
  }
  private wave(): string {
    if (this.waveform.length > 0) { return this.waveform; }
    const pcm = this.pcm();
    const header = new ArrayBuffer(44);
    const v = new DataView(header);
    const tags: number[] = [82,73,70,70,0,0,0,0,87,65,86,69,102,109,116,32];
    tags.forEach((value: number, index: number): void => { v.setUint8(index, value); });
    v.setUint32(4, pcm.byteLength + 36, true); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, 2, true); v.setUint32(24, 48000, true); v.setUint32(28, 192000, true);
    v.setUint16(32, 4, true); v.setUint16(34, 16, true);
    [100,97,116,97].forEach((value: number, index: number): void => { v.setUint8(36 + index, value); });
    v.setUint32(40, pcm.byteLength, true);
    this.waveform = this.context.filesDir + '/audio579-' + this.run + '.wav';
    const f = fs.openSync(this.waveform, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
    try {
      if (fs.writeSync(f.fd, header) !== header.byteLength || fs.writeSync(f.fd, pcm) !== pcm.byteLength) {
        throw new Error('Actual challenge write incomplete');
      }
    } finally { fs.closeSync(f); }
    return this.waveform;
  }
  private async captureStart(c: Request, source: audio.SourceType): Promise<void> {
    if (this.capturer !== undefined) { throw new Error('Release prior actual capture'); }
    const options: audio.AudioCapturerOptions = { streamInfo: this.stream(),
      capturerInfo: { source: source, capturerFlags: 0 },
      playbackCaptureConfig: { filterOptions: { usages: [audio.StreamUsage.STREAM_USAGE_MEDIA] } } };
    if (source !== audio.SourceType.SOURCE_TYPE_PLAYBACK_CAPTURE) { options.playbackCaptureConfig = undefined; }
    this.capturer = await audio.createAudioCapturer(options);
    this.samples = 0; this.captured = 0; this.captureOperation = c.operation; this.captureRequest = c;
    const path = this.context.filesDir + '/audio579-' + this.run + '-' + c.operation + '.pcm';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
    fs.closeSync(file);
    this.captureCallback = (data: ArrayBuffer): void => {
      if (this.samples + data.byteLength > 16 * 1024 * 1024) { throw new Error('Bounded real PCM exceeded'); }
      const out = fs.openSync(path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND | fs.OpenMode.NOFOLLOW);
      try { if (fs.writeSync(out.fd, data) !== data.byteLength) { throw new Error('PCM short write'); } }
      finally { fs.closeSync(out); }
      this.samples += data.byteLength; this.captured++;
    };
    this.capturer.on('readData', this.captureCallback);
    await this.capturer.start();
    this.append(c, 'capture-started', JSON.stringify({ path: path, source: source, state: this.capturer.state,
      actualStream: await this.capturer.getStreamInfo() }));
  }
  private async captureStop(c: Request): Promise<void> {
    const capturer = this.capturer;
    if (capturer === undefined) { throw new Error('No real capture to stop'); }
    await capturer.stop(); capturer.off('readData', this.captureCallback); await capturer.release();
    this.capturer = undefined;
    const bytes = this.samples; const count = this.captured;
    this.append(c, 'capture-stopped', JSON.stringify({ operation: this.captureOperation, bytes: bytes, callbacks: count }));
    await this.wait(1500);
    this.append(c, 'capture-quiet', JSON.stringify({ beforeBytes: bytes, afterBytes: this.samples,
      beforeCallbacks: count, afterCallbacks: this.captured }));
  }
  private async communication(c: Request): Promise<void> {
    const manager = audio.getAudioManager(); const route = manager.getRoutingManager();
    const beforeScene = await manager.getAudioScene();
    const beforeSpeaker = await route.isCommunicationDeviceActive(audio.CommunicationDeviceType.SPEAKER);
    this.append(c, 'communication-before', JSON.stringify({ scene: beforeScene, speaker: beforeSpeaker }));
    let renderer: audio.AudioRenderer | undefined = undefined;
    let changedScene: boolean = false; let changedRoute: boolean = false;
    try {
      await manager.setAudioScene(audio.AudioScene.AUDIO_SCENE_VOICE_CHAT); changedScene = true;
      await route.setCommunicationDevice(audio.CommunicationDeviceType.SPEAKER, true); changedRoute = true;
      this.append(c, 'communication-selected', JSON.stringify({ scene: await manager.getAudioScene(),
        speaker: await route.isCommunicationDeviceActive(audio.CommunicationDeviceType.SPEAKER) }));
      await this.captureStart(c, audio.SourceType.SOURCE_TYPE_VOICE_COMMUNICATION);
      renderer = await audio.createAudioRenderer({ streamInfo: this.stream(),
        rendererInfo: this.info(audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION) });
      await renderer.start();
      const bytes = this.pcm(); let offset: number = 0;
      while (offset < bytes.byteLength) {
        const written = await renderer.write(bytes.slice(offset));
        if (written <= 0 || written > bytes.byteLength - offset) { throw new Error('Real renderer write failed'); }
        offset += written;
      }
      await renderer.drain();
      this.append(c, 'communication-rendered', JSON.stringify({ bytes: offset, state: renderer.state }));
      await renderer.stop(); await renderer.release(); renderer = undefined;
      await this.captureStop(c);
    } finally {
      if (renderer !== undefined) { await renderer.release(); }
      if (this.capturer !== undefined) { await this.captureStop(c); }
      if (changedRoute) { await route.setCommunicationDevice(audio.CommunicationDeviceType.SPEAKER, beforeSpeaker); }
      if (changedScene) { await manager.setAudioScene(beforeScene); }
      this.append(c, 'communication-restored', JSON.stringify({ scene: await manager.getAudioScene(),
        speaker: await route.isCommunicationDeviceActive(audio.CommunicationDeviceType.SPEAKER) }));
    }
  }
  private async tone(c: Request): Promise<void> {
    const tone = await audio.createTonePlayer(this.info(audio.StreamUsage.STREAM_USAGE_MEDIA));
    try {
      for (let index: number = 0; index < 2; index++) {
        const digit: number = parseInt(this.run.substring(index * 2, index * 2 + 2), 16) % 10;
        await tone.load(digit as audio.ToneType); this.append(c, 'tone-loaded', JSON.stringify({ digit: digit }));
        await tone.start(); this.append(c, 'tone-started'); await this.wait(600);
        await tone.stop(); this.append(c, 'tone-stopped'); await this.wait(200);
      }
    } finally { await tone.release(); this.append(c, 'tone-released'); }
  }
  private async spatial(c: Request): Promise<void> {
    const manager = audio.getAudioManager().getSpatializationManager();
    const supported = manager.isSpatializationSupported(); const head = manager.isHeadTrackingSupported();
    const before = manager.isSpatializationEnabled(); const tracking = manager.isHeadTrackingEnabled();
    this.append(c, 'spatial-capability', JSON.stringify({ supported: supported, headTracking: head,
      enabled: before, trackingEnabled: tracking }));
    let callbacks: number = 0; let headCallbacks: number = 0;
    const callback = (value: boolean): void => { callbacks++; this.append(c, 'spatial-callback', JSON.stringify(value)); };
    const headCallback = (value: boolean): void => { headCallbacks++; this.append(c, 'head-callback', JSON.stringify(value)); };
    if (this.role === 'denied') { await manager.setSpatializationEnabled(before); }
    manager.on('spatializationEnabledChange', callback); manager.on('headTrackingEnabledChange', headCallback);
    let renderer: audio.AudioRenderer | undefined = undefined;
    try {
      // A false optional sensor/provider flag does not bypass framework tests.
      for (let cycle: number = 0; cycle < 2; cycle++) {
        for (const value of [false, true, false]) {
          await manager.setSpatializationEnabled(value); await this.wait(300);
          this.append(c, 'spatial-changed', JSON.stringify({ cycle: cycle, requested: value, actual: manager.isSpatializationEnabled() }));
          await manager.setHeadTrackingEnabled(value);
          const poses: number[] = value ? [0, 1] : [0];
          for (const pose of poses) {
          if (value) { this.append(c, 'spatial-pose-window', JSON.stringify({ cycle: cycle, index: pose })); await this.wait(800); }
          renderer = await audio.createAudioRenderer({ streamInfo: this.stream(), rendererInfo: this.info(audio.StreamUsage.STREAM_USAGE_MEDIA) });
          await renderer.start(); const bytes = this.pcm(); let offset: number = 0;
          this.append(c, 'spatial-render-begin', JSON.stringify({ cycle: cycle, spatial: value }));
          while (offset < bytes.byteLength) {
            const written: number = await renderer.write(bytes.slice(offset));
            if (written <= 0 || written > bytes.byteLength - offset) { throw new Error('Real spatial renderer short write'); }
            offset += written;
          }
          await renderer.drain(); await renderer.stop(); await renderer.release(); renderer = undefined;
          this.append(c, 'spatial-render-end', JSON.stringify({ cycle: cycle, spatial: value, bytes: offset }));
          }
        }
      }
      await manager.setSpatializationEnabled(true); await manager.setHeadTrackingEnabled(true);
      this.append(c, 'spatial-restore-pose-window'); await this.wait(800);
      renderer = await audio.createAudioRenderer({ streamInfo: this.stream(), rendererInfo: this.info(audio.StreamUsage.STREAM_USAGE_MEDIA) });
      await renderer.start(); const restorePcm = this.pcm(); let restored: number = 0;
      while (restored < restorePcm.byteLength) {
        const wrote: number = await renderer.write(restorePcm.slice(restored));
        if (wrote <= 0 || wrote > restorePcm.byteLength - restored) { throw new Error('Real pose baseline renderer short write'); }
        restored += wrote;
      }
      await renderer.drain(); await renderer.stop(); await renderer.release(); renderer = undefined;
      this.append(c, 'spatial-before-head-disable'); await this.wait(800);
      await manager.setHeadTrackingEnabled(false); await manager.setSpatializationEnabled(false);
      this.append(c, 'spatial-head-disabled'); await this.wait(2500);
    } finally {
      if (renderer !== undefined) { await renderer.release(); }
      await manager.setSpatializationEnabled(before); await manager.setHeadTrackingEnabled(tracking);
      manager.off('spatializationEnabledChange', callback); manager.off('headTrackingEnabledChange', headCallback);
      this.append(c, 'spatial-restored', JSON.stringify({ spatial: manager.isSpatializationEnabled(), head: manager.isHeadTrackingEnabled() }));
      const beforeCallbacks: number = callbacks; const beforeHead: number = headCallbacks; await this.wait(1500);
      this.append(c, 'spatial-quiet', JSON.stringify({ before: beforeCallbacks, after: callbacks, headBefore: beforeHead, headAfter: headCallbacks }));
    }
  }
  private async intelligentVoice(c: Request): Promise<void> {
    const manager = voice.getIntelligentVoiceManager();
    this.append(c, 'voice-capabilities', JSON.stringify(manager.getCapabilityInfo()));
    const callback = (value: voice.ServiceChangeType): void => { this.append(c, 'voice-service-change', JSON.stringify(value)); };
    manager.on('serviceChange', callback);
    let engine: voice.EnrollIntelligentVoiceEngine | undefined = undefined;
    try {
      engine = await voice.createEnrollIntelligentVoiceEngine({ wakeupPhrase: c.phrase === undefined ? '小艺小艺' : c.phrase });
      this.append(c, 'voice-created');
      await engine.init({ language: 'zh', region: 'CN' }); this.append(c, 'voice-initialized');
      this.append(c, 'voice-listening');
      this.append(c, 'voice-enrollment', JSON.stringify(await engine.enrollForResult(true)));
      await engine.stop(); this.append(c, 'voice-stopped');
      await engine.commit(); this.append(c, 'voice-commit');
      await engine.release(); engine = undefined; this.append(c, 'voice-released');
      const wake = await voice.createWakeupIntelligentVoiceEngine({ needReconfirm: false, wakeupPhrase: c.phrase === undefined ? '小艺小艺' : c.phrase });
      let wakeups: number = 0;
      const heard = (value: voice.WakeupIntelligentVoiceEngineCallbackInfo): void => {
        wakeups++; this.append(c, 'voice-wakeup', JSON.stringify(value));
      };
      try {
        wake.on('wakeupIntelligentVoiceEvent', heard); this.append(c, 'voice-await-actual-wakeup');
        await this.wait(13000);
        this.append(c, 'voice-before-revoke', JSON.stringify({ callbacks: wakeups }));
        const beforeRevoke: number = wakeups; await this.wait(8000);
        const revoked: number = await abilityAccessCtrl.createAtManager().checkAccessToken(this.context.applicationInfo.accessTokenId, 'ohos.permission.MICROPHONE');
        this.append(c, 'voice-after-revoke', JSON.stringify({ before: beforeRevoke, after: wakeups, permission: revoked }));
      } finally {
        wake.off('wakeupIntelligentVoiceEvent', heard); await wake.release(); this.append(c, 'voice-wakeup-released');
        const count: number = wakeups; await this.wait(1500); this.append(c, 'voice-wakeup-quiet', JSON.stringify({ before: count, after: wakeups }));
      }
    } finally {
      if (engine !== undefined) { await engine.release(); this.append(c, 'voice-released'); }
      manager.off('serviceChange', callback); await this.wait(1500); this.append(c, 'voice-quiet');
    }
  }
  private async state(wanted: string): Promise<void> {
    const deadline: number = this.now() + 15000;
    while (this.playerState !== wanted) {
      if (this.playerState === 'error') { throw new Error('Actual native media error; original code is in raw error event'); }
      if (this.now() > deadline) { throw new Error('Actual player state deadline: ' + wanted); }
      await this.wait(50);
    }
  }
  private async player(c: Request): Promise<void> {
    const file = fs.openSync(this.wave(), fs.OpenMode.READ_ONLY);
    const player = media.createAudioPlayer();
    player.on('dataLoad', (): void => { this.playerState = 'loaded'; this.append(c, 'player-loaded'); });
    player.on('play', (): void => { this.playerState = 'playing'; this.append(c, 'player-playing'); });
    player.on('pause', (): void => { this.playerState = 'paused'; this.append(c, 'player-paused'); });
    player.on('finish', (): void => { this.playerState = 'completed'; this.append(c, 'player-finished'); });
    player.on('stop', (): void => { this.playerState = 'stopped'; this.append(c, 'player-stopped'); });
    player.on('reset', (): void => { this.playerState = 'idle'; this.append(c, 'player-reset'); });
    player.on('error', (error: BusinessError): void => {
      this.playerState = 'error'; this.append(c, 'player-error', JSON.stringify(error.message), error.code);
    });
    try {
      this.playerState = '';
      player.fdSrc = { fd: file.fd, offset: 0, length: fs.statSync(file.fd).size };
      await this.state('loaded'); player.play(); await this.state('playing'); await this.wait(400);
      player.pause(); await this.state('paused'); await this.wait(200);
      player.play(); await this.state('playing'); await this.state('completed');
      player.stop(); await this.state('stopped'); player.reset(); await this.state('idle');
    } finally {
      player.release(); this.append(c, 'player-released'); fs.closeSync(file);
      await this.wait(1500); this.append(c, 'player-quiet');
    }
  }
  private async recorder(c: Request): Promise<void> {
    const path = this.context.filesDir + '/audio579-recorder-' + this.run + '-' + c.operation + '.m4a';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.EXCL);
    const recorder = media.createAudioRecorder();
    recorder.on('prepare', (): void => { this.playerState = 'prepared'; this.append(c, 'recorder-prepared'); });
    recorder.on('start', (): void => { this.playerState = 'recording'; this.append(c, 'recorder-started'); });
    recorder.on('pause', (): void => { this.playerState = 'paused'; this.append(c, 'recorder-paused'); });
    recorder.on('resume', (): void => { this.playerState = 'recording'; this.append(c, 'recorder-resumed'); });
    recorder.on('stop', (): void => { this.playerState = 'stopped'; this.append(c, 'recorder-stopped'); });
    recorder.on('reset', (): void => { this.playerState = 'idle'; this.append(c, 'recorder-reset'); });
    recorder.on('release', (): void => { this.playerState = 'released'; this.append(c, 'recorder-released'); });
    recorder.on('error', (error: BusinessError): void => {
      this.playerState = 'error'; this.append(c, 'recorder-error', JSON.stringify(error.message), error.code);
    });
    this.append(c, 'recorder-file', JSON.stringify(path));
    try {
      this.playerState = '';
      recorder.prepare({ uri: 'fd://' + file.fd, audioEncoderMime: media.CodecMimeType.AUDIO_AAC,
        fileFormat: media.ContainerFormatType.CFT_MPEG_4A, audioEncodeBitRate: 128000,
        audioSampleRate: 48000, numberOfChannels: 2 });
      await this.state('prepared'); recorder.start(); await this.state('recording'); await this.wait(1000);
      recorder.pause(); await this.state('paused'); await this.wait(200);
      recorder.resume(); await this.state('recording'); await this.wait(1000);
      recorder.stop(); await this.state('stopped'); recorder.reset(); await this.state('idle');
    } finally {
      recorder.release(); await this.state('released'); fs.closeSync(file);
      this.append(c, 'recorder-file-finished', JSON.stringify({ path: path, bytes: fs.statSync(path).size }));
      await this.wait(1500); this.append(c, 'recorder-quiet');
    }
  }
  private async soundPool(c: Request): Promise<void> {
    const file = fs.openSync(this.wave(), fs.OpenMode.READ_ONLY);
    const pool = await media.createSoundPool(2, this.info(audio.StreamUsage.STREAM_USAGE_MEDIA));
    let loaded: number = -1; let finished: number = -1;
    const onLoad = (id: number): void => { loaded = id; this.append(c, 'soundpool-loaded', JSON.stringify(id)); };
    const onFinish = (id: number): void => { finished = id; this.append(c, 'soundpool-finished', JSON.stringify(id)); };
    pool.on('loadComplete', onLoad); pool.on('playFinishedWithStreamId', onFinish);
    try {
      const sound = await pool.load(file.fd, 0, fs.statSync(file.fd).size);
      const deadline: number = this.now() + 15000;
      while (loaded !== sound) { if (this.now() > deadline) { throw new Error('Actual SoundPool load callback missing'); } await this.wait(50); }
      const stream = await pool.play(sound, { loop: 0, rate: 0, leftVolume: 1, rightVolume: 1, priority: 1 });
      this.append(c, 'soundpool-playing', JSON.stringify({ sound: sound, stream: stream }));
      while (finished !== stream) { if (this.now() > deadline) { throw new Error('Actual SoundPool completion missing'); } await this.wait(50); }
      const interrupted = await pool.play(sound, { loop: 10, rate: 0, leftVolume: 1, rightVolume: 1 });
      this.append(c, 'soundpool-replayed', JSON.stringify(interrupted)); await this.wait(300);
      await pool.stop(interrupted); this.append(c, 'soundpool-stopped', JSON.stringify(interrupted));
      await pool.unload(sound); this.append(c, 'soundpool-unloaded', JSON.stringify(sound));
    } finally {
      pool.off('loadComplete'); pool.off('playFinishedWithStreamId'); await pool.release();
      this.append(c, 'soundpool-released'); fs.closeSync(file);
      await this.wait(1500); this.append(c, 'soundpool-quiet');
    }
  }
  private async execute(c: Request): Promise<void> {
    this.append(c, 'begin', JSON.stringify(c));
    try {
      if (c.action === 'permission') {
        const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(this.context, ['ohos.permission.MICROPHONE']);
        this.append(c, 'permission-result', JSON.stringify(result));
      } else if (c.action === 'capture-start') {
        await this.captureStart(c, audio.SourceType.SOURCE_TYPE_PLAYBACK_CAPTURE);
      } else if (c.action === 'capture-stop') { await this.captureStop(c);
      } else if (c.action === 'communication') { await this.communication(c);
      } else if (c.action === 'tone') { await this.tone(c);
      } else if (c.action === 'spatial') { await this.spatial(c);
      } else if (c.action === 'voice') { await this.intelligentVoice(c);
      } else if (c.action === 'player') { await this.player(c);
      } else if (c.action === 'recorder') { await this.recorder(c);
      } else if (c.action === 'soundpool') { await this.soundPool(c);
      } else if (c.action === 'midi') {
        this.append(c, 'midi-started', JSON.stringify(midi.run(this.run, c.operation, this.context.filesDir)));
      } else if (c.action === 'state') {
        const manager = audio.getAudioManager(); const streams = manager.getStreamManager();
        this.append(c, 'native-stream-state', JSON.stringify({ scene: await manager.getAudioScene(),
          speaker: await manager.getRoutingManager().isCommunicationDeviceActive(audio.CommunicationDeviceType.SPEAKER),
          capturers: await streams.getCurrentAudioCapturerInfoArray(),
          renderers: await streams.getCurrentAudioRendererInfoArray() }));
      } else if (c.action === 'cleanup') {
        if (this.capturer !== undefined) { await this.captureStop(c); }
      } else if (c.action === 'quiet') { await this.wait(1500); }
      this.append(c, 'return');
    } catch (error) {
      const e = error as BusinessError;
      this.append(c, 'throw', JSON.stringify({ message: e.message, codeType: typeof e.code }),
        typeof e.code === 'number' ? e.code : -1);
    } finally { this.append(c, 'end'); }
  }
}
