// SPDX-License-Identifier: Apache-2.0
// Observe actual routed pages. No synthetic observer objects or constructor shim.
import observer from '@ohos.arkui.observer';
import fs from '@ohos.file.fs';

interface Row {
  runId: string; name: string; listener: string; generation: number;
  phase: number; index: number; pageName: string; path: string;
  state: number; pageId: string; contextMatches: boolean; counts: number[];
}

@Entry
@Component
struct Index {
  @State private note: string = 'Observing real router lifecycle';
  private generation: number = 0;
  private phase: number = 0;
  private counts: number[] = [0, 0];
  private started: boolean = false;
  private readonly resultPath: string = '/data/storage/el2/base/files/router-observer-__RUN__-results.log';
  private record(row: Row): void {
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file);
  }
  private marker(name: string): void {
    this.record({ runId: '__RUN__', name, listener: '', generation: this.generation,
      phase: this.phase, index: 0, pageName: '', path: '', state: 0, pageId: '',
      contextMatches: true, counts: [this.counts[0], this.counts[1]] });
    this.note = name;
  }
  private callback(listener: string, slot: number, info: observer.RouterPageInfo): void {
    this.counts[slot]++;
    this.record({ runId: '__RUN__', name: 'event', listener, generation: this.generation,
      phase: this.phase, index: info.index, pageName: info.name, path: info.path,
      state: info.state, pageId: info.pageId, contextMatches: info.context === this.getUIContext(),
      counts: [this.counts[0], this.counts[1]] });
  }
  private delay(ms: number): Promise<void> {
    return new Promise<void>((resolve: () => void) => { setTimeout(resolve, ms); });
  }
  private async roundTrip(): Promise<void> {
    await this.getUIContext().getRouter().pushUrl({ url: 'pages/ObserverDetail' });
    await this.delay(2000);
    if (this.getUIContext().getRouter().getLength() !== '1') {
      throw new Error('real routed child did not return');
    }
  }
  private async run(): Promise<void> {
    const context = this.getUIContext();
    const first = (info: observer.RouterPageInfo): void => { this.callback('a', 0, info); };
    const second = (info: observer.RouterPageInfo): void => { this.callback('b', 1, info); };
    try {
      await this.delay(500);
      for (this.generation = 0; this.generation < 2; this.generation++) {
        this.counts = [0, 0]; this.phase = 0;
        observer.on('routerPageUpdate', context, first);
        observer.on('routerPageUpdate', context, second);
        this.marker('registered');
        await this.roundTrip(); this.marker('both-returned');
        observer.off('routerPageUpdate', context, first);
        this.phase = 1; this.marker('first-removed');
        await this.roundTrip(); this.marker('second-returned');
        observer.off('routerPageUpdate', context);
        this.phase = 2; this.marker('all-removed');
        await this.roundTrip(); this.marker('unsubscribed-returned');
      }
      this.marker('summary');
    } catch (error) { this.marker('failed'); }
    finally { observer.off('routerPageUpdate', context); }
  }
  aboutToAppear(): void {
    if (this.started) { return; }
    this.started = true;
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
