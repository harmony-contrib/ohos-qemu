import { common, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import rpc from '@ohos.rpc';
import idleNative from 'libsettings_idle579.so';
import { Journal, Request, FOREIGN_BUNDLE } from './Journal';

export async function nativeFixture(context: common.UIAbilityContext, request: Request): Promise<void> {
  Journal.write(context, request, 'native.identity', 0, JSON.stringify(idleNative.identity(context)));
  const ownToken: rpc.IRemoteObject = idleNative.selfToken(context);
  if (request.action === 'native-ui') {
    Journal.write(context, request, 'native.ui', 0, JSON.stringify(idleNative.attempt(ownToken, 1, 'normal')));
  } else if (request.action === 'native-malformed') {
    const modes: string[] = ['missing-token', 'missing-id', 'extra', 'zero', 'negative',
      'wrong-descriptor', 'truncated-1', 'truncated-2', 'truncated-3'];
    Journal.write(context, request, 'native.malformed.control-before', 0,
      JSON.stringify(idleNative.attempt(ownToken, 1, 'normal')));
    for (const mode of modes) {
      Journal.write(context, request, 'native.malformed', 0,
        JSON.stringify(idleNative.attempt(ownToken, 1, mode)));
    }
    Journal.write(context, request, 'native.malformed.control-after', 0,
      JSON.stringify(idleNative.attempt(ownToken, 1, 'normal')));
  } else if (request.action === 'native-foreign') {
    const want: Want = { bundleName: FOREIGN_BUNDLE, moduleName: 'entry', abilityName: 'PeerService',
      parameters: { run: request.run, boot: request.boot, operation: request.operation, action: 'peer-token' } };
    let connection: number = -1;
    try {
      const remote: rpc.IRemoteObject = await new Promise<rpc.IRemoteObject>((resolve, reject) => {
        connection = context.connectServiceExtensionAbility(want, {
          onConnect: (element, object: rpc.IRemoteObject): void => { resolve(object); },
          onDisconnect: (element): void => { Journal.write(context, request, 'peer.disconnected', 0, 'null'); },
          onFailed: (code: number): void => { reject(new Error('real connect failure:' + code.toString())); }
        });
      });
      const data = rpc.MessageSequence.create();
      const reply = rpc.MessageSequence.create();
      try {
        data.writeInterfaceToken('settings_idle579.peer');
        data.writeString(request.run); data.writeString(request.boot); data.writeString(request.operation);
        const result = await remote.sendMessageRequest(1, data, reply, new rpc.MessageOption());
        Journal.write(context, request, 'peer.transport', result.errCode, JSON.stringify({ connection }));
        if (result.errCode !== 0) { throw new Error('actual peer RPC failed'); }
        const operation: string = reply.readString();
        const startId: number = reply.readInt();
        const identity: string = reply.readString();
        const foreignToken: rpc.IRemoteObject = reply.readRemoteObject();
        if (operation !== request.operation || startId <= 0) { throw new Error('actual peer reply mismatch'); }
        Journal.write(context, request, 'peer.reply', 0, JSON.stringify({ operation, startId, identity }));
        Journal.write(context, request, 'native.foreign', 0,
          JSON.stringify(idleNative.attempt(foreignToken, startId, 'normal')));
      } finally { data.reclaim(); reply.reclaim(); }
    } finally {
      if (connection >= 0) {
        await context.disconnectServiceExtensionAbility(connection);
        Journal.write(context, request, 'peer.disconnect.return', 0, JSON.stringify({ connection }));
      }
    }
  } else { throw new Error('fixed native boundary action required'); }
  Journal.write(context, request, 'native.done', 0, 'null');
}
