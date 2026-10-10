// SPDX-License-Identifier: Apache-2.0
import trace from '@ohos.hiTraceMeter';
import process from '@ohos.process';
import fs from '@ohos.file.fs';
import native from 'libhitraceprobe.so';

interface Row { runId: string; name: string; values: number[]; error: string; }

@Entry
@Component
struct Index {
  @State private note: string = 'Actual public HiTrace calls';
  private readonly resultPath: string = '/data/storage/el2/base/files/hitrace-__RUN__-results.log';
  private record(name: string, values: number[], error: string = ''): void {
    const row: Row = { runId: '__RUN__', name, values, error };
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(row) + '\n'); } finally { fs.closeSync(file); }
    this.note = name;
  }
  private run(): void {
    try {
      this.record('identity', [process.pid, process.uid, process.euid]);
      for (let generation = 0; generation < 2; generation++) {
        this.record('native.' + generation, native.run('__RUN__', generation));
        const prefix = 'oqht-__RUN__-a' + generation;
        const enabled = trace.isTraceEnabled();
        trace.startTrace(prefix + '-async', 0);
        trace.startTrace(prefix + '-async', 2147483647);
        trace.traceByValue(prefix + '-count', -2147483649);
        trace.traceByValue(prefix + '-count', 0);
        trace.traceByValue(prefix + '-count', 2147483648);
        trace.finishTrace(prefix + '-async', 2147483647);
        trace.finishTrace(prefix + '-async', 0);
        this.record('arkts.' + generation, [enabled ? 1 : 0]);
      }
      this.record('summary', [2]);
    } catch (error) { this.record('failed', [], (error as Error).message || 'trace exception'); }
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.resultPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.closeSync(file); this.run();
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
