// SPDX-License-Identifier: Apache-2.0
@Entry
@Component
struct ObserverDetail {
  private timer: number = -1;
  onPageShow(): void {
    this.timer = setTimeout(() => { this.getUIContext().getRouter().back(); }, 700);
  }
  aboutToDisappear(): void { clearTimeout(this.timer); }
  build() { Column() { Text('Actual observer child __RUN__') }.width('100%').height('100%') }
}
