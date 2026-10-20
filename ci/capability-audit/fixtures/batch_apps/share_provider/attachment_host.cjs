// Actual candidate helper functions + native temporary file IO. URI grants,
// process restart and OHOS Context are host models, never guest evidence.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {stripTypeScriptTypes}=require('node:module');
const out=process.argv[2];fs.mkdirSync(out);const cache=path.join(out,'cache'),files=path.join(out,'files');fs.mkdirSync(cache);fs.mkdirSync(files);
const source=path.join(out,'payload.vcf');fs.writeFileSync(source,'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:actual-host-IO\r\nEND:VCARD\r\n');
let failRead=false,failWrite=false,grew=false,grow=false,closed=0,opened=0;
const OpenMode={READ_ONLY:fs.constants.O_RDONLY,WRITE_ONLY:fs.constants.O_WRONLY,CREATE:fs.constants.O_CREAT,NOFOLLOW:fs.constants.O_NOFOLLOW};
const adapter={OpenMode,accessSync(p){try{fs.accessSync(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}},
 openSync(p,f){if(p==='file://host/payload.vcf')p=source;const fd=fs.openSync(p,f);opened++;return {fd};},closeSync(f){fs.closeSync(typeof f==='number'?f:f.fd);closed++;},
 statSync(p){const s=typeof p==='number'?fs.fstatSync(p):fs.statSync(p);return {size:s.size,ino:BigInt(s.ino),mtime:s.mtimeMs,isFile:()=>s.isFile()};},
 readSync(fd,b){if(failRead)return 0;const n=fs.readSync(fd,new Uint8Array(b));if(grow&&!grew){fs.appendFileSync(source,'x');grew=true;}return n;},
 writeSync(fd,b){return failWrite?0:fs.writeSync(fd,new Uint8Array(b));},fsyncSync:fs.fsyncSync,unlinkSync:fs.unlinkSync,rmdirSync:fs.rmdirSync,mkdirSync:fs.mkdirSync,listFileSync:fs.readdirSync};
const code=fs.readFileSync(process.argv[3],'utf8').replace(/^import .*;\r?\n/gm,'').replaceAll('export class','class');
const sandbox={fs:adapter,util:{generateRandomUUID:crypto.randomUUID},uri:{URI:class{constructor(s){const u=new URL(s);this.scheme=u.protocol.slice(0,-1);this.authority=u.host;this.path=u.pathname;this.userInfo=u.username;this.fragment=u.hash;}}},common:{MM_ATTACHMENT_TYPE:{AUDIO:3},int:{MMS_AUDIO_FILE_MAX_SIZE:280*1024,MMS_FILE_MAX_SIZE:300*1024}},Uint8Array,ArrayBuffer,Number,decodeURIComponent};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(code+'\nthis.Helper=SendDataAttachment;',{mode:'transform'}),sandbox);const H=sandbox.Helper,ctx={cacheDir:cache,filesDir:files,getApplicationContext(){return this;}},want={action:'ohos.want.action.sendData',type:'text/vcard',uri:'file://host/payload.vcf',flags:1,parameters:{'ability.params.stream':['file://host/payload.vcf']}};
let checks=0;function check(name,fn){fn();assert.equal(opened,closed,'all opened FDs closed: '+name);checks++;}
check('real full-byte import and cancel',()=>{const a=H.stage(ctx,want);assert.deepEqual(fs.readFileSync(a.path),fs.readFileSync(source));assert.equal(H.description(a.id),'payload.vcf\n'+fs.statSync(source).size+' B');H.cancel(a.id);assert.equal(fs.existsSync(a.directory),false);});
check('missing read flag rejects before opening',()=>{const n=opened;assert.throws(()=>H.stage(ctx,{...want,flags:0}));assert.equal(n,opened);});
check('plain text array remains original route',()=>assert.equal(H.stage(ctx,{action:want.action,type:'text/plain',parameters:{'ability.params.stream':['plain text']}}),undefined));
check('short read rolls back',()=>{failRead=true;assert.throws(()=>H.stage(ctx,want));failRead=false;assert.deepEqual(fs.readdirSync(cache),[]);});
check('short write rolls back',()=>{failWrite=true;assert.throws(()=>H.stage(ctx,want));failWrite=false;assert.deepEqual(fs.readdirSync(cache),[]);});
check('growing source rejects',()=>{grow=true;assert.throws(()=>H.stage(ctx,want));grow=false;assert.deepEqual(fs.readdirSync(cache),[]);});
check('size limit rejects real file',()=>{const prior=fs.readFileSync(source);fs.writeFileSync(source,Buffer.alloc(300*1024+1));assert.throws(()=>H.stage(ctx,want));fs.writeFileSync(source,prior);assert.deepEqual(fs.readdirSync(cache),[]);});
check('reserved handoff preserves actual draft bytes',()=>{const a=H.stage(ctx,want);H.reserve(a.id);H.cancel(a.id);assert.equal(fs.existsSync(a.path),true);const m=H.handoff(a.id,ctx);assert.deepEqual(fs.readFileSync(m.path),fs.readFileSync(source));assert.equal(fs.existsSync(a.directory),false);H.dispose();assert.equal(fs.existsSync(m.path),true);});
check('cold process model recovery removes only owned staging',()=>{const a=H.stage(ctx,want);H.active=undefined;H.recovered=false;H.recover(ctx);assert.equal(fs.existsSync(a.directory),false);});
check('live import refuses replacement',()=>{const a=H.stage(ctx,want);assert.throws(()=>H.stage(ctx,want));assert.throws(()=>H.stage(ctx,{action:want.action,type:'text/plain',parameters:{'ability.params.stream':['must not replace live attachment']}}));assert.equal(fs.existsSync(a.path),true);H.dispose();});
console.log(JSON.stringify({checks,exit_code:0,native_callback:false,OHOS_URI_grants_verified:false,SDK_compiled:false,scope:'actual candidate helper + native host file IO; Context/URI/restart models'}));
