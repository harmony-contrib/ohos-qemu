import sensor from '@ohos.sensor';
import stationary from '@ohos.stationary';
import cooperate from '@ohos.cooperate';
import drag from '@ohos.deviceStatus.dragInteraction';
import deviceStatus from '@ohos.multimodalAwareness.deviceStatus';
import spatial from '@ohos.multimodalAwareness.spatialAwareness';
import metadata from '@ohos.multimodalAwareness.metadataBinding';
import motion from '@ohos.multimodalAwareness.motion';
import userStatus from '@ohos.multimodalAwareness.userStatus';
import onScreen from '@ohos.multimodalAwareness.onScreen';
import inputDevice from '@ohos.multimodalInput.inputDevice';
import image from '@ohos.multimedia.image';
import window from '@ohos.window';
import common from '@ohos.app.ability.common';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { BusinessError, Callback } from '@ohos.base';
import { Journal, RUN, BUNDLE } from './Journal';

export class Driver {
  static stage?: window.WindowStage;
  private static accel: Callback<sensor.AccelerometerResponse> = (v) => Journal.record('sensor-callback',JSON.stringify({x:v.x,y:v.y,z:v.z,timestamp:v.timestamp}));
  private static rotation: Callback<sensor.RotationVectorResponse> = (v) => Journal.record('rotation-sensor-callback',JSON.stringify(v));
  private static still: Callback<stationary.ActivityResponse> = (v) => Journal.record('still-callback', JSON.stringify(v));
  private static relative: Callback<stationary.ActivityResponse> = (v) => Journal.record('relative-callback', JSON.stringify(v));
  private static distance: Callback<spatial.DistanceMeasurementResponse> = (v) => Journal.record('distance-callback', JSON.stringify(v));
  private static door: Callback<spatial.DoorPositionResponse> = (v) => Journal.record('door-callback', JSON.stringify(v));
  private static age: Callback<userStatus.UserClassification> = (v) => Journal.record('age-callback', JSON.stringify(v));
  private static user: Callback<userStatus.UserStatusData> = (v) => Journal.record('user-callback', JSON.stringify(v));
  private static steady: Callback<deviceStatus.SteadyStandingStatus> = (v) => Journal.record('steady-callback', JSON.stringify(v));
  private static hand: Callback<motion.OperatingHandStatus> = (v) => Journal.record('hand-callback', JSON.stringify(v));
  private static hold: Callback<motion.HoldingHandStatus> = (v) => Journal.record('holding-callback', JSON.stringify(v));
  private static pickup: Callback<motion.PickupEvent> = (v) => Journal.record('pickup-callback', JSON.stringify(v));
  private static smart: Callback<motion.SmartRotateEvent> = (v) => Journal.record('smart-rotate-callback', JSON.stringify(v));
  private static hover: Callback<motion.HoverHandAction> = (v) => Journal.record('hover-callback', JSON.stringify(v));
  private static rotate: Callback<motion.RotateEvent> = (v) => Journal.record('rotate-callback', JSON.stringify(v));
  private static drag: Callback<drag.DragState> = (v) => {
    Journal.record('drag-callback', JSON.stringify(v));
    Journal.record('drag-summary', JSON.stringify(drag.getDataSummary()));
  };
  private static coop: Callback<cooperate.CooperateMessage> = (v) => Journal.record('cooperate-callback', JSON.stringify(v));
  private static mouse: Callback<cooperate.MouseLocation> = (v) => Journal.record('mouse-callback', JSON.stringify(v));
  private static permission: Callback<onScreen.ReadingScreenPermissionStatus> = (v) => Journal.record('screen-permission-callback', JSON.stringify(v));
  private static screen: Callback<onScreen.OnscreenAwarenessInfo[]> = (v) => Journal.record('screen-callback', JSON.stringify(v));
  private static meta: Callback<number> = (v) => {
    Journal.record('metadata-submit-request', JSON.stringify(v));
    metadata.submitMetadata('msdp579://' + BUNDLE + '/' + RUN);
    Journal.record('metadata-submitted', JSON.stringify('msdp579://' + BUNDLE + '/' + RUN));
  };
  private static config(): spatial.DistanceMeasurementConfigParams {
    return {deviceList:[Journal.payload.peer as string], techType:spatial.TechnologyType.ULTRASOUND,
      reportMode:spatial.ReportingMode.REPORT_MODE_PERIODIC_REPORTING, reportFrequency:1};
  }
  static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
    await Journal.identity();
    switch (action) {
      case 'capabilities': Journal.record('capabilities',JSON.stringify([canIUse('SystemCapability.Msdp.DeviceStatus.Cooperate'),canIUse('SystemCapability.Msdp.DeviceStatus.Drag'),canIUse('SystemCapability.Msdp.DeviceStatus.Stationary'),canIUse('SystemCapability.MultimodalAwareness.DeviceStatus'),canIUse('SystemCapability.MultimodalAwareness.DistanceMeasurement'),canIUse('SystemCapability.MultimodalAwareness.MetadataBinding'),canIUse('SystemCapability.MultimodalAwareness.Motion'),canIUse('SystemCapability.MultimodalAwareness.OnScreenAwareness'),canIUse('SystemCapability.MultimodalAwareness.UserStatus')])); break;
      case 'context': Journal.record('context', JSON.stringify({filesDir:context.filesDir})); break;
      case 'permissions': {
        const value = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context,
          ['ohos.permission.ACTIVITY_MOTION','ohos.permission.DISTRIBUTED_DATASYNC']);
        Journal.record('permission-result', JSON.stringify(value)); break;
      }
      case 'rotation-writer-denial': {const api=await import('libmsdp579.so');Journal.record('rotation-writer-denial',api.writerDenial());break;}
      case 'algo-on': { const api=await import('libmsdp579.so');for (const type of [0,1,2]) {Journal.record('algo-on-return',JSON.stringify({type,result:api.on(type)}));} break; }
      case 'algo-off-one': {const api=await import('libmsdp579.so');Journal.record('algo-off-return',JSON.stringify({type:Journal.payload.type,result:api.off(Journal.payload.type as number)}));break;}
      case 'algo-drain': {const api=await import('libmsdp579.so');Journal.record('algo-native-raw',api.drain());break;}
      case 'sensor-list': Journal.record('sensor-list',JSON.stringify(sensor.getSensorListSync())); break;
      case 'sensor-on': sensor.on(sensor.SensorId.ACCELEROMETER,Driver.accel,{interval:100000000}); break;
      case 'rotation-sensor-on': sensor.on(sensor.SensorId.ROTATION_VECTOR,Driver.rotation,{interval:10000000}); break;
      case 'rotation-sensor-off': sensor.off(sensor.SensorId.ROTATION_VECTOR,Driver.rotation); break;
      case 'sensor-off': sensor.off(sensor.SensorId.ACCELEROMETER,Driver.accel); break;
      case 'still-on': stationary.on('still',stationary.ActivityEvent.ENTER_EXIT,1,Driver.still); break;
      case 'still-on-invalid': stationary.on('still',stationary.ActivityEvent.ENTER_EXIT,-1,Driver.still); break;
      case 'still-once': stationary.once('still',(v) => Journal.record('still-once-callback',JSON.stringify(v))); break;
      case 'still-off': stationary.off('still',stationary.ActivityEvent.ENTER_EXIT,Driver.still); break;
      case 'relative-on': stationary.on('relativeStill',stationary.ActivityEvent.ENTER_EXIT,1,Driver.relative); break;
      case 'relative-once': stationary.once('relativeStill',(v) => Journal.record('relative-once-callback',JSON.stringify(v))); break;
      case 'relative-off': stationary.off('relativeStill',stationary.ActivityEvent.ENTER_EXIT,Driver.relative); break;
      case 'device-on': deviceStatus.on('steadyStandingDetect',Driver.steady); break;
      case 'device-off': deviceStatus.off('steadyStandingDetect',Driver.steady); break;
      case 'rotation': Journal.record('rotation',JSON.stringify(await deviceStatus.getDeviceRotationRadian())); break;
      case 'motion-on': motion.on('operatingHandChanged',Driver.hand); break;
      case 'motion-off': motion.off('operatingHandChanged',Driver.hand); break;
      case 'motion-recent': Journal.record('motion-recent',JSON.stringify(motion.getRecentOperatingHandStatus())); break;
      case 'holding-on': motion.on('holdingHandChanged',Driver.hold); break;
      case 'holding-off': motion.off('holdingHandChanged',Driver.hold); break;
      case 'pickup-on': motion.onPickupChange(Driver.pickup); break;
      case 'pickup-off': motion.offPickupChange(Driver.pickup); break;
      case 'smart-on': motion.onSmartRotateChange(Driver.smart); break;
      case 'smart-off': motion.offSmartRotateChange(Driver.smart); break;
      case 'hover-on': motion.onHoverHandChange({left:0,top:0,width:100,height:100},Driver.hover); break;
      case 'hover-invalid': motion.onHoverHandChange({left:0,top:0,width:0,height:0},Driver.hover); break;
      case 'hover-off': motion.offHoverHandChange(Driver.hover); break;
      case 'rotate-on': motion.onRotateChange(Driver.rotate); break;
      case 'rotate-off': motion.offRotateChange(Driver.rotate); break;
      case 'distance-on': spatial.onDistanceMeasure(Driver.config(),Driver.distance); break;
      case 'distance-off': spatial.offDistanceMeasure(Driver.config(),Driver.distance); break;
      case 'door-on': spatial.onIndoorOrOutdoorIdentify(Driver.config(),Driver.door); break;
      case 'door-off': spatial.offIndoorOrOutdoorIdentify(Driver.config(),Driver.door); break;
      case 'age-on': userStatus.on('userAgeGroupDetected',Driver.age); break;
      case 'age-off': userStatus.off('userAgeGroupDetected',Driver.age); break;
      case 'user-on': Journal.record('user-return',JSON.stringify(userStatus.subscribe(userStatus.UserStatusFeature.GESTURES_RECOGNITION,Driver.user))); break;
      case 'user-off': Journal.record('user-return',JSON.stringify(userStatus.unsubscribe(userStatus.UserStatusFeature.GESTURES_RECOGNITION,Driver.user))); break;
      case 'user-configure': Journal.record('user-return',JSON.stringify(userStatus.configure(userStatus.UserStatusFeature.GESTURES_RECOGNITION,'{}'))); break;
      case 'user-capabilities': Journal.record('user-capabilities',JSON.stringify(userStatus.queryCapabilities([]))); break;
      case 'metadata-on': metadata.on('operationSubmitMetadata',BUNDLE,Driver.meta); break;
      case 'metadata-off': metadata.off('operationSubmitMetadata',BUNDLE,Driver.meta); break;
      case 'metadata-notify': Journal.record('metadata-notified',JSON.stringify(await metadata.notifyMetadataBindingEvent(Journal.payload.bundle as string))); break;
      case 'metadata-encode': {
        const buffer = new ArrayBuffer(64 * 64 * 4); const bytes = new Uint8Array(buffer);
        for (let i=0;i<bytes.length;i++) { bytes[i]=(i+RUN.charCodeAt(i%RUN.length))%256; }
        const source = await image.createPixelMapUsingAllocator(buffer,{size:{width:64,height:64},pixelFormat:image.PixelMapFormat.RGBA_8888,editable:true},image.AllocatorType.DMA);
        let encoded: image.PixelMap | undefined;
        try {
          encoded=await metadata.encodeImage(source,'msdp579_'+RUN);
          const output=new ArrayBuffer(64*64*4);await encoded.readPixelsToBuffer(output);
          Journal.record('encoded-pixels',JSON.stringify(Array.from(new Uint8Array(output))));
          Journal.record('decoded-metadata',JSON.stringify(await metadata.decodeImage(encoded)));
        } finally { if (encoded && encoded!==source) { await encoded.release(); } await source.release(); }
        break;
      }
      case 'screen-content': Journal.record('page-content',JSON.stringify(await onScreen.getPageContent({textOnly:true,contentUnderstand:true}))); break;
      case 'screen-permission-on': onScreen.onReadingScreenPermissionListener(Driver.permission); break;
      case 'screen-permission-off': onScreen.offReadingScreenPermissionListener(Driver.permission); break;
      case 'screen-on': onScreen.subscribe({capList:['pageContent']},Driver.screen); break;
      case 'screen-off': onScreen.unsubscribe({capList:['pageContent']},Driver.screen); break;
      case 'screen-trigger': Journal.record('screen-trigger',JSON.stringify(await onScreen.trigger({capList:['pageContent']}))); break;
      case 'screen-capture': Journal.record('screen-capture',JSON.stringify(await onScreen.capture({capList:['pageContent']}))); break;
      case 'screen-interact': Journal.record('screen-interact',JSON.stringify(await onScreen.interact({capList:['pageContent']}))); break;
      case 'screen-apperceive': Journal.record('screen-apperceive',JSON.stringify(await onScreen.apperceive({capList:['pageContent']}))); break;
      case 'screen-control': {
        const page=await onScreen.getPageContent({textOnly:true});Journal.record('page-content',JSON.stringify(page));
        if (!page.paragraphs || page.paragraphs.length===0) { throw new Error('actual own page hook missing'); }
        await onScreen.sendControlEvent({windowId:page.windowId,sessionId:page.sessionId,eventType:onScreen.EventType.SCROLL_TO_HOOK,hookId:page.paragraphs[0].hookId});Journal.record('screen-control-return',JSON.stringify(page));break;
      }
      case 'screen-control-invalid': await onScreen.sendControlEvent({windowId:-1,sessionId:-1,eventType:onScreen.EventType.SCROLL_TO_HOOK}); break;
      case 'drag-on': drag.on('drag',Driver.drag); break;
      case 'drag-off': drag.off('drag',Driver.drag); break;
      case 'drag-summary': Journal.record('drag-summary',JSON.stringify(drag.getDataSummary())); break;
      case 'cooperate-on': cooperate.on('cooperateMessage',Driver.coop); break;
      case 'cooperate-off': cooperate.off('cooperateMessage',Driver.coop); break;
      case 'cooperate-prepare': await cooperate.prepareCooperate(); break;
      case 'cooperate-unprepare': await cooperate.unprepareCooperate(); break;
      case 'cooperate-activate': await cooperate.activateCooperate(Journal.payload.peer as string,Journal.payload.device_id as number); break;
      case 'cooperate-activate-invalid': await cooperate.activateCooperate('',-1); break;
      case 'cooperate-deactivate': await cooperate.deactivateCooperate(true); break;
      case 'cooperate-mouse-on': cooperate.on('cooperateMouse',Journal.payload.peer as string,Driver.mouse); break;
      case 'cooperate-mouse-off': cooperate.off('cooperateMouse',Journal.payload.peer as string,Driver.mouse); break;
      case 'cooperate-state': Journal.record('cooperate-state',JSON.stringify(await cooperate.getCooperateSwitchState(Journal.payload.peer as string))); break;
      case 'input-devices': {
        const ids=await inputDevice.getDeviceList();
        for (const id of ids) { Journal.record('input-device',JSON.stringify(await inputDevice.getDevice(id))); } break;
      }
      case 'quiet': await new Promise<void>((resolve)=>setTimeout(resolve,4200)); Journal.record('quiet-end'); break;
      default: throw new Error('unlisted fixed MSDP action');
    }
    Journal.record('done');
  }
}
