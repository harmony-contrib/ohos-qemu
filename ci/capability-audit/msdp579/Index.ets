import udc from '@ohos.data.unifiedDataChannel';
import { Journal, RUN } from '../common/Journal';
@Entry
@Component
struct Index {
  @State dropped: string = '';
  build() {
    Column({space:24}) {
      Text('MSDP579 ' + RUN).id('msdp579-nonce');
      Text('Drag ' + RUN).id('msdp579-drag-source').width(240).height(100).draggable(true)
        .onDragStart((event: DragEvent) => {
          const text = new udc.PlainText({textContent:'msdp579_'+RUN,abstract:'MSDP579'});
          event.setData(new udc.UnifiedData(text));
          Journal.record('ui-drag-start',JSON.stringify('msdp579_'+RUN));
          return {extraInfo:'msdp579_'+RUN};
        });
      Text('Drop here ' + this.dropped).id('msdp579-drag-sink').width(300).height(160)
        .allowDrop(['general.plain-text'])
        .onDrop((event: DragEvent) => {
          const records=event.getData().getRecords();
          const values: string[] = [];
          for (const record of records) {
            if (record.getType() === 'general.plain-text') { values.push((record as udc.PlainText).textContent); }
          }
          Journal.record('ui-drop-data',JSON.stringify(values));
          this.dropped=RUN;Journal.record('ui-drop-result',JSON.stringify(event.getResult()));
        });
      TextInput({placeholder:'Remote keyboard challenge'}).id('msdp579-remote-input')
        .onChange((v: string) => Journal.record('ui-text-changed',JSON.stringify(v)));
    }.width('100%').height('100%').padding(24)
      .onMouse((event: MouseEvent) => Journal.record('ui-mouse',JSON.stringify({deviceId:event.deviceId,x:event.x,y:event.y,action:event.action,button:event.button}))); 
  }
}
