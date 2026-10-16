/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import Want from '@ohos.app.ability.Want';

export class SendDataPayload {
  static text(want: Want): string | undefined {
    if (want.action !== 'ohos.want.action.sendData' || want.type !== 'text/plain' ||
        (want.uri !== undefined && want.uri.length > 0) || want.parameters?.['ability.picker.records'] !== undefined) {
      return undefined;
    }
    const stream = want.parameters?.['ability.params.stream'];
    let text: string;
    if (typeof stream === 'string') {
      text = stream;
    } else if (Array.isArray(stream) && stream.length === 1 && typeof stream[0] === 'string') {
      text = stream[0] as string;
    } else {
      throw new Error('sendData text/plain requires one text stream');
    }
    if (text.length === 0 || text.length > 262144 || text.includes('\u0000')) {
      throw new Error('Invalid shared text length or content');
    }
    return text;
  }
}
