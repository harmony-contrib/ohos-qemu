/* SPDX-License-Identifier: Apache-2.0 */
import { common } from '@kit.AbilityKit';
import { CalendarAudit } from '../model/CalendarAudit';
@Entry({ useSharedStorage: true })
@Component
struct Index {
  @LocalStorageLink('calendarRequest') requestJson: string = '';
  @State status: string = 'Ready';
  private busy: boolean = false;
  private async execute(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    try {
      const audit = new CalendarAudit(getContext(this) as common.UIAbilityContext, this.requestJson);
      this.status = 'Running real public APIs';
      await audit.execute();
      this.status = 'Raw observations recorded';
    } catch (error) { this.status = (error as Error).message; }
    finally { this.busy = false; }
  }
  build() {
    Column({ space: 20 }) {
      Text('Calendar QA __ROLE__').fontSize(24)
      Text(this.status).id('calendar-qa-status')
      Button('Execute requested operation').id('calendar-qa-run').onClick(() => this.execute())
      Text('Only real API outcomes are recorded. No pass decision is made by this app.')
    }.padding(24).height('100%').width('100%')
  }
}
