// Single admitted model, from fixed OpenHarmony-SIG NonStreamingAsrModels case 2.
// English only. No SenseVoice/remote/text fallback or run-time model selector.
import { OfflineRecognizerConfig } from 'sherpa_onnx';
export const MODEL_DIRECTORY: string = 'sherpa-onnx-whisper-tiny.en';
export const VAD_MODEL: string = 'silero_vad.onnx';
export function recognizerConfig(): OfflineRecognizerConfig {
  const config = new OfflineRecognizerConfig();
  config.featConfig.sampleRate = 16000;
  config.modelConfig.whisper.encoder = MODEL_DIRECTORY + '/tiny.en-encoder.int8.onnx';
  config.modelConfig.whisper.decoder = MODEL_DIRECTORY + '/tiny.en-decoder.int8.onnx';
  config.modelConfig.whisper.language = 'en';
  config.modelConfig.whisper.task = 'transcribe';
  config.modelConfig.tokens = MODEL_DIRECTORY + '/tiny.en-tokens.txt';
  config.modelConfig.modelType = 'whisper';
  config.modelConfig.provider = 'cpu';
  config.modelConfig.numThreads = 1;
  config.modelConfig.debug = false;
  config.ruleFsts = ''; config.ruleFars = '';
  return config;
}
