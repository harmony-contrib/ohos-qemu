import nativeProbe from 'libbatchmediaaudioevent.so';
import hilog from '@ohos.hilog';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import common from '@ohos.app.ability.common';
import fs from '@ohos.file.fs';
import util from '@ohos.util';
import backgroundTaskManager from '@ohos.resourceschedule.backgroundTaskManager';
import wantAgent from '@ohos.wantAgent';
import notificationManager from '@ohos.notificationManager';
import { BusinessError } from '@ohos.base';

interface AudioEventReady {
  run_id: string;
  action: string;
  state_result: number;
  state: number;
  frames_result: number;
  frames: number;
  copied_bytes: number;
}

interface AudioEventNativeControl {
  run(runId: string, mode: number): boolean;
  status(runId: string): number;
  abort(runId: string): boolean;
}

// One ordinary UIAbility owns this real audioRecording task and its notification.
// Completion and cancellation follow the actual native worker, not a timer pass.
class AudioRecordingSession {
  private readonly context: common.UIAbilityContext;
  private readonly runId: string;
  private readonly mode: number;
  private readonly native: AudioEventNativeControl;
  private sequence: number = 0;
  private pollTimer: number = -1;
  private startedMs: number = 0;
  private taskId: number = -1;
  private backgroundStarted: boolean = false;
  private subscribed: boolean = false;
  private nativeStarted: boolean = false;
  private cleaning: boolean = false;
  private failed: boolean = false;

  constructor(context: common.UIAbilityContext, runId: string, mode: number, control: AudioEventNativeControl) {
    this.context = context;
    this.runId = runId;
    this.mode = mode;
    this.native = control;
  }

  private record(event: string, detail: string): void {
    const text = JSON.stringify({ run_id: this.runId, mode: this.mode, event: event,
      wall_clock_ms: Date.now(), detail: detail }) + '\n';
    const path = this.context.getApplicationContext().filesDir + '/audio-event-' + this.runId + '-mode' +
      this.mode + '-background-' + this.sequence.toString().padStart(3, '0') + '.json';
    this.sequence++;
    try {
      if (fs.accessSync(path)) {
        throw new Error('Existing background-task evidence is preserved');
      }
      const output = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
      try {
        const encoded = new util.TextEncoder().encodeInto(text);
        if (fs.writeSync(output.fd, encoded.buffer as ArrayBuffer) !== encoded.byteLength) {
          throw new Error('Background-task evidence write was incomplete');
        }
        fs.fsyncSync(output.fd);
      } finally {
        fs.closeSync(output);
      }
    } catch (error) {
      // SDK file errors propagate. Evidence failure must never imply task success.
      const actual = error as BusinessError;
      // ArkTS requires a real Error. Preserve the original BusinessError fields
      // in its message even when the SDK rejected with a plain business object.
      throw new Error(JSON.stringify({ name: actual.name, code: actual.code,
        message: actual.message, stack: actual.stack, data: actual.data }));
    }
    hilog.info(0xD003900, 'BatchMediaAudioEvent', '%{public}s', text);
  }

  private reportFailure(event: string, error: BusinessError): void {
    this.failed = true;
    try {
      this.record(event, JSON.stringify({ code: error.code, message: error.message }));
    } catch (evidenceError) {
      // Disk failure remains a failed/missing independent artifact. Still clean up
      // the real task and subscriptions; never reject an unobserved timer Promise.
      hilog.error(0xD003900, 'BatchMediaAudioEvent', '%{public}s failed: %{public}s; evidence: %{public}s',
        event, JSON.stringify(error), JSON.stringify(evidenceError));
    }
  }

  private readonly onCancel = (info: backgroundTaskManager.ContinuousTaskCancelInfo): void => {
    try {
      this.record('continuous_task_cancel', JSON.stringify({ info: info, expected_stop: this.cleaning }));
    } finally {
      if (!this.cleaning && (this.taskId < 0 || info.id === this.taskId)) {
        this.failed = true;
        this.native.abort(this.runId);
      }
    }
  };

  private readonly onSuspend = (info: backgroundTaskManager.ContinuousTaskSuspendInfo): void => {
    try {
      this.record('continuous_task_suspend', JSON.stringify(info));
    } finally {
      if (!this.cleaning && (this.taskId < 0 || info.continuousTaskId === this.taskId) && info.suspendState) {
        this.failed = true;
        this.native.abort(this.runId);
      }
    }
  };

  notePage(event: string): void {
    this.record('page_' + event, 'UI lifecycle observation only; no foreground override');
  }

