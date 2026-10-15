// Real API26 lazy layout factories, modifiers and native custom-layout callbacks.
import { LazyDynamicLayout, LazyDynamicLayoutAttribute, LazyCustomLayoutAlgorithm, LazyLayoutAlgorithm,
  LazyLayoutHelper, FrameNode, LayoutConstraint, Position, LengthMetrics,
  LazyVWaterFlowLayout, LazyVWaterFlowLayoutAttribute, LazyWaterFlowLayoutAttribute } from '@kit.ArkUI';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

interface Observation { runId: string; kind: string; cycle: number; name: string; values: number[]; error: string; }
class Journal {
  static kind: string = 'none';
  static cycle: number = 0;
  static record(name: string, values: number[] = [], error: string = ''): void {
    const row: Observation = { runId: '__RUN__', kind: Journal.kind, cycle: Journal.cycle, name, values, error };
    const file = fs.openSync('/data/storage/el2/base/files/arkui-lazy-layouts-__RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
}
class WaterModifier implements AttributeModifier<LazyVWaterFlowLayoutAttribute> {
  applyNormalAttribute(instance: LazyVWaterFlowLayoutAttribute): void {
    try {
      const base: LazyWaterFlowLayoutAttribute<LazyVWaterFlowLayoutAttribute> = instance;
      const reset = base.rowsGap(undefined).columnsGap(undefined).header(undefined).footer(undefined)
        .sticky(undefined).onVisibleIndexesChange(undefined) === instance;
      Journal.record('modifier.water.reset', [reset ? 1 : 0]);
      const chained = base.rowsGap(LengthMetrics.vp(4)).columnsGap(LengthMetrics.vp(4))
        .columnsTemplate('1fr 1fr').width(240) === instance;
      Journal.record('modifier.water', [chained ? 1 : 0]);
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
}
class DynamicModifier implements AttributeModifier<LazyDynamicLayoutAttribute> {
  applyNormalAttribute(instance: LazyDynamicLayoutAttribute): void {
    try {
      const reset = instance.onVisibleIndexesChange(undefined) === instance;
      Journal.record('modifier.dynamic.reset', [reset ? 1 : 0]);
      const chained = instance.width(240) === instance;
      Journal.record('modifier.dynamic', [chained ? 1 : 0]);
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
}
@ObservedV2
class RealColumnAlgorithm extends LazyCustomLayoutAlgorithm {
  private step: number;
  private count: number = 0;
  constructor(step: number) { super({ axis: Axis.Vertical }); this.step = step; }
  onMeasure(self: FrameNode, constraint: LayoutConstraint, helper?: LazyLayoutHelper): void {
    try {
      this.count = self.getChildrenCount();
      const row = vp2px(this.step);
      const inactive: number[] = [];
      for (let index = 0; index < this.count; index++) {
        const child = self.getChild(index);
        child?.measure({ maxSize: { width: constraint.maxSize.width, height: row },
          minSize: { width: 0, height: 0 }, percentReference: { width: constraint.maxSize.width, height: row } });
        if (helper !== undefined && ((index + 1) * row <= helper.getViewStart() || index * row >= helper.getViewEnd())) {
          inactive.push(index);
        }
      }
      if (helper !== undefined) {
        helper.setAdjustedOffset(0); helper.setChildrenInactive(inactive);
        Journal.record('algorithm.measure', [this.step, this.count, Math.round(helper.getViewStart()),
          Math.round(helper.getViewEnd()), helper.getLazyLayoutDirection(), inactive.length]);
      } else { Journal.record('algorithm.no-helper', [this.step, this.count]); }
      self.setMeasuredSize({ width: constraint.maxSize.width, height: this.count * row });
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
  onLayout(self: FrameNode, position: Position): void {
    try {
      const row = vp2px(this.step);
      for (let index = 0; index < this.count; index++) { self.getChild(index)?.layout({ x: 0, y: index * row }); }
      self.setLayoutPosition(position); Journal.record('algorithm.layout', [this.step, this.count]);
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
}
@Entry
@ComponentV2
struct Index {
  @Local kind: string = 'none';
  @Local cycle: number = 0;
  private lastKind: string = 'none';
  @Local columns: string = '1fr 1fr';
  @Local algorithm: LazyLayoutAlgorithm | undefined = undefined;
  private readonly water: WaterModifier = new WaterModifier();
  private readonly dynamic: DynamicModifier = new DynamicModifier();
  private readonly scroller: Scroller = new Scroller();
  private readonly items: number[] = Array.from({ length: 40 }, (_: number, index: number) => index);
  private startLayout(kind: string): void {
    if (this.kind !== 'none') { Journal.record('failed', [], 'live layout must be removed first'); return; }
    try {
      if (kind !== this.lastKind) { this.cycle = 0; }
      this.lastKind = kind;
      Journal.kind = kind; Journal.cycle = this.cycle;
      this.columns = '1fr 1fr'; this.algorithm = kind === 'dynamic' ? new RealColumnAlgorithm(40) : undefined;
      Journal.record('identity', [process.uid, process.euid, process.pid]); Journal.record('create.request', [1]); this.kind = kind;
    } catch (error) { Journal.record('failed', [], String(error)); }
  }
  build() {
    Column({ space: 8 }) {
      Text('__RUN__').id('lazy-layouts-ready')
      Row({ space: 8 }) {
        Button('Create water').id('lazy-layouts-water').onClick(() => { this.startLayout('water'); })
        Button('Create dynamic').id('lazy-layouts-dynamic').onClick(() => { this.startLayout('dynamic'); })
      }
      if (this.kind !== 'none') {
        Scroll(this.scroller) {
          if (this.kind === 'water') {
            LazyVWaterFlowLayout() {
              ForEach(this.items, (index: number) => {
                Text('__RUN__:' + index).id('lazy-layouts-item-' + index).width('100%')
                  .height(36 + (index % 3) * 12).fontSize(12)
                  .backgroundColor(index % 2 === 0 ? '#ddeeff' : '#aaccdd')
              }, (index: number) => String(index))
            }.attributeModifier(this.water).columnsTemplate(this.columns).id('lazy-layouts-water-factory')
              .onVisibleIndexesChange((start: number, end: number) => { Journal.record('visible.water', [start, end]); })
          } else if (this.algorithm !== undefined) {
            LazyDynamicLayout(this.algorithm) {
              ForEach(this.items, (index: number) => {
                Text('__RUN__:' + index).id('lazy-layouts-item-' + index).width(220).height(36).fontSize(12)
                  .backgroundColor(index % 2 === 0 ? '#ddeeff' : '#aaccdd')
              }, (index: number) => String(index))
            }.attributeModifier(this.dynamic).id('lazy-layouts-dynamic-factory')
              .onVisibleIndexesChange((indices: number[]) => { Journal.record('visible.dynamic', indices); })
          }
        }.width(260).height(200).scrollable(ScrollDirection.Vertical).id('lazy-layouts-scroll')
        Row({ space: 8 }) {
          Button('Bottom').id('lazy-layouts-last').onClick(() => {
            Journal.record('nodes.change.after', [this.getUIContext().getFrameNodeById('lazy-layouts-item-0')?.getUniqueId() ?? -1,
              this.getUIContext().getFrameNodeById('lazy-layouts-' + this.kind + '-factory')?.getUniqueId() ?? -1]);
            this.scroller.scrollEdge(Edge.Bottom); Journal.record('scroll.request.last', [1]);
          })
          Button('Top').id('lazy-layouts-first').onClick(() => {
            this.scroller.scrollEdge(Edge.Top); Journal.record('scroll.request.first', [1]);
          })
          Button('Change layout').id('lazy-layouts-change').onClick(() => {
            Journal.record('nodes.change.before', [this.getUIContext().getFrameNodeById('lazy-layouts-item-0')?.getUniqueId() ?? -1,
              this.getUIContext().getFrameNodeById('lazy-layouts-' + this.kind + '-factory')?.getUniqueId() ?? -1]);
            if (this.kind === 'water') { this.columns = '1fr 1fr 1fr'; }
            else { this.algorithm = new RealColumnAlgorithm(60); }
            Journal.record('change.request', [1]);
          })
        }
        Button('Remove layout').id('lazy-layouts-remove').onClick(() => {
          Journal.record('remove.request', [1]); this.kind = 'none'; this.cycle++;
        })
      } else {
        Text('removed __RUN__:' + this.cycle).id('lazy-layouts-removed')
      }
    }.width('100%').height('100%')
  }
}
