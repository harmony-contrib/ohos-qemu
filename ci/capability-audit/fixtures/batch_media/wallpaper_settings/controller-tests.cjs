/* Actual controller bodies with controlled public API dependencies; not backend proof. */
const fs = require('fs');
const assert = require('assert/strict');
const ts = require(process.argv[3]);
const source = fs.readFileSync(process.argv[2], 'utf8');
const js = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS}}).outputText;
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
const flush = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
let cases=0;
function setup() {
  const env={states:[], opens:[], closes:[], sources:[], pixels:[], picks:[], sets:[], restores:[], policy:async()=>false,
    choose:async()=>({photoUris:['file://media/Photo/13/IMG.png']}), size:1000, isFile:true, width:1920, height:1080,
    openError:null, decodeError:null, closeError:null, sourceReleaseError:null, pixelWait:null, setWait:null, setError:null, restoreError:null};
  const pixel=()=>{const p={released:0,async release(){ assert(!env.states.at(-1)?.preview || env.states.at(-1).preview!==this || env.forceClosed);
    this.released++;assert.equal(this.released,1);}};env.pixels.push(p);return p;};
  const modules={
    '@ohos.file.photoAccessHelper':{default:{PhotoSelectOptions:class{},PhotoViewMIMETypes:{IMAGE_TYPE:'image/*'},PhotoViewPicker:class {async select(o){env.picks.push(o);return env.choose();}}}},
    '@ohos.file.fs':{default:{OpenMode:{READ_ONLY:0},async open(uri,mode){env.opens.push({uri,mode});if(env.openError)throw env.openError;return {fd:31};},
      async stat(fd){assert.equal(fd,31);return {size:env.size,isFile:()=>env.isFile};},async close(f){assert.equal(f.fd,31);env.closes.push(f.fd);if(env.closeError)throw env.closeError;}}},
    '@ohos.multimedia.image':{default:{createImageSource(fd){assert.equal(fd,31);const s={released:0,async getImageInfo(){return {size:{width:env.width,height:env.height}};},
      async createPixelMap(){if(env.decodeError)throw env.decodeError;if(env.pixelWait)return env.pixelWait.promise;return pixel();},
      async release(){this.released++;assert.equal(this.released,1);if(env.sourceReleaseError)throw env.sourceReleaseError;}};env.sources.push(s);return s;}}},
    '@ohos.wallpaper':{default:{WallpaperType:{WALLPAPER_SYSTEM:0,WALLPAPER_LOCKSCREEN:1},async setImage(p,t){assert.equal(p.released,0);env.sets.push({p,t});if(env.setError)throw env.setError;if(env.setWait)await env.setWait.promise;assert.equal(p.released,0);},
      async restore(t){env.restores.push(t);if(env.restoreError)throw env.restoreError;}}},
    '@ohos/settings.common/src/main/ets/utils/SystemParamUtil':{SystemParamUtil:{isModifyWallpaperDisable:()=>env.policy()}},
    '@ohos/settings.common/src/main/ets/utils/LogUtil':{LogUtil:{info(){},error(){}}}
  };
  const mod={exports:{}};new Function('require','module','exports',js)(id=>{assert(id in modules,id);return modules[id];},mod,mod.exports);
  const {WallpaperSelectionController:C,WallpaperSelectionPhase:P}=mod.exports;
  const controller=new C(s=>env.states.push(s));return {env,controller,P,pixel};
}
(async()=>{
  {const {env,controller:c,P}=setup();await c.choose();assert.equal(env.states.at(-1).phase,P.PREVIEW);assert.equal(env.picks[0].MIMEType,'image/*');assert.equal(env.picks[0].maxSelectNumber,1);
   assert.deepEqual(env.opens,[{uri:'file://media/Photo/13/IMG.png',mode:0}]);assert.equal(env.sources[0].released,1);assert.equal(env.closes.length,1);assert.equal(env.sets.length,0);
   assert(await c.apply(0));assert(await c.apply(1));assert.equal(env.states.at(-1).phase,P.SAVED);assert.deepEqual(env.sets.map(x=>x.t),[0,1]);await c.cancel();assert.equal(env.pixels[0].released,1);
   await c.cancel();assert.equal(env.pixels[0].released,1);assert(await c.restore(0));assert.equal(env.states.at(-1).phase,P.RESTORED);assert.deepEqual(env.restores,[0]);await c.dispose();cases++;}
  {const {env,controller:c,P}=setup();const wait=deferred();env.choose=()=>wait.promise;const pending=c.choose();await flush();assert(await c.cancel());await c.choose();assert.equal(env.picks.length,1);
   wait.resolve({photoUris:['file://media/Photo/99/new.png']});await pending;assert.equal(env.opens.length,0);assert.equal(env.sets.length,0);assert.equal(env.states.at(-1).phase,P.CANCELLED);cases++;}
  {const {env,controller:c,pixel}=setup();env.pixelWait=deferred();const pending=c.choose();await flush();assert.equal(env.sources.length,1);const callbacks=env.states.length;env.forceClosed=true;
   await c.dispose();const p=pixel();env.pixelWait.resolve(p);await pending;assert.equal(p.released,1);assert.equal(env.sources[0].released,1);assert.equal(env.closes.length,1);assert.equal(env.sets.length,0);assert.equal(env.states.length,callbacks);cases++;}
  {const {env,controller:c,P}=setup();await c.choose();env.setError={code:201,message:'actual token denied'};assert.equal(await c.apply(0),false);assert.equal(env.states.at(-1).phase,P.ERROR);
   assert.equal(env.states.at(-1).errorCode,201);assert.equal(env.states.at(-1).errorMessage,'actual token denied');assert.equal(env.pixels[0].released,0);await c.cancel();assert.equal(env.pixels[0].released,1);cases++;}
  {const {env,controller:c,P}=setup();env.openError={code:13900012,message:'actual selected URI revoked'};await c.choose();assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.states.at(-1).errorCode,13900012);assert.equal(env.sources.length,0);assert.equal(env.sets.length,0);cases++;}
  for(const change of [{size:0},{size:32*1024*1024+1},{isFile:false},{width:0},{height:0},{width:1.5},{width:8193},{width:8192,height:8192}]) {
   const {env,controller:c,P}=setup();Object.assign(env,change);await c.choose();assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.pixels.length,0);assert.equal(env.closes.length,1);
   if(env.sources.length)assert.equal(env.sources[0].released,1);cases++;}
  for(const prop of ['decodeError','sourceReleaseError','closeError']) {const {env,controller:c,P}=setup();env[prop]={code:5,message:'actual '+prop};await c.choose();assert.equal(env.states.at(-1).phase,P.ERROR);
   assert.equal(env.states.at(-1).errorCode,5);assert.equal(env.sources[0].released,1);assert.equal(env.closes.length,1);for(const pixel of env.pixels)assert.equal(pixel.released,1);cases++;}
  {const {env,controller:c,P}=setup();env.choose=async()=>({photoUris:[]});await c.choose();assert.equal(env.states.at(-1).phase,P.CANCELLED);assert.equal(env.opens.length,0);assert.equal(env.sets.length,0);cases++;}
  for(const uris of [['','x'],[''],['x'.repeat(4097)],['bad\0uri']]) {const {env,controller:c,P}=setup();env.choose=async()=>({photoUris:uris});await c.choose();assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.opens.length,0);cases++;}
  {const {env,controller:c}=setup();await c.choose();const wait=deferred();env.policy=()=>wait.promise;const pending=c.apply(0);await flush();assert(await c.cancel());wait.resolve(false);assert.equal(await pending,false);assert.equal(env.sets.length,0);assert.equal(env.pixels[0].released,1);cases++;}
  {const {env,controller:c,P}=setup();env.policy=async()=>true;await c.choose();assert.equal(env.picks.length,0);assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.sets.length,0);cases++;}
  {const {env,controller:c}=setup();await c.choose();env.setWait=deferred();const pending=c.apply(0);await flush();assert(c.isCommitting());assert.equal(await c.cancel(),false);env.forceClosed=true;
   await c.dispose();assert.equal(env.pixels[0].released,0);const callbacks=env.states.length;env.setWait.resolve();assert.equal(await pending,false);assert.equal(env.pixels[0].released,1);assert.equal(env.states.length,callbacks);assert.equal(env.sets.length,1);cases++;}
  {const {env,controller:c,P}=setup();assert.equal(await c.restore(99),false);assert.equal(env.restores.length,0);assert.equal(env.states.at(-1).errorCode,401);await c.choose();assert.equal(await c.apply(99),false);assert.equal(env.sets.length,0);
   env.restoreError={code:201,message:'actual restore denied'};assert.equal(await c.restore(1),false);assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.pixels[0].released,0);await c.cancel();cases++;}
  {const {env,controller:c}=setup();await c.choose();const first=env.pixels[0];await c.choose();assert.equal(first.released,1);assert.equal(env.pixels[1].released,0);env.forceClosed=true;await c.dispose();assert.equal(env.pixels[1].released,1);cases++;}
  {const {env,controller:c,P}=setup();await c.choose();env.pixels[0].release=async()=>{env.pixels[0].released++;throw {code:5,message:'actual PixelMap release failed'};};assert.equal(await c.cancel(),false);assert.equal(env.states.at(-1).phase,P.ERROR);assert.equal(env.states.at(-1).errorCode,5);assert.equal(env.pixels[0].released,1);cases++;}
  console.log(JSON.stringify({actual_controller_cases:cases,scope:'controlled SDK dependencies; NOT real URI/permission/service/renderer proof'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
