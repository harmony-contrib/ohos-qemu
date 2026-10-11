// Real physical-input hover callbacks; never invoke the callback ourselves.
import drag from '@ohos.arkui.dragController';
import data from '@ohos.data.unifiedDataChannel';
import fs from '@ohos.file.fs';

interface Row {
  runId: string; name: string; generation: number; state: number; sequence: number;
  instance: boolean; config: number[]; summarySize: number; count: number;
  time: number; error: string; infosOmitted: boolean;
}

@Entry
@Component
struct Index {
  @State private mode: number = 0;
  @State private note: string = 'Choose a real drag cycle';
  private generation: number = 0;
  private count: number = 0;
  private started: boolean = false;
  private readonly path: string = '/data/storage/el2/base/files/spring-loading-__RUN__-results.log';
  private record(name: string, state: number = -1, sequence: number = -1, instance: boolean = true,
    config: number[] = [], summarySize: number = -1, error: string = '', infosOmitted: boolean = false): void {
    const row: Row = { runId: '__RUN__', name, generation: this.generation, state, sequence, instance,
      config, summarySize, count: this.count, time: Date.now(), error, infosOmitted };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private config(context: drag.SpringLoadingContext): number[] {
    const config = context.currentConfig;
    if (config === undefined) { return []; }
    return [config.stillTimeLimit ?? -1, config.updateInterval ?? -1,
      config.updateNotifyCount ?? -1, config.updateToFinishInterval ?? -1];
  }
  private callback(context: drag.SpringLoadingContext): void {
    this.count++;
    try {
      const infos = context.dragInfos;
      const size = infos?.dataSummary?.totalSize ?? -1;
      const omitted = infos === undefined;
      this.record('callback', context.state, context.currentNotifySequence,
        context instanceof drag.SpringLoadingContext, this.config(context), size, '', omitted);
      if (context.state === drag.DragSpringLoadingState.BEGIN) {
        if (this.mode === 2) {
          context.abort();
          this.record('abort.called', context.state, context.currentNotifySequence,
            context instanceof drag.SpringLoadingContext, this.config(context), size, '', omitted);
        } else if (this.mode === 1) {
          context.updateConfiguration({ stillTimeLimit: 150, updateInterval: 200,
            updateNotifyCount: 2, updateToFinishInterval: 200 });
          this.record('begin.updated', context.state, context.currentNotifySequence,
            context instanceof drag.SpringLoadingContext, this.config(context), size, '', omitted);
        }
      } else {
        // SDK requires this call to have no effect outside BEGIN.
        context.updateConfiguration({ stillTimeLimit: 0, updateInterval: 0,
          updateNotifyCount: 0, updateToFinishInterval: 0 });
        this.record('outside-begin.ignored', context.state, context.currentNotifySequence,
          context instanceof drag.SpringLoadingContext, this.config(context), size, '', omitted);
      }
    } catch (error) { this.record('failed', -1, -1, false, [], -1, String(error)); }
  }
  private choose(mode: number): void {
    this.mode = mode; this.generation++; this.count = 0;
    this.note = 'Generation ' + this.generation + ', mode ' + mode;
    this.record('ready.' + mode);
  }
  private quiet(): void {
    this.record('quiet.begin');
    setTimeout(() => { this.record('quiet.end'); }, 1500);
  }
  aboutToAppear(): void {
    if (this.started) { return; } this.started = true;
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file);
    try {
      const first = new drag.SpringLoadingContext();
      const second = new drag.SpringLoadingContext();
      const valid = first instanceof drag.SpringLoadingContext && second instanceof drag.SpringLoadingContext &&
        first !== second && typeof first.abort === 'function' && typeof first.updateConfiguration === 'function';
      first.abort(); first.updateConfiguration({ updateNotifyCount: 0 });
      this.record('constructor', -1, -1, valid);
    } catch (error) { this.record('failed', -1, -1, false, [], -1, String(error)); }
  }
  build() {
    Column({ space: 12 }) {
      Text(this.note).id('spring-note')
      Row({ space: 8 }) {
        Button('Normal').id('spring-mode-normal').onClick(() => { this.choose(1); })
        Button('Abort').id('spring-mode-abort').onClick(() => { this.choose(2); })
        Button('Cancel').id('spring-mode-cancel').onClick(() => { this.choose(3); })
      }
      // A generic draggable source exercises physical dragging directly. Text
      // has separate mouse-selection prerequisites; an unselected Text never
      // starts a drag and cannot test the SpringLoading lifecycle at all.
      Column() { Text('Drag the nonce data') }
        .id('spring-source').width('80%').height(100)
        .backgroundColor('#206080').draggable(true)
        .onDragStart((event: DragEvent): DragItemInfo => {
          const text = new data.PlainText(); text.textContent = '__RUN__';
          event.setData(new data.UnifiedData(text)); this.record('drag.started');
          return { extraInfo: '__RUN__' };
        })
        .onDragEnd(() => { this.record('drag.ended'); })
      Text('Hold inside this real target').id('spring-target').width('80%').height(160)
        .backgroundColor('#804020')
        .onDrop(() => { this.record('drop'); })
        .onDragSpringLoading((context: drag.SpringLoadingContext) => { this.callback(context); },
          { stillTimeLimit: 150, updateInterval: this.mode === 3 ? 10000 : 100,
            updateNotifyCount: 2, updateToFinishInterval: 100 })
      Button('Check quiet interval').id('spring-quiet').onClick(() => { this.quiet(); })
    }.width('100%').height('100%').padding(12)
  }
}
