/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import SeedStore, { SeedRequest } from '../model/SeedStore';

@Entry
@Component
struct Index {
  @LocalStorageLink('seedRequest') private requestJson: string = '';
  @State private status: string = 'Ready';
  private busy: boolean = false;
  private operations: Set<string> = new Set();
  private async start(): Promise<void> {
    if (this.busy) { return; }
    try {
      const request = JSON.parse(this.requestJson) as SeedRequest;
      const key = request.runId + '/' + request.operationId;
      if (this.operations.has(key)) { throw new Error('Operation already started'); }
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const store = new SeedStore(context, request);
      this.operations.add(key);
      this.busy = true;
      this.status = 'Running ' + request.mode;
      await store.execute();
      this.status = 'Operation recorded';
    } catch (error) { this.status = (error as Error).message; }
    finally { this.busy = false; }
  }
  build() {
    Column({ space: 16 }) {
      Text('Contacts public CRUD seed').fontSize(24)
      Text(this.status).id('contact_seed_status')
      Button('Run requested CRUD operation').id('contact_seed_start').onClick(() => this.start())
      Text('Contacts access requires the normal user permission dialog.')
    }.padding(24).width('100%').height('100%')
  }
}
