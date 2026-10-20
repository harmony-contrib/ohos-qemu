import { common } from '@kit.AbilityKit';

// Private main-thread/worker protocol: no request can supply recognized text.
export interface CaptionInput {
  kind: string;
  session: string;
  sequence: number;
  context?: common.Context;
  samples?: Float32Array;
}
export interface CaptionOutput {
  kind: string;
  session: string;
  sequence: number;
  samples: number;
  segments: number;
  text: string;
  language: string;
  message: string;
}
export const SAMPLE_RATE: number = 16000;
export const WINDOW_SAMPLES: number = 512;
export const MAX_BUFFERED_SAMPLES: number = SAMPLE_RATE * 15;
export const MAX_SEGMENT_SAMPLES: number = SAMPLE_RATE * 30;
