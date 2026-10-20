/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import Want from '@ohos.app.ability.Want';
import { Driver } from '../common/Driver';
import { Journal, ROLE } from '../common/Journal';

@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('uri579Want') @Watch('changed') serialized: string = '';
  @State ready: string = '';
  @State status: string = '';
  private driver: Driver | undefined = undefined;
  private busy: boolean = false;
  private lastOperation: string = '';
  private automatic: boolean = false;
  private changed(): void {
    if (this.serialized.length === 0) { return; }
    const want: Want = JSON.parse(this.serialized) as Want;
    const r = Journal.request(want);
    if (this.lastOperation === r.operation) { return; }
    this.lastOperation = r.operation;
    this.driver = new Driver(getContext(this) as common.UIAbilityContext, want, r);
    this.ready = r.run + '/' + r.operation + '/' + r.action;
    this.automatic = !['share','mms'].includes(r.action);
    if (this.automatic) { this.execute(); }
  }
  private async execute(): Promise<void> {
    if (this.busy || this.driver === undefined) { return; }
    const selected = this.driver;
    this.busy = true;
    try { await selected.execute(); this.status = 'Actual observations saved'; }
    catch (error) { this.status = (error as Error).message; }
    finally {
      this.busy = false;
      // A new actual Want can arrive while the prior request is completing.
      // Continue that single pending request instead of dropping onNewWant.
      if (this.driver !== selected && this.automatic) { this.execute(); }
    }
  }
  aboutToAppear(): void { this.changed(); }
  build() {
    Column({ space: 18 }) {
      Text('URI579 __ROLE__ __RUN__')
      Text(this.ready).id('uri579-ready')
      Text(this.status).id('uri579-status')
      Button('Invoke actual API').id('uri579-run').onClick(() => this.execute())
      if (ROLE !== 'owner') {
        Button('Close this actual receiver').id('uri579-close').onClick(() => this.driver?.close())
      }
    }.padding(24).height('100%').width('100%')
  }
}
