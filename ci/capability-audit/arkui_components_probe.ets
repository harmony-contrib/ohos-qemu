// Actual component factories and native layout, not constructor aliases.
import { ArcList, ArcListItem, ArcListAttribute, ArcListItemAttribute } from '@ohos.arkui.ArcList';
import { ArcScrollBar, ArcScrollBarAttribute } from '@ohos.arkui.ArcScrollBar';
import { DynamicLayout, DynamicLayoutAttribute } from '@ohos.arkui.components.ArkDynamicLayout';
import { RowLayoutAlgorithm, ColumnLayoutAlgorithm, LayoutAlgorithm } from '@kit.ArkUI';
import fs from '@ohos.file.fs';

interface Row {
  runId: string; name: string; phase: number; chained: boolean; values: number[]; error: string;
}
class Capture {
  static phase: number = 0;
  static readonly path: string = '/data/storage/el2/base/files/arkui-components-__RUN__-results.log';
  static record(name: string, chained: boolean = true, values: number[] = [], error: string = ''): void {
    const row: Row = { runId: '__RUN__', name, phase: Capture.phase, chained, values, error };
    const file = fs.openSync(Capture.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
}
class ListModifier implements AttributeModifier<ArcListAttribute> {
  applyNormalAttribute(instance: ArcListAttribute): void {
    try {
      const same = instance.width(220).height(180).scrollBar(BarState.Off) === instance;
      Capture.record('modifier.arc-list', same);
    } catch (error) { Capture.record('modifier.arc-list', false, [], String(error)); }
  }
}
class ItemModifier implements AttributeModifier<ArcListItemAttribute> {
  applyNormalAttribute(instance: ArcListItemAttribute): void {
    try {
      const same = instance.height(48).width('100%') === instance;
      Capture.record('modifier.arc-item', same);
    } catch (error) { Capture.record('modifier.arc-item', false, [], String(error)); }
  }
}
class BarModifier implements AttributeModifier<ArcScrollBarAttribute> {
  applyNormalAttribute(instance: ArcScrollBarAttribute): void {
    try {
      const same = instance.width(24).height(180).backgroundColor('#101010') === instance;
      Capture.record('modifier.arc-bar', same);
    } catch (error) { Capture.record('modifier.arc-bar', false, [], String(error)); }
  }
}
class DynamicModifier implements AttributeModifier<DynamicLayoutAttribute> {
  applyNormalAttribute(instance: DynamicLayoutAttribute): void {
    try {
      const same = instance.width(260).height(150).backgroundColor('#204060') === instance;
      Capture.record('modifier.dynamic', same);
    } catch (error) { Capture.record('modifier.dynamic', false, [], String(error)); }
  }
}

@Entry
@Component
struct Index {
  @State private phase: number = 0;
  @State private counter: number = 0;
  @State private algorithm: LayoutAlgorithm = new RowLayoutAlgorithm();
  private readonly scroller: Scroller = new Scroller();
  private readonly listModifier: ListModifier = new ListModifier();
  private readonly itemModifier: ItemModifier = new ItemModifier();
  private readonly barModifier: BarModifier = new BarModifier();
  private readonly dynamicModifier: DynamicModifier = new DynamicModifier();
  private start(): void {
    if (this.phase !== 0) { Capture.record('failed', false, [], 'duplicate start'); return; }
    Capture.phase = 1; Capture.record('ready.row'); this.phase = 1;
  }
  private change(): void {
    if (this.phase !== 1 || this.counter !== 1) {
      Capture.record('failed', false, [], 'real child click before layout switch required'); return;
    }
    Capture.phase = 2; Capture.record('switch.column', true, [this.counter]);
    this.algorithm = new ColumnLayoutAlgorithm(); this.phase = 2;
  }
  private child(): void {
    this.counter++;
    const child = this.getUIContext().getFrameNodeById('components-child-a');
    const parent = this.getUIContext().getFrameNodeById('components-dynamic');
    Capture.record('child.clicked', true, [this.counter, child?.getUniqueId() ?? -1, parent?.getUniqueId() ?? -1]);
  }
  aboutToAppear(): void {
    const file = fs.openSync(Capture.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); Capture.record('ready');
  }
  build() {
    Column({ space: 8 }) {
      Button('Start components').id('components-start').onClick(() => { this.start(); })
      if (this.phase > 0) {
        Row() {
          ArcList({ scroller: this.scroller }) {
            ForEach([0, 1, 2, 3, 4, 5, 6, 7], (index: number) => {
              ArcListItem() {
                Text('__RUN__ item ' + index).id('components-item-' + index)
                  .fontSize(14).fontColor('#FFFFFF').backgroundColor('#306020')
              }.attributeModifier(this.itemModifier)
            })
          }.attributeModifier(this.listModifier).id('components-arc-list')
            .onScrollIndex((start: number, end: number, center: number) => {
              Capture.record('arc.index', true, [start, end, center]);
            })
          ArcScrollBar({ scroller: this.scroller, state: BarState.On })
            .attributeModifier(this.barModifier).id('components-arc-bar')
        }
        Button('Scroll to last').id('components-scroll').onClick(() => {
          Capture.record('scroll.request'); this.scroller.scrollToIndex(7, false, ScrollAlign.CENTER);
        })
        DynamicLayout(this.algorithm) {
          Button('__RUN__ child A ' + this.counter).id('components-child-a')
            .width(100).height(50).backgroundColor('#B03020').onClick(() => { this.child(); })
          Text('__RUN__ child B').id('components-child-b')
            .width(100).height(50).backgroundColor('#20A030')
        }.attributeModifier(this.dynamicModifier).id('components-dynamic')
        Button('Switch row to column').id('components-switch').onClick(() => { this.change(); })
      }
    }.width('100%').height('100%').padding(8)
  }
}
