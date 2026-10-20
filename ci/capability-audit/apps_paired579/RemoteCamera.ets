import common from '@ohos.app.ability.common';
import camera from '@ohos.multimedia.camera';
import image from '@ohos.multimedia.image';
import fs from '@ohos.file.fs';
import { BusinessError } from '@ohos.base';
import { Journal, RUN } from './Journal';

export class RemoteCamera {
  static input?: camera.CameraInput;
  static session?: camera.PhotoSession;
  static preview?: camera.PreviewOutput;
  static photo?: camera.PhotoOutput;
  static device?: camera.CameraDevice;
  static pending: string = '';
  static completed: number = 0;
  static previewStarts: number = 0;
  static previewEnds: number = 0;
  static async stop(): Promise<void> {
    const errors: string[] = [];
    if (RemoteCamera.session) {
      try { await RemoteCamera.session.stop(); } catch (error) { Journal.fail('actual-camera-stop-error',error as BusinessError);errors.push(String(error)); }
      try { await RemoteCamera.session.release(); } catch (error) { Journal.fail('actual-camera-release-error',error as BusinessError);errors.push(String(error)); }
      RemoteCamera.session=undefined;
    }
    if (RemoteCamera.preview) {
      try { await RemoteCamera.preview.release(); } catch (error) { Journal.fail('actual-preview-release-error',error as BusinessError);errors.push(String(error)); }
      RemoteCamera.preview=undefined;
    }
    if (RemoteCamera.photo) {
      try { await RemoteCamera.photo.release(); } catch (error) { Journal.fail('actual-photo-release-error',error as BusinessError);errors.push(String(error)); }
      RemoteCamera.photo=undefined;
    }
    if (RemoteCamera.input) {
      try { await RemoteCamera.input.close(); } catch (error) { Journal.fail('actual-camera-close-error',error as BusinessError);errors.push(String(error)); }
      RemoteCamera.input=undefined;
    }
    RemoteCamera.pending='';Journal.record('actual-remote-camera-cleaned',JSON.stringify(errors));
    if (errors.length) { throw new Error('actual camera cleanup errors retained'); }
  }
  static async savePhoto(photo: camera.Photo,context: common.UIAbilityContext,id: string): Promise<void> {
    try {
      if (!id) { throw new Error('unrequested real remote photo'); }
      const component=await photo.main.getComponent(image.ComponentType.JPEG);
      const size=component.byteBuffer.byteLength;
      if (size<=4 || size>32*1024*1024) { throw new Error('bounded actual JPEG required'); }
      const path=context.filesDir+'/paired579-camera-'+RUN+'-'+id+'.jpg';
      const file=fs.openSync(path,fs.OpenMode.CREATE|fs.OpenMode.WRITE_ONLY|fs.OpenMode.EXCL);
      try { fs.writeSync(file.fd,component.byteBuffer); } finally { fs.closeSync(file); }
      RemoteCamera.completed++;
      Journal.record('actual-remote-camera-photo',JSON.stringify({file:path,bytes:size,device:RemoteCamera.device,completed:RemoteCamera.completed}),0,id,'camera-shutter');
    } finally { await photo.release();RemoteCamera.pending=''; }
  }
  static async execute(action: string,context: common.UIAbilityContext,surface: string): Promise<void> {
    const id=Journal.requestId;const manager=camera.getCameraManager(context);
    if (action==='camera-devices') {
      Journal.record('actual-remote-cameras',JSON.stringify(manager.getSupportedCameras().filter((device: camera.CameraDevice)=>device.connectionType===camera.ConnectionType.CAMERA_CONNECTION_REMOTE)));
    } else if (action==='camera-start') {
      if (RemoteCamera.session || !surface) { throw new Error('one actual remote camera session and source surface required'); }
      const name=Journal.payload['deviceName'];
      if (typeof name!=='string') { throw new Error('actual independent peer name required'); }
      const devices=manager.getSupportedCameras().filter((device: camera.CameraDevice)=>
        device.connectionType===camera.ConnectionType.CAMERA_CONNECTION_REMOTE && device.hostDeviceName===name);
      Journal.record('actual-peer-camera-candidates',JSON.stringify(devices));
      if (!devices.length) { throw new Error('no actual authenticated independent peer camera'); }
      // At most front/back cameras on this sole isolated endpoint. Select a
      // real enumerated ID; do not synthesize a network-prefixed camera ID.
      devices.sort((left: camera.CameraDevice,right: camera.CameraDevice)=>left.cameraPosition-right.cameraPosition);
      RemoteCamera.device=devices[0];RemoteCamera.completed=0;RemoteCamera.previewStarts=0;RemoteCamera.previewEnds=0;
      const capability=manager.getSupportedOutputCapability(RemoteCamera.device,camera.SceneMode.NORMAL_PHOTO);
      const previews=capability.previewProfiles.filter((profile: camera.Profile)=>profile.size.width>=320 && profile.size.height>=240 && profile.size.width<=1920 && profile.size.height<=1080);
      const photos=capability.photoProfiles.filter((profile: camera.Profile)=>profile.format===camera.CameraFormat.CAMERA_FORMAT_JPEG && profile.size.width<=4096 && profile.size.height<=4096);
      if (!previews.length || !photos.length) { throw new Error('actual remote preview/JPEG profiles absent'); }
      previews.sort((a: camera.Profile,b: camera.Profile)=>a.size.width*a.size.height-b.size.width*b.size.height);
      photos.sort((a: camera.Profile,b: camera.Profile)=>a.size.width*a.size.height-b.size.width*b.size.height);
      RemoteCamera.input=manager.createCameraInput(RemoteCamera.device);await RemoteCamera.input.open();
      RemoteCamera.preview=manager.createPreviewOutput(previews[0],surface);
      RemoteCamera.preview.on('frameStart',(error: BusinessError)=>{
        if (error && error.code) { Journal.fail('actual-remote-preview-error',error,id,action); }
        else { RemoteCamera.previewStarts++;Journal.record('actual-remote-preview-start',JSON.stringify(RemoteCamera.previewStarts),0,id,action); }
      });
      RemoteCamera.preview.on('frameEnd',(error: BusinessError)=>{
        if (error && error.code) { Journal.fail('actual-remote-preview-error',error,id,action); }
        else { RemoteCamera.previewEnds++;Journal.record('actual-remote-preview-end',JSON.stringify(RemoteCamera.previewEnds),0,id,action); }
      });
      RemoteCamera.photo=manager.createPhotoOutput(photos[0]);
      RemoteCamera.photo.on('photoAvailable',(error: BusinessError,photo: camera.Photo)=>{
        const request=RemoteCamera.pending;
        if (error && error.code) { Journal.fail('actual-remote-photo-error',error,request,'camera-shutter');RemoteCamera.pending='';return; }
        RemoteCamera.savePhoto(photo,context,request).catch((failure: BusinessError)=>Journal.fail('actual-remote-photo-error',failure,request,'camera-shutter'));
      });
      RemoteCamera.session=manager.createSession(camera.SceneMode.NORMAL_PHOTO) as camera.PhotoSession;
      RemoteCamera.session.beginConfig();RemoteCamera.session.addInput(RemoteCamera.input);
      RemoteCamera.session.addOutput(RemoteCamera.preview);RemoteCamera.session.addOutput(RemoteCamera.photo);
      await RemoteCamera.session.commitConfig();await RemoteCamera.session.start();
      Journal.record('actual-remote-camera-started',JSON.stringify({device:RemoteCamera.device,preview:previews[0],photo:photos[0],surface}));
    } else if (action==='camera-shutter') {
      if (!RemoteCamera.photo || RemoteCamera.pending) { throw new Error('one outstanding real camera request only'); }
      RemoteCamera.pending=id;
      try { await RemoteCamera.photo.capture(); } catch (error) { RemoteCamera.pending='';throw error; }
      Journal.record('actual-remote-shutter-request');
    } else if (action==='camera-state') {
      Journal.record('actual-remote-camera-state',JSON.stringify({device:RemoteCamera.device,pending:RemoteCamera.pending,
        completed:RemoteCamera.completed,previewStarts:RemoteCamera.previewStarts,previewEnds:RemoteCamera.previewEnds}));
    } else if (action==='camera-stop') { await RemoteCamera.stop();
    } else { throw new Error('unknown fixed remote camera action'); }
    Journal.record('done','null',0,id,action);
  }
}
