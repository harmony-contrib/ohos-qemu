// SPDX-License-Identifier: Apache-2.0
import worker, { __EVENT__ } from '@ohos.worker';

interface Request { nonce: string; generation: number; sequence: number; action: string; buffer: ArrayBuffer; }
interface Reply {
  nonce: string; generation: number; sequence: number; kind: string; buffer: ArrayBuffer;
  portName: string; portUsable: boolean; otherPortAbsent: boolean; inputBytes: number;
}
const port = worker.__PORT__;
port.onmessage = (event: __WORKER_EVENT__): void => {
  const message = event.data as Request;
  if (message.nonce !== '__RUN__' || message.generation < 1 || message.generation > 2) {
    throw new Error('invalid fresh worker challenge/generation');
  }
  const inputBytes: number = message.buffer.byteLength;
  if (message.action === 'transform') {
    const words = new Uint32Array(message.buffer);
    for (let i: number = 0; i < words.length; ++i) {
      words[i] = ((words[i] ^ 0x5a5a5a5a) + message.generation + message.sequence) >>> 0;
    }
    const reply: Reply = { nonce: message.nonce, generation: message.generation, sequence: message.sequence,
      kind: 'data', buffer: message.buffer, portName: '__PORT__', portUsable: typeof port.postMessage === 'function',
      otherPortAbsent: typeof worker.__OTHER_PORT__ === 'undefined', inputBytes };
    port.postMessage(reply, [message.buffer]);
  } else if (message.action === 'close') {
    const reply: Reply = { nonce: message.nonce, generation: message.generation, sequence: message.sequence,
      kind: 'closed', buffer: new ArrayBuffer(0), portName: '__PORT__', portUsable: typeof port.close === 'function',
      otherPortAbsent: typeof worker.__OTHER_PORT__ === 'undefined', inputBytes };
    port.postMessage(reply);
    port.close();
  } else { throw new Error('unrecognized Worker request'); }
};
