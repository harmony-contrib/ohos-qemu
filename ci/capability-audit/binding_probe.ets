// SPDX-License-Identifier: Apache-2.0
// Binding classes are returned by the public SDK factory, not constructors.
import { UIUtils, Binding, MutableBinding } from '@ohos.arkui.StateManagement';
import fs from '@ohos.file.fs';

class Box { value: number = 0; }
interface Result { runId: string; name: string; values: number[]; checks: boolean[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Checking real data-binding factories';
  private readonly runId: string = '__BINDING_RUN_ID__';
  private readonly path: string = '/data/storage/el2/base/files/binding-__BINDING_RUN_ID__-results.log';
  private record(name: string, values: number[] = [], checks: boolean[] = [], error: string = ''): void {
    const row: Result = { runId: this.runId, name, values, checks, error };
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(row) + '\n'); fs.closeSync(file); this.note = name;
  }
  private generation(generation: number): void {
    const seed: number = parseInt(this.runId.substring(0, 4), 16) + generation * 100;
    let source: number = seed;
    let setters: number = 0;
    const first: Binding<number> = UIUtils.makeBinding<number>(() => source);
    const second: MutableBinding<number> = UIUtils.makeBinding<number>(() => source,
      (value: number) => { setters++; source = value; });
    const other: Binding<number> = UIUtils.makeBinding<number>(() => -seed);
    for (let step = 0; step <= 32; step++) {
      const value: number = seed + (step % 2 === 0 ? step : -step);
      second.value = value;
      this.record('number.' + generation + '.' + step,
        [first.value, second.value, other.value, source, setters],
        [first !== second, first !== other, second !== other]);
    }
    const original: Box = new Box(); original.value = seed;
    let objectSource: Box = original;
    const objectRead: Binding<Box> = UIUtils.makeBinding<Box>(() => objectSource);
    const objectWrite: MutableBinding<Box> = UIUtils.makeBinding<Box>(() => objectSource,
      (value: Box) => { objectSource = value; });
    const replacement: Box = new Box(); replacement.value = seed + 1;
    const before: boolean = objectRead.value === original && objectWrite.value === original;
    objectWrite.value = replacement;
    this.record('object.' + generation, [objectRead.value.value, objectWrite.value.value, original.value],
      [before, objectRead.value === replacement, objectWrite.value === replacement, original !== replacement]);
  }
  private boundaries(): void {
    const thrown: Error = new Error('binding-owned-' + this.runId);
    const read: Binding<number> = UIUtils.makeBinding<number>((): number => { throw thrown; });
    let caught: boolean = false;
    try { this.record('unexpected.getter-success', [read.value]); }
    catch (error) { caught = (error as Error) === thrown; }
    this.record('getter.exception', [], [caught]);
    let source: number = 17;
    const write: MutableBinding<number> = UIUtils.makeBinding<number>(() => source,
      (value: number) => { if (value < 0) { throw thrown; } source = value; });
    caught = false;
    try { write.value = -1; }
    catch (error) { caught = (error as Error) === thrown; }
    this.record('setter.exception', [write.value, source], [caught]);
    write.value = 31;
    this.record('setter.recovery', [write.value, source], [read !== write]);
  }
  private run(): void {
    try {
      for (let generation = 0; generation < 2; generation++) { this.generation(generation); }
      this.boundaries(); this.record('summary', [68, 3], [true]);
    } catch (error) { this.record('failed', [], [], (error as Error).message || 'exception'); }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
