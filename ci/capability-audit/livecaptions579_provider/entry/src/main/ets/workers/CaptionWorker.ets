/*
 * Adapted from OpenHarmony-SIG applications_ai_model_samples AsrAndTts,
 * revision 2b768749568a9cff787c2f822913bfe5e9c78684.
 * Copyright (c) 2025 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import worker, { MessageEvents, ThreadWorkerGlobalScope } from '@ohos.worker';
import { BusinessError } from '@kit.BasicServicesKit';
import { OfflineRecognizer, OfflineStream, SpeechSegment, Vad, VadConfig, SileroVadConfig } from 'sherpa_onnx';
import { CaptionInput, CaptionOutput, SAMPLE_RATE, WINDOW_SAMPLES, MAX_SEGMENT_SAMPLES } from '../common/CaptionProtocol';
import { VAD_MODEL, recognizerConfig } from '../common/ModelProfile';

const port: ThreadWorkerGlobalScope = worker.workerPort;
let recognizer: OfflineRecognizer | undefined = undefined;
let detector: Vad | undefined = undefined;
let session: string = '';
let sequence: number = 0;
let acceptedSamples: number = 0;
let decodedSegments: number = 0;
let sinceFlush: number = 0;
let tail: Float32Array = new Float32Array(0);
let failed: boolean = false;

function send(kind: string, text: string = '', language: string = '', message: string = ''): void {
  const output: CaptionOutput = { kind, session, sequence, samples: acceptedSamples,
    segments: decodedSegments, text, language, message };
  port.postMessage(output);
}
function decodeSegments(): void {
  if (detector === undefined || recognizer === undefined) { throw new Error('actual recognizer is absent'); }
  while (!detector.isEmpty()) {
    // Copy owned samples; pop cannot invalidate memory supplied to the stream.
    const segment: SpeechSegment = detector.front(false);
    try {
      if (segment.samples.length < SAMPLE_RATE / 5) { continue; }
      if (segment.samples.length > MAX_SEGMENT_SAMPLES) { throw new Error('speech segment exceeds bounded session input'); }
      const stream: OfflineStream = recognizer.createStream();
      stream.acceptWaveform({ samples: segment.samples, sampleRate: SAMPLE_RATE });
      recognizer.decode(stream);
      const result = recognizer.getResult(stream);
      ++decodedSegments;
      // Only native result text is displayed; model metadata tags are removed.
      const text: string = result.text.replace(/<\|[^|>]+\|>/g, '').trim();
      if (text.length > 0) { send('result', text, result.lang); }
    } finally { detector.pop(); }
  }
}
function accept(samples: Float32Array): void {
  if (detector === undefined || samples.length <= 0 || samples.length > MAX_SEGMENT_SAMPLES) {
    throw new Error('bounded real PCM required');
  }
  for (let i: number = 0; i < samples.length; ++i) {
    if (!Number.isFinite(samples[i]) || samples[i] < -1 || samples[i] > 1) { throw new Error('invalid real PCM value'); }
  }
  acceptedSamples += samples.length;
  const joined = new Float32Array(tail.length + samples.length);
  joined.set(tail); joined.set(samples, tail.length);
  let offset: number = 0;
  while (offset + WINDOW_SAMPLES <= joined.length) {
    detector.acceptWaveform(joined.subarray(offset, offset + WINDOW_SAMPLES));
    offset += WINDOW_SAMPLES; sinceFlush += WINDOW_SAMPLES;
    decodeSegments();
    // Bound uninterrupted speech. Ordinary chunks do not reset/flush VAD.
    if (sinceFlush >= SAMPLE_RATE * 15) {
      detector.flush(); decodeSegments(); detector.reset(); sinceFlush = 0;
    }
  }
  tail = joined.slice(offset);
}
port.onmessage = (event: MessageEvents): void => {
  const input = event.data as CaptionInput;
  try {
    if (failed || typeof input.session !== 'string' || !/^[a-f0-9-]{36}$/.test(input.session) ||
      !Number.isInteger(input.sequence)) { throw new Error('invalid private worker session'); }
    if (input.kind === 'init') {
      if (recognizer !== undefined || detector !== undefined || input.sequence !== 0 || input.context === undefined) {
        throw new Error('one genuine worker initialization required');
      }
      session = input.session;
      const manager = input.context.resourceManager;
      recognizer = new OfflineRecognizer(recognizerConfig(), manager);
      detector = new Vad(new VadConfig(new SileroVadConfig(VAD_MODEL, 0.5, 0.2, 0.4, WINDOW_SAMPLES),
        SAMPLE_RATE, false, 1), 30, manager);
      detector.reset();
      // Calls the real native handle after initialization, not a model pass bit.
      if (!detector.isEmpty()) { throw new Error('fresh detector contains unexpected audio'); }
      send('ready');
    } else if (input.kind === 'pcm') {
      if (input.session !== session || input.sequence !== sequence + 1 || input.samples === undefined) {
        throw new Error('real PCM sequence/session mismatch');
      }
      sequence = input.sequence;
      accept(input.samples);
      send('ack');
    } else { throw new Error('worker accepts initialization and captured PCM only'); }
  } catch (error) {
    failed = true;
    const actual = error as BusinessError;
    send('error', '', '', typeof actual.message === 'string' ? actual.message : 'native worker failed');
  }
};
port.onmessageerror = (event: MessageEvents): void => {
  failed = true;
  send('error', '', '', 'private worker message could not be delivered');
};
