import { common, ServiceExtensionAbility, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { Journal, Request } from './Journal';
import { parameterBoundary } from './ParameterBoundary';

interface ConditionalServiceContext extends common.ServiceExtensionContext {
  terminateSelfIfStartId(expectedStartId: number): Promise<boolean>;
}

// A fixture-only retained closure preserves the OLD actual Context/token when
// the real host process survives a service-instance destruction. It does not
// substitute a replacement context. The owner must observe actual same PID and
// separate AMS record/token generations or leave this challenge unexecuted.
let retainedStop: (() => Promise<boolean>) | undefined = undefined;
let retainedGeneration: number = 0;
let creates: number = 0;

export default class IdleService extends ServiceExtensionAbility {
  private queue: Promise<void> = Promise.resolve();
  private initialStartId: number = 0;
  private latestStartId: number = 0;
  private generation: number = 0;
  private active: boolean = true;
  private last: Request | undefined = undefined;

  onCreate(want: Want): void {
    this.generation = ++creates;
    this.active = true;
  }
  onRequest(want: Want, startId: number): void {
    const request = Journal.request(want);
    if (!this.active || !Number.isInteger(startId) || startId <= 0) {
      throw new Error('actual live onRequest with positive startId required');
    }
    if (this.initialStartId === 0) { this.initialStartId = startId; }
    this.latestStartId = startId;
    this.last = request;
    Journal.write(this.context, request, 'request', 0,
      JSON.stringify({ startId, initialStartId: this.initialStartId, generation: this.generation }));
    this.queue = this.queue.then(() => this.execute(request, startId));
  }
  private async attempt(request: Request, expectedStartId: number): Promise<void> {
    const context = this.context as ConditionalServiceContext;
    Journal.write(context, request, 'stop.call', 0,
      JSON.stringify({ expectedStartId, latestStartId: this.latestStartId, generation: this.generation }));
    try {
      const stopped: boolean = await context.terminateSelfIfStartId(expectedStartId);
      Journal.write(context, request, 'stop.return', 0, JSON.stringify({ stopped, generation: this.generation }));
    } catch (error) {
      const e = error as BusinessError;
      Journal.write(context, request, 'stop.error', typeof e.code === 'number' ? e.code : -1,
        JSON.stringify({ message: e.message, generation: this.generation }));
    }
  }
  private async execute(request: Request, startId: number): Promise<void> {
    if (!this.active) { return; }
    Journal.write(this.context, request, 'work.begin', 0, JSON.stringify({ startId, generation: this.generation }));
    try {
      if (request.action === 'remember' || request.action === 'heartbeat') {
        // A real executed request, deliberately kept running until a later stop.
      } else if (request.action === 'stale') {
        await this.attempt(request, this.initialStartId);
      } else if (request.action === 'future') {
        await this.attempt(request, 2147483647);
      } else if (request.action === 'current') {
        await this.attempt(request, startId);
      } else if (request.action === 'parameters') {
        await parameterBoundary(this.context,
          (event: string, label: string, code: number, raw: string): void => {
            Journal.write(this.context, request, event, code, JSON.stringify({ label, raw }));
          });
      } else if (request.action === 'retain-context') {
        const oldContext = this.context as ConditionalServiceContext;
        const oldId: number = startId;
        retainedGeneration = this.generation;
        retainedStop = (): Promise<boolean> => oldContext.terminateSelfIfStartId(oldId);
        Journal.write(this.context, request, 'old-context.saved', 0,
          JSON.stringify({ startId: oldId, generation: retainedGeneration }));
      } else if (request.action === 'old-context-attempt') {
        if (retainedStop === undefined || retainedGeneration === this.generation) {
          throw new Error('actual earlier destroyed service Context not retained in this real process');
        }
        Journal.write(this.context, request, 'old-context.call', 0,
          JSON.stringify({ oldGeneration: retainedGeneration, currentGeneration: this.generation }));
        try {
          const stopped: boolean = await retainedStop();
          Journal.write(this.context, request, 'old-context.return', 0, JSON.stringify({ stopped }));
        } catch (error) {
          const e = error as BusinessError;
          Journal.write(this.context, request, 'old-context.error', typeof e.code === 'number' ? e.code : -1,
            JSON.stringify({ message: e.message }));
        }
      } else { throw new Error('unlisted real service action'); }
      Journal.write(this.context, request, 'work.end', 0, JSON.stringify({ startId, generation: this.generation }));
    } catch (error) {
      const e = error as BusinessError;
      Journal.write(this.context, request, 'work.error', typeof e.code === 'number' ? e.code : -1,
        JSON.stringify({ message: e.message, startId, generation: this.generation }));
    }
  }
  onDestroy(): void {
    this.active = false;
    if (this.last !== undefined) {
      Journal.write(this.context, this.last, 'destroy', 0,
        JSON.stringify({ latestStartId: this.latestStartId, generation: this.generation }));
    }
  }
}
