// Candidate real lazy factory/typed modifier/visible-index behavior; no constructor aliases.
import { LazyColumnLayout, LazyColumnLayoutAttribute, LengthMetrics } from '@kit.ArkUI';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

interface Observation { runId: string; cycle: number; name: string; values: number[]; error: string; }
class Journal {
  static cycle: number = 0;
  static record(name: string, values: number[] = [], error: string = ''): void {
    const row: Observation = { runId: '__RUN__', cycle: Journal.cycle, name, values, error };
    const file = fs.openSync('/data/storage/el2/base/files/arkui-lazy-types-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
}
class ColumnModifier implements AttributeModifier<LazyColumnLayoutAttribute> {
  applyNormalAttribute(instance: LazyColumnLayoutAttribute): void {
    try {
      const reset = instance.space(undefined).alignItems(undefined).header(undefined)
        .footer(undefined).sticky(undefined).onVisibleIndexesChange(undefined) === instance;
      Journal.record('modifier.column.reset', [reset ? 1 : 0]);
      const same = instance.width(220).space(LengthMetrics.vp(4)).alignItems(HorizontalAlign.Start) === instance;
      Journal.record('modifier.column', [same ? 1 : 0]);
    } catch (error) { Journal.record('failed.modifier.column', [], String(error)); }
  }
}
@Entry
@ComponentV2
struct Index {
  @Local active: boolean = false;
  @Local cycle: number = 0;
  @Local removed: boolean = false;
  private readonly modifier: ColumnModifier = new ColumnModifier();
  private readonly scroller: Scroller = new Scroller();
  private readonly items: number[] = Array.from({ length: 40 }, (_: number, index: number) => index);
  build() {
    Column({ space: 12 }) {
      Text('__RUN__').id('arkui-lazy-types-ready')
      Button('Create lazy column').id('arkui-lazy-types-start').onClick(() => {
        if (!this.active) {
          if (this.removed) { this.cycle++; }
          Journal.cycle = this.cycle;
          Journal.record('identity', [process.uid, process.euid, process.pid]);
          Journal.record('create.request', [1]); this.removed = false; this.active = true;
        }
      })
      if (this.active) {
        Scroll(this.scroller) {
          LazyColumnLayout() {
            ForEach(this.items, (index: number) => {
              Text('__RUN__:' + index).id('arkui-lazy-types-item-' + index)
                .width(200).height(36).backgroundColor(index % 2 === 0 ? '#ddeeff' : '#aaccdd')
            }, (index: number) => String(index))
          }.attributeModifier(this.modifier).id('arkui-lazy-types-column')
            .onVisibleIndexesChange((start: number, end: number) => { Journal.record('visible.column', [start, end]); })
        }.width(240).height(200).scrollable(ScrollDirection.Vertical).id('arkui-lazy-types-scroll')
        Button('Scroll to last').id('arkui-lazy-types-last').onClick(() => {
          this.scroller.scrollEdge(Edge.Bottom); Journal.record('scroll.request.last', [1]);
        })
        Button('Scroll to first').id('arkui-lazy-types-first').onClick(() => {
          this.scroller.scrollEdge(Edge.Top); Journal.record('scroll.request.first', [1]);
        })
        Button('Remove lazy column').id('arkui-lazy-types-remove').onClick(() => {
          this.active = false; this.removed = true; Journal.record('remove.request', [1]);
        })
      }
      if (this.removed) {
        Text('removed __RUN__:' + this.cycle).id('arkui-lazy-types-removed')
      }
    }.width('100%').height('100%')
  }
}
