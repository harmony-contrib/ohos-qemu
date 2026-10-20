import { common } from '@kit.AbilityKit';
import rpc from '@ohos.rpc';
export interface NativeIdentity {
  pid: number;
  uid: number;
  selfTokenHex: string;
  library: string;
  bundle: string;
}
export interface NativeAttempt {
  pid: number;
  uid: number;
  selfTokenHex: string;
  library: string;
  mode: string;
  descriptor: string;
  code: number;
  expectedStartId: number;
  requestBytes: number;
  requestObjects: number;
  clientParcelHex: string;
  transport: number;
  replyBytes: number;
  replyHex: string;
  readResult: boolean;
  readStopped: boolean;
  result: number;
  stopped: boolean;
  remaining: number;
}
export const selfToken: (context: common.Context) => rpc.IRemoteObject;
export const identity: (context: common.Context) => NativeIdentity;
export const attempt: (token: rpc.IRemoteObject, expectedStartId: number, mode: string) => NativeAttempt;
