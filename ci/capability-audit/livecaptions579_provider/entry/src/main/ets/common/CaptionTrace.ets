import hilog from '@ohos.hilog';
import process from '@ohos.process';

// No recognized text or captured audio is written to persistent product logs.
// UI is the consumer; counters and native statuses describe actual operations.
export function captionTrace(session: string, event: string, sequence: number,
  samples: number, segments: number, code: number = 0): void {
  hilog.info(0xFF70, 'LiveCaptions',
    'LC uid=%{public}d pid=%{public}d session=%{public}s event=%{public}s sequence=%{public}d samples=%{public}d segments=%{public}d code=%{public}d',
    process.uid, process.pid, session, event, sequence, samples, segments, code);
}
