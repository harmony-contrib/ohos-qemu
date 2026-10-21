import ServiceExtensionAbility from '@ohos.app.ability.ServiceExtensionAbility';
import { Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import settings from '@ohos.settings';
import util from '@ohos.util';
import { CaptionSession } from '../common/CaptionSession';
import { captionTrace } from '../common/CaptionTrace';

class ServiceEpoch {
  static owner: string = '';
}
const ENABLED_KEY: string = 'vassistant_ai_caption_enable';
const CLOSE_URI: string = 'ohos://vassistant/caption?action=close';

export default class AiCaptionServiceExtAbility extends ServiceExtensionAbility {
  private readonly instance: string = util.generateRandomUUID();
  private destroyed: boolean = false;
  private generation: number = 0;
  private desiredOpen: boolean = false;
  private latestStartId: number = 0;
  private activeSession: CaptionSession | undefined = undefined;
  private queue: Promise<void> = Promise.resolve();
  onCreate(want: Want): void {
    ServiceEpoch.owner = this.instance;
    // The user-table key describes the visible requested caption session, not
    // ASR/capture success. Native running/result counters remain separate.
    this.setEnabled(false);
    this.context.getApplicationContext().setSupportedProcessCache(false);
    captionTrace(this.instance, 'service_created', 0, 0, 0);
  }
  onRequest(want: Want, startId: number): void {
    this.latestStartId = startId;
    if (!Number.isInteger(startId) || startId <= 0 ||
      (want.uri !== undefined && want.uri !== '' && want.uri !== CLOSE_URI)) {
      captionTrace(this.instance, 'request_rejected', 0, 0, 0, startId);
      if (!this.desiredOpen && this.activeSession === undefined && startId > 0) {
        const idleGeneration: number = this.generation;
        this.enqueue(async (): Promise<void> => { await this.stopIfCurrent(startId, idleGeneration); });
      }
      return;
    }
    const close: boolean = want.uri === CLOSE_URI;
    this.desiredOpen = !close;
    captionTrace(this.instance, close ? 'request_close' : 'request_open', 0, 0, 0, startId);
    const generation: number = ++this.generation;
    // Cancellation is synchronous. New onRequest invalidates old native/UI
    // callbacks before any awaited cleanup/initialization can complete.
    this.activeSession?.cancel();
    this.enqueue(async (): Promise<void> => {
      await this.releaseActive();
      if (!this.current(generation)) { return; }
      this.setEnabled(false);
      if (close) { await this.stopIfCurrent(startId, generation); return; }
      const id: string = util.generateRandomUUID();
      const session = new CaptionSession(id, this.context,
        (): void => { this.stopSession(session, startId, generation); },
        (): void => { if (this.current(generation) && this.activeSession === session) { this.setEnabled(true); } },
        (reason: Error): void => { this.failSession(session, startId, generation, reason); });
      this.activeSession = session;
      try { await session.start(); }
      catch (error) {
        if (this.current(generation) && this.activeSession === session) {
          this.failSession(session, startId, generation, error as Error);
        }
      }
    });
  }
  private current(generation: number): boolean {
    return !this.destroyed && ServiceEpoch.owner === this.instance && this.generation === generation;
  }
  private setEnabled(value: boolean): void {
    if (ServiceEpoch.owner !== this.instance) { return; }
    if (!settings.setValueSync(this.context, ENABLED_KEY, value ? 'true' : 'false', settings.domainName.USER_PROPERTY)) {
      throw new Error('actual user caption state write failed');
    }
  }
  private enqueue(operation: () => Promise<void>): void {
    // A real error is logged; later requests still reach the cleanup path.
    this.queue = this.queue.then(operation).catch((error: BusinessError): void => {
      captionTrace(this.instance, 'service_error', 0, 0, 0, error.code || -1);
    });
  }
  private async releaseActive(): Promise<void> {
    const prior = this.activeSession;
    if (prior !== undefined) { await prior.stop(); }
    if (this.activeSession === prior) { this.activeSession = undefined; }
  }
  private stopSession(session: CaptionSession, startId: number, generation: number): void {
    if (!this.current(generation) || this.activeSession !== session) { return; }
    session.cancel(); this.desiredOpen = false; this.setEnabled(false);
    const idleStartId: number = this.latestStartId;
    const stoppedGeneration: number = ++this.generation;
    this.enqueue(async (): Promise<void> => {
      await this.releaseActive();
      if (this.current(stoppedGeneration)) { await this.stopIfCurrent(idleStartId, stoppedGeneration); }
    });
  }
  private failSession(session: CaptionSession, startId: number, generation: number, reason: Error): void {
    if (!this.current(generation) || this.activeSession !== session) { return; }
    captionTrace(session.id, 'session_error', 0, 0, 0, (reason as BusinessError).code || -1);
    this.stopSession(session, startId, generation);
  }
  private async stopIfCurrent(startId: number, generation: number): Promise<void> {
    if (!this.current(generation) || this.latestStartId !== startId || this.activeSession !== undefined) { return; }
    const accepted: boolean = await this.context.terminateSelfIfStartId(startId);
    // false means newer real AMS work exists; preserve it, never fall back to
    // the unconditioned terminateSelf API.
    captionTrace(this.instance, 'conditional_stop', 0, 0, 0, accepted ? startId : -startId);
  }
  onDestroy(): void {
    this.destroyed = true; this.desiredOpen = false; ++this.generation;
    this.activeSession?.cancel();
    if (ServiceEpoch.owner === this.instance) {
      this.setEnabled(false); ServiceEpoch.owner = '';
    }
    // No asynchronous old-generation state write can clobber a new instance.
    this.enqueue(async (): Promise<void> => { await this.releaseActive(); });
    captionTrace(this.instance, 'service_destroyed', 0, 0, 0, this.latestStartId);
  }
}
