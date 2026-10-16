/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import { fileIo as fs } from '@kit.CoreFileKit';

export class Observation {
  schema_version: number = 1;
  timestamp_ms: number = Date.now();
  run_id: string = '';
  launch_id: string = '';
  case_id: string = '';
  invocation_id: string = '';
  event: string = '';
  api: string = '';
  callback_count: number = 0;
  value_type: string = '';
  raw_json: string = '';
  error_type: string = '';
  error_code: number | undefined = undefined;
  error_message: string = '';
  after_dispose: boolean = false;
}

export default class ResultJournal {
  readonly runId: string;
  readonly launchId: string;
  readonly caseId: string;
  private readonly path: string;

  constructor(filesDir: string, runId: string, launchId: string, caseId: string) {
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(runId) || !/^[A-Za-z0-9_-]{1,64}$/.test(launchId)) {
      throw new Error('Invalid journal identity');
    }
    this.runId = runId;
    this.launchId = launchId;
    this.caseId = caseId;
    this.path = filesDir + '/contact-picker-' + runId + '.jsonl';
  }

  append(value: Observation): void {
    value.run_id = this.runId;
    value.launch_id = this.launchId;
    value.case_id = this.caseId;
    const file = fs.openSync(this.path, fs.OpenMode.CREATE | fs.OpenMode.READ_WRITE | fs.OpenMode.APPEND);
    try { fs.writeSync(file.fd, JSON.stringify(value) + '\n'); }
    finally { fs.closeSync(file); }
  }
}
