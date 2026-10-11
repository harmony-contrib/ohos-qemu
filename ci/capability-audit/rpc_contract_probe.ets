import rpc from '@ohos.rpc';

__RPC_DECLARATION__

@Entry
@Component
struct Index {
  @State result: string = '__RPC_RUN__';
  aboutToAppear(): void {
    const object: rpc.IRemoteObject = new rpc.RemoteObject('__RPC_RUN__');
    __RPC_OPERATION__
  }
  build() {
    Column() { Text(this.result).id('rpc-contract-result') }.width('100%').height('100%')
  }
}
