/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import { SelectAudit } from '../model/SelectAudit';
@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('select375Want') @Watch('wantChanged') wantJson: string = '';
  @State status: string = 'No owned request';
  @State ready: string = '';
  private busy: boolean = false;
  private activeWant: string = '';
  private wantChanged(): void { if (!this.busy) { this.showReady(); } }
  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    this.activeWant = this.wantJson;
    try {
      const audit = new SelectAudit(getContext(this) as common.UIAbilityContext, this.wantJson);
      this.ready = audit.identity();
      this.status = 'Running real APIs';
      await audit.execute();
      this.status = 'Raw observations recorded';
    } catch (error) { this.status = (error as Error).message; }
    finally {
      this.busy = false;
      if (this.wantJson !== this.activeWant) { this.showReady(); }
    }
  }
  private showReady(): void {
    try {
      this.ready = SelectAudit.ready(this.wantJson);
      this.status = 'Ready ' + this.ready;
      // Targets consume only the actual incoming Want. No HDC command grants
      // them a URI; foreign probes carry URI text only and no authorization.
      if ('__ROLE__' !== 'caller') { this.execute(); }
    } catch (error) { this.status = (error as Error).message; }
  }
  aboutToAppear(): void { this.showReady(); }
  build() {
    Column({ space: 18 }) {
      Text('Select375 __ROLE__ __RUN__').fontSize(20)
      Text(this.ready).id('select375-ready')
      Text(this.status).id('select375-status')
      if ('__ROLE__' === 'caller') {
        Button('Execute owned select case').id('select375-run').onClick(() => this.execute())
      }
    }.padding(24).height('100%').width('100%')
  }
}
