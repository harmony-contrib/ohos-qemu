/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import SeedStore, { SeedRequest } from '../model/SeedStore';

// The WindowStage passes this Ability instance's LocalStorage in loadContent.
@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('seedRequest') @Watch('onRequestChanged') private requestJson: string = '';
  @State private status: string = 'Waiting for a seed request';
  @State private busy: boolean = false;
  @State private valid: boolean = false;
  private request: SeedRequest = new SeedRequest();
  private operations: Set<string> = new Set();
  private generation: number = 0;

  aboutToAppear(): void { this.onRequestChanged(); }

  private identity(request: SeedRequest): string {
    return request.runId + '/' + request.operationId + '/' + request.mode;
  }

  private onRequestChanged(): void {
    ++this.generation;
    this.valid = false;
    try {
      const request = JSON.parse(this.requestJson) as SeedRequest;
      if (typeof request.runId !== 'string' || typeof request.operationId !== 'string' ||
          typeof request.mode !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(request.runId) ||
          !/^[A-Za-z0-9_-]{1,64}$/.test(request.operationId) ||
          !['create', 'cleanup'].includes(request.mode)) { throw new Error('Invalid seed request'); }
      this.request = request;
      if (this.busy) { this.status = 'Waiting for the previous operation'; return; }
      if (this.operations.has(request.runId + '/' + request.operationId)) {
        throw new Error('Operation already started');
      }
      this.valid = true;
      this.status = 'Ready: ' + this.identity(request);
    } catch (error) { this.status = 'Launch rejected: ' + (error as Error).message; }
  }

  private async start(): Promise<void> {
    if (!this.valid || this.busy) { return; }
    // Capture this launch. A later onNewWant must not redirect its CRUD/journal
    // or allow the old continuation to replace the new request's ready state.
    const request = this.request;
    const generation = this.generation;
    const key = request.runId + '/' + request.operationId;
    try {
      if (this.operations.has(key)) { throw new Error('Operation already started'); }
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const store = new SeedStore(context, request);
      this.operations.add(key);
      this.busy = true;
      this.valid = false;
      this.status = 'Running ' + this.identity(request);
      await store.execute();
      if (this.generation === generation) { this.status = 'Operation recorded'; }
    } catch (error) {
      if (this.generation === generation) { this.status = 'Operation failed: ' + (error as Error).message; }
    } finally {
      this.busy = false;
      if (this.generation !== generation) { this.onRequestChanged(); }
    }
  }
  build() {
    Column({ space: 16 }) {
      Text('Contacts public CRUD seed').fontSize(24)
      Text(this.status).id('contact_seed_status')
      Button('Run requested CRUD operation').id('contact_seed_start')
        .enabled(this.valid && !this.busy).onClick(() => this.start())
      Text('Contacts access requires the normal user permission dialog.')
    }.padding(24).width('100%').height('100%')
  }
}
