import { common, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import audio from '@ohos.multimedia.audio';
import config from '@ohos.accessibility.config';
import settings from '@ohos.settings';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import { Journal, Request, SERVICE as ROLE, RUN } from './Journal';

interface Saved { enabled: boolean; target: string; targets: string[]; }
interface PrivacyAudioManager extends audio.AudioManager {
  reportPlaybackCaptureUserChoice(sessionId: number, choice: boolean): number;
}
function baseline(context: common.UIAbilityContext): string { return context.filesDir + '/caption-baseline-' + RUN + '.json'; }
export async function run(context: common.UIAbilityContext, want: Want): Promise<void> {
  const request: Request = Journal.request(want);
  Journal.write(context, request, 'begin', 0, ROLE);
  try {
    if (ROLE === 'control') {
      if (request.action === 'save') {
        const saved: Saved = { enabled: await config.shortkey.get(), target: await config.shortkeyTarget.get(),
          targets: await config.shortkeyMultiTargets.get() };
        const path: string = baseline(context);
        if (fs.accessSync(path)) { throw new Error('fresh actual baseline file required'); }
        const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.NOFOLLOW);
        try { fs.writeSync(file.fd, JSON.stringify(saved)); fs.fsyncSync(file.fd); } finally { fs.closeSync(file); }
        Journal.write(context, request, 'saved', 0, JSON.stringify(saved));
      } else if (request.action === 'configure') {
        await config.shortkeyMultiTargets.set(['CAPTIONS_ASSISTANT']); await config.shortkey.set(true);
        Journal.write(context, request, 'configured', 0, JSON.stringify({ enabled: await config.shortkey.get(),
          targets: await config.shortkeyMultiTargets.get() }));
      } else if (request.action === 'restore') {
        const saved = JSON.parse(fs.readTextSync(baseline(context))) as Saved;
        await config.shortkey.set(false); await config.shortkeyTarget.set(saved.target);
        await config.shortkeyMultiTargets.set(saved.targets); await config.shortkey.set(saved.enabled);
        Journal.write(context, request, 'restored', 0, JSON.stringify({ enabled: await config.shortkey.get(),
          target: await config.shortkeyTarget.get(), targets: await config.shortkeyMultiTargets.get() }));
      } else if (request.action === 'state') {
        const manager: audio.AudioStreamManager = audio.getAudioManager().getStreamManager();
        Journal.write(context, request, 'state', 0, JSON.stringify({ captionRequested:
          settings.getValueSync(context, 'vassistant_ai_caption_enable', 'false', settings.domainName.USER_PROPERTY),
          capturers: manager.getCurrentAudioCapturerInfoArraySync() }));
      } else { throw new Error('fixed actual control action required'); }
    } else if (ROLE === 'ordinary') {
      if (request.action === 'forbidden-provider') {
        await context.startAbility({ bundleName: 'com.ohos.vassistant', abilityName: 'AiCaptionServiceExtAbility' });
        Journal.write(context, request, 'forbidden.provider.return', 0, 'actual unauthorized start returned');
        Journal.write(context, request, 'done', 0, request.action); return;
      }
      if (request.action !== 'forbidden-decision') { throw new Error('fixed unprivileged native-report action required'); }
      // Valid native parameter types; this is an actual service permission
      // boundary, not a TypeError/guessed callback as a negative result.
      const p = want.parameters;
      if (typeof p?.streamId !== 'number' || !Number.isInteger(p.streamId as number) || (p.streamId as number) <= 0) {
        throw new Error('actual live foreign capturer stream ID required');
      }
      const value: number = (audio.getAudioManager() as PrivacyAudioManager).reportPlaybackCaptureUserChoice(p.streamId as number, true);
      Journal.write(context, request, 'forbidden.return', 0, JSON.stringify({ streamId: p.streamId, result: value }));
    } else {
      if (request.action !== 'play-a' && request.action !== 'play-b') { throw new Error('fixed actual media action required'); }
      const name: string = request.action === 'play-a' ? 'caption-a.wav' : 'caption-b.wav';
      const wav: Uint8Array = await context.resourceManager.getRawFileContent(name);
      const pcm: Uint8Array = waveform(wav);
      const renderer = await audio.createAudioRenderer({ streamInfo: {
        samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000, channels: audio.AudioChannel.CHANNEL_1,
        sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE, encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW },
        rendererInfo: { usage: audio.StreamUsage.STREAM_USAGE_MUSIC, rendererFlags: 0 },
        privacyType: ROLE === 'private' ? audio.AudioPrivacyType.PRIVACY_TYPE_PRIVATE : audio.AudioPrivacyType.PRIVACY_TYPE_PUBLIC });
      try {
        const streamId: number = await renderer.getAudioStreamId();
        await renderer.start();
        Journal.write(context, request, 'renderer.start', 0, JSON.stringify({ streamId, state: renderer.state,
          privacy: ROLE === 'private' ? 1 : 0, resource: name, waveformBytes: pcm.byteLength }));
        const silence: Uint8Array = new Uint8Array(32000);
        let written: number = await writeAll(renderer, silence);
        written += await writeAll(renderer, pcm); written += await writeAll(renderer, silence);
        await renderer.drain();
        Journal.write(context, request, 'renderer.drained', 0, JSON.stringify({ streamId, written,
          audioTime: await renderer.getAudioTime(), state: renderer.state }));
      } finally {
        if (renderer.state === audio.AudioState.STATE_RUNNING) { await renderer.stop(); }
        await renderer.release(); Journal.write(context, request, 'renderer.released', 0, renderer.state.toString());
      }
    }
    Journal.write(context, request, 'done', 0, request.action);
  } catch (error) {
    const actual = error as BusinessError;
    Journal.write(context, request, 'error', actual.code || -1, actual.message);
  }
}
function waveform(wav: Uint8Array): Uint8Array {
  const view: DataView = new DataView(wav.buffer, wav.byteOffset, wav.byteLength);
  if (wav.byteLength < 44 || view.getUint32(0, true) !== 0x46464952 || view.getUint32(8, true) !== 0x45564157 ||
    view.getUint32(4, true) + 8 !== wav.byteLength) { throw new Error('admitted complete RIFF WAVE required'); }
  let valid: boolean = false; let pcm: Uint8Array | undefined = undefined; let pos: number = 12;
  while (pos + 8 <= wav.byteLength) {
    const kind: number = view.getUint32(pos, true); const size: number = view.getUint32(pos + 4, true); pos += 8;
    if (size > wav.byteLength - pos) { throw new Error('truncated real WAV chunk'); }
    if (kind === 0x20746d66) {
      if (valid || size < 16 || view.getUint16(pos, true) !== 1 || view.getUint16(pos + 2, true) !== 1 ||
        view.getUint32(pos + 4, true) !== 16000 || view.getUint32(pos + 8, true) !== 32000 ||
        view.getUint16(pos + 12, true) !== 2 || view.getUint16(pos + 14, true) !== 16) { throw new Error('real PCM mono16k S16LE fixture required'); }
      valid = true;
    } else if (kind === 0x61746164) {
      if (pcm !== undefined || size < 32000 || size > 30 * 32000 || size % 2 !== 0) { throw new Error('bounded real speech data required'); }
      pcm = wav.slice(pos, pos + size);
    }
    pos += size + size % 2;
  }
  if (!valid || pcm === undefined || pos !== wav.byteLength) { throw new Error('complete admitted WAV chunks required'); }
  return pcm;
}
async function writeAll(renderer: audio.AudioRenderer, bytes: Uint8Array): Promise<number> {
  let offset: number = 0;
  while (offset < bytes.byteLength) {
    const buffer: ArrayBuffer = bytes.slice(offset, Math.min(offset + 4096, bytes.byteLength)).buffer;
    const written: number = await renderer.write(buffer);
    if (!Number.isInteger(written) || written <= 0 || written > buffer.byteLength) { throw new Error('real AudioRenderer partial write failed'); }
    offset += written;
  }
  return offset;
}