  private async waitForMicrophone(): Promise<void> {
    try {
      const action = this.mode === 1 ? 'focus_begin' : 'contender_start';
      const path = this.context.getApplicationContext().filesDir + '/audio-event-' + this.runId + '-' + action + '-ready.json';
      const deadline = Date.now() + 8000;
      while (!this.failed && Date.now() < deadline) {
        if (this.native.status(this.runId) !== 0) {
          throw new Error('Native stream finished before actual microphone readiness');
        }
        if (fs.accessSync(path)) {
          const ready = JSON.parse(fs.readTextSync(path)) as AudioEventReady;
          if (ready.run_id !== this.runId || ready.action !== action || ready.state_result !== 0 ||
            ready.state !== 2 || ready.frames_result !== 0 || ready.frames <= 0 || ready.copied_bytes <= 0) {
            throw new Error('Native microphone readiness has no real RUNNING PCM');
          }
          this.record('native_microphone_ready', JSON.stringify(ready));
          return;
        }
        await new Promise<void>((resolve) => { setTimeout(resolve, 20); });
      }
      throw new Error('Native microphone readiness timed out or task canceled');
    } catch (error) {
      const actual = error as BusinessError;
      // ArkTS requires a real Error. Preserve the original BusinessError fields
      // in its message even when the SDK rejected with a plain business object.
      throw new Error(JSON.stringify({ name: actual.name, code: actual.code,
        message: actual.message, stack: actual.stack, data: actual.data }));
    }
  }

  async start(microphoneGranted: boolean): Promise<void> {
    try {
      // Revocation mode stays foreground. Only the two focus actors need a task.
      const needsBackground: boolean = this.mode !== 0 && microphoneGranted;
      if (needsBackground) {
        const initiallyEnabled = await notificationManager.isNotificationEnabled();
        this.record('notification_initial', JSON.stringify({ enabled: initiallyEnabled }));
        if (!initiallyEnabled) {
          // The real user/permission controller answers; denial is not bypassed.
          await notificationManager.requestEnableNotification(this.context);
        }
        const enabled = await notificationManager.isNotificationEnabled();
        this.record('notification_authorized', JSON.stringify({ enabled: enabled }));
        if (!enabled) {
          throw new Error('Continuous-task notification remains disabled');
        }
        backgroundTaskManager.on('continuousTaskCancel', this.onCancel);
        this.subscribed = true;
        backgroundTaskManager.on('continuousTaskSuspend', this.onSuspend);
      }
      this.record('native_start_requested', JSON.stringify({ needs_background: needsBackground }));
      const accepted = this.native.run(this.runId, this.mode);
      this.nativeStarted = accepted;
      if (!accepted) {
        throw new Error('Native audio-event worker start rejected');
      }
      this.startedMs = Date.now();
      if (needsBackground) {
        await this.waitForMicrophone();
        const target = await wantAgent.getWantAgent({
          wants: [{ bundleName: this.context.abilityInfo.bundleName,
            abilityName: this.context.abilityInfo.name, moduleName: this.context.abilityInfo.moduleName }],
          operationType: wantAgent.OperationType.START_ABILITY,
          requestCode: this.mode,
          wantAgentFlags: [wantAgent.WantAgentFlags.CONSTANT_FLAG]
        });
        const notification = await backgroundTaskManager.startBackgroundRunning(this.context, ['audioRecording'], target);
        this.backgroundStarted = true;
        this.taskId = notification.continuousTaskId === undefined ? -1 : notification.continuousTaskId;
        this.record('background_started', JSON.stringify(notification));
        if (this.failed) {
          throw new Error('Continuous task was canceled or suspended during startup');
        }
      } else {
        this.record('background_not_requested', microphoneGranted ? 'foreground revocation mode' : 'actual microphone grant denied');
      }
      this.pollTimer = setInterval(() => { this.poll(); }, 100);
    } catch (error) {
      this.failed = true;
      const actual = error as BusinessError;
      try {
        this.record('startup_failed', JSON.stringify({ code: actual.code, message: actual.message }));
      } finally {
        if (this.nativeStarted) {
          this.native.abort(this.runId);
          this.pollTimer = setInterval(() => { this.poll(); }, 100);
        } else {
          this.finish(-1, false);
        }
      }
      throw new Error(JSON.stringify({ name: actual.name, code: actual.code,
        message: actual.message, stack: actual.stack, data: actual.data }));
    }
  }

