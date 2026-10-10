// SPDX-License-Identifier: Apache-2.0
import hidebug from '@ohos.hidebug';
import fs from '@ohos.file.fs';
import native from 'libgraphicsmemoryprobe.so';

interface Row {
  runId: string; phase: number; native: number[]; gl: number; graph: number; total: number;
  publicTypes: string[]; publicValues: string[]; error: string;
}

@Entry
@Component
struct Index {
  @State private note: string = 'Real graphics memory accounting';
  private readonly resultPath: string = '/data/storage/el2/base/files/graphics-memory-__RUN__-results.log';
  private record(row: Row): void {
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
  }
  private async run(): Promise<void> {
    try {
      for (let phase = 0; phase <= 4; phase++) {
        if (phase > 0 && native.action(phase) !== phase) throw new Error('buffer action failed');
        // Public API's minimum cache age is two seconds; do not read stale accounting.
        await new Promise<void>((resolve) => { setTimeout(resolve, 3100); });
        const values: number[] = native.snapshot();
        const summary: hidebug.GraphicsMemorySummary = await hidebug.getGraphicsMemorySummary(2);
        const total: number = await hidebug.getGraphicsMemory();
        // Retain wrong public types as diagnostic strings, never coerce them into a passing number.
        // Continue the allocation lifecycle so an independent NDK/backend failure is not hidden.
        this.record({ runId: '__RUN__', phase, native: values,
          gl: typeof summary.gl === 'number' ? summary.gl : -1,
          graph: typeof summary.graph === 'number' ? summary.graph : -1,
          total: typeof total === 'number' ? total : -1,
          publicTypes: [typeof summary.gl, typeof summary.graph, typeof total],
          publicValues: [String(summary.gl), String(summary.graph), String(total)], error: '' });
      }
      this.record({ runId: '__RUN__', phase: 5, native: [], gl: 0, graph: 0, total: 0,
        publicTypes: [], publicValues: [], error: '' });
      this.note = 'Accounting capture complete';
    } catch (error) {
      this.record({ runId: '__RUN__', phase: -1, native: [], gl: 0, graph: 0, total: 0,
        publicTypes: [], publicValues: [], error: (error as Error).message || 'graphics memory exception' });
    }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
