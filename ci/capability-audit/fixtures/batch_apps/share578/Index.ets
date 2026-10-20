/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import { ShareAudit } from '../model/ShareAudit';
import { MmsAudit } from '../model/MmsAudit';
interface ActiveAudit { identity(): string; execute(): Promise<void>; finish(): void; }
@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('share578Want') @Watch('wantChanged') wantJson: string = '';
  @State status: string = 'No owned request';
  @State ready: string = '';
  private busy: boolean = false;
  private activeAudit: ActiveAudit | undefined = undefined;
  private activeWant: string = '';
  private readonly role: string = '__ROLE__';
  private isMms(): boolean {
    const want = JSON.parse(this.wantJson) as Record<string, Object>;
    const parameters = want['parameters'] as Record<string, string>;
    const request = JSON.parse(parameters['request']) as Record<string, string>;
    return request['case_id'] === 'mms-file-cancel';
  }
  private wantChanged(): void { if (!this.busy) { this.showReady(); } }
  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    this.activeWant = this.wantJson;
    try {
      const audit: ActiveAudit = this.isMms() ? new MmsAudit(getContext(this) as common.UIAbilityContext, this.wantJson) :
        new ShareAudit(getContext(this) as common.UIAbilityContext, this.wantJson);
      this.activeAudit = audit;
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
      this.ready = this.isMms() ? MmsAudit.ready(this.wantJson) : ShareAudit.ready(this.wantJson);
      this.status = 'Ready ' + this.ready;
      // Targets consume only the actual incoming Want. No HDC command grants
      // them a URI; foreign probes carry URI text only and no authorization.
      if (this.role !== 'caller') { this.execute(); }
    } catch (error) { this.status = (error as Error).message; }
  }
  aboutToAppear(): void { this.showReady(); }
  build() {
    Column({ space: 18 }) {
      Text('Share578 __ROLE__ __RUN__').fontSize(20)
      Text(this.ready).id('share578-ready')
      Text(this.status).id('share578-status')
      if (this.role === 'caller') {
        Button('Execute real modal share').id('share578-run').onClick(() => this.execute())
        Button('Cleanup completed share payload').id('share578-cleanup').onClick(() => this.activeAudit?.finish())
      }
    }.padding(24).height('100%').width('100%')
  }
}