  private poll(): void {
    if (this.cleaning) {
      return;
    }
    const actual = this.native.status(this.runId);
    if (actual !== 0) {
      this.finish(actual, false);
    } else if (Date.now() - this.startedMs > 60000) {
      this.failed = true;
      this.native.abort(this.runId);
      // Do not claim a stuck native call released its resources. Root must reject
      // and collect its worker/stream evidence; the notification is still stopped.
      this.finish(2, true);
    }
  }

  private async finish(nativeStatus: number, nativeStillRunning: boolean): Promise<void> {
    if (this.cleaning) {
      return;
    }
    this.cleaning = true;
    if (this.pollTimer >= 0) {
      clearInterval(this.pollTimer);
      this.pollTimer = -1;
    }
    try {
      try {
        this.record('native_finished', JSON.stringify({ native_status: nativeStatus,
          native_still_running: nativeStillRunning, background_failed: this.failed }));
      } catch (error) {
        this.failed = true;
        hilog.error(0xD003900, 'BatchMediaAudioEvent', 'Native completion evidence failed: %{public}s', JSON.stringify(error));
      }
      if (this.backgroundStarted) {
        // Matching public stop takes the actual UIAbility that owns this task.
        await backgroundTaskManager.stopBackgroundRunning(this.context);
        this.backgroundStarted = false;
        this.record('background_stopped', 'actual public stopBackgroundRunning Promise resolved');
      }
    } catch (error) {
      this.reportFailure('cleanup_failed', error as BusinessError);
    } finally {
      if (this.subscribed) {
        try {
          backgroundTaskManager.off('continuousTaskCancel', this.onCancel);
          this.record('background_cancel_observer_removed', 'actual SDK call returned');
        } catch (error) {
          this.reportFailure('cancel_observer_cleanup_failed', error as BusinessError);
        }
        try {
          backgroundTaskManager.off('continuousTaskSuspend', this.onSuspend);
          this.record('background_suspend_observer_removed', 'actual SDK call returned');
        } catch (error) {
          this.reportFailure('suspend_observer_cleanup_failed', error as BusinessError);
        }
      }
    }
  }
}

@Entry
@Component
struct Index {
  @State note: string = 'Ready for actual microphone focus/revocation audit';
  @State launched: boolean = false;
  private readonly runId: string = '__BATCH_MEDIA_AUDIO_EVENT_RUN_ID__';
  private readonly mode: number = __BATCH_MEDIA_AUDIO_EVENT_MODE__;
  private session?: AudioRecordingSession;

  private async startProbe(): Promise<void> {
    if (this.launched) {
      return;
    }
    this.launched = true;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const access = abilityAccessCtrl.createAtManager();
      const authorization = await access.requestPermissionsFromUser(context, ['ohos.permission.MICROPHONE']);
      const permissionEvidence = JSON.stringify({ run_id: this.runId, mode: this.mode,
        permissions: authorization.permissions, auth_results: authorization.authResults,
        dialog_shown_results: authorization.dialogShownResults });
      const evidencePath = context.getApplicationContext().filesDir + '/audio-event-' + this.runId + '-mode' + this.mode + '-permission.json';
      if (fs.accessSync(evidencePath)) {
        throw new Error('Existing microphone authorization evidence is preserved');
      }
      const evidenceFile = fs.openSync(evidencePath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
      try {
        fs.writeSync(evidenceFile.fd, permissionEvidence);
        fs.fsyncSync(evidenceFile.fd);
      } finally {
        fs.closeSync(evidenceFile);
      }
      hilog.info(0xD003900, 'BatchMediaAudioEvent', '%{public}s', permissionEvidence);
      const index = authorization.permissions.indexOf('ohos.permission.MICROPHONE');
      const granted = index >= 0 && authorization.authResults[index] === 0;
      this.session = new AudioRecordingSession(context, this.runId, this.mode, nativeProbe);
      await this.session.start(granted);
      this.note = 'Actual stream/task active; waiting for root nonce action and independent PCM verification';
    } catch (error) {
      this.note = 'Actual permission, background-task, or native startup failed';
      hilog.error(0xD003900, 'BatchMediaAudioEvent', '%{public}s:%{public}s', this.runId, JSON.stringify(error));
    }
  }

  build() {
    Column() {
      Text('Public Audio Focus / Revocation audit').fontSize(24)
      Text(this.note).fontSize(18)
      Button('Start audio audit').enabled(!this.launched).onClick(() => { this.startProbe(); })
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor(Color.White)
  }
}
