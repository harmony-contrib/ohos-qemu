// SPDX-License-Identifier: Apache-2.0
// Collection is not a claim that every export/provider/backend works.
import fs from '@ohos.file.fs';
import probe from 'libarktsexportsprobe.so';

interface Property { name: string; read_status: number; value_type: number; read_exception: boolean; }
interface Module {
  module: string; load_status: number; load_exception: boolean; module_type: number;
  collection_status: number; collection_exception: boolean; properties: Property[];
}
interface NativeProbe { inspect: (names: string[]) => Module[]; }
interface Report { runId: string; collection: string; modules: Module[]; export_collection_complete: boolean; }

@Entry
@Component
struct Index {
  @State private note: string = 'Collecting actual SDK module exports';
  aboutToAppear(): void {
    const path: string = '/data/storage/el2/base/files/arkts-exports-__RUN__-results.log';
    const file = fs.openSync(path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    try {
      const names: string[] = __MODULES__;
      const modules: Module[] = (probe as NativeProbe).inspect(names);
      const report: Report = { runId: '__RUN__', collection: 'all_own_string_properties', modules: modules,
                              export_collection_complete: true };
      fs.writeSync(file.fd, JSON.stringify(report) + '\n');
      this.note = 'Actual export collection complete';
    } finally { fs.closeSync(file); }
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
