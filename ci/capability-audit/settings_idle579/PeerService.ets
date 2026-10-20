import { ServiceExtensionAbility, Want, common } from '@kit.AbilityKit';
import rpc from '@ohos.rpc';
import idleNative from 'libsettings_idle579.so';
import { Journal, Request } from './Journal';

class PeerObject extends rpc.RemoteObject {
  private context: common.ServiceExtensionContext;
  private request: Request;
  private startId: number;
  constructor(context: common.ServiceExtensionContext, request: Request, startId: number) {
    super('settings_idle579.peer');
    this.context = context; this.request = request; this.startId = startId;
  }
  onRemoteMessageRequest(code: number, data: rpc.MessageSequence,
    reply: rpc.MessageSequence, options: rpc.MessageOption): boolean {
    if (code !== 1 || data.readInterfaceToken() !== 'settings_idle579.peer' ||
      data.readString() !== this.request.run || data.readString() !== this.request.boot ||
      data.readString() !== this.request.operation || this.startId <= 0) { return false; }
    Journal.write(this.context, this.request, 'peer.token.request', 0, JSON.stringify({
      startId: this.startId, callingUid: rpc.IPCSkeleton.getCallingUid(), callingPid: rpc.IPCSkeleton.getCallingPid(),
      identity: JSON.stringify(idleNative.identity(this.context)) }));
    reply.writeString(this.request.operation);
    reply.writeInt(this.startId);
    reply.writeString(JSON.stringify(idleNative.identity(this.context)));
    reply.writeRemoteObject(idleNative.selfToken(this.context));
    return true;
  }
}

export default class PeerService extends ServiceExtensionAbility {
  private latestStartId: number = 0;
  private last: Request | undefined = undefined;
  onRequest(want: Want, startId: number): void {
    const request = Journal.request(want);
    this.latestStartId = startId; this.last = request;
    Journal.write(this.context, request, 'peer.work', 0,
      JSON.stringify({ startId, identity: JSON.stringify(idleNative.identity(this.context)) }));
  }
  onConnect(want: Want): rpc.RemoteObject {
    const request = Journal.request(want);
    if (this.latestStartId <= 0) { throw new Error('actual prior onRequest required'); }
    Journal.write(this.context, request, 'peer.connect', 0, JSON.stringify({ startId: this.latestStartId }));
    return new PeerObject(this.context, request, this.latestStartId);
  }
  onDestroy(): void {
    if (this.last !== undefined) { Journal.write(this.context, this.last, 'peer.destroy', 0, 'null'); }
  }
}
