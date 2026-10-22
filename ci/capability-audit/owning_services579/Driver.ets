import common from '@ohos.app.ability.common';
import window from '@ohos.window';
import fs from '@ohos.file.fs';
import osAccount from '@ohos.account.osAccount';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import cryptoFramework from '@ohos.security.cryptoFramework';
import native from 'libowning_services579.so';
import { BusinessError } from '@ohos.base';
import { Journal, RUN, BUNDLE } from './Journal';

export class Driver {
 static stage?: window.WindowStage;
 static pin?: osAccount.PINAuth;
 static idm?: osAccount.UserIdentityManager;
 static auth?: osAccount.UserAuth;
 static input?: osAccount.IInputData;
 static authContext: Uint8Array = new Uint8Array([]);
 static account: number = -1;
 static inputRequest: string = '';
 static inputAction: string = '';
 static challenge: Uint8Array = new Uint8Array([]);
 static token: Uint8Array = new Uint8Array([]);
 static pinBytes: Uint8Array = new Uint8Array([]);
 static random(n: number): Uint8Array { return cryptoFramework.createRandom().generateRandomSync(n).data; }
 static hex(b: Uint8Array): string { let s=''; for (let i=0;i<b.length;i++) { s+=b[i].toString(16).padStart(2,'0'); } return s; }
 static async execute(action: string, context: common.UIAbilityContext): Promise<void> {
  const p=Journal.payload;
  if(action==='identity'){await Journal.identity();}
  else if(action==='declarations'){
   Journal.record('declarations',JSON.stringify({DistributedFile:canIUse('SystemCapability.FileManagement.File.DistributedFile'),HiDumper:canIUse('SystemCapability.HiviewDFX.HiDumper'),DataTransitManager:canIUse('SystemCapability.Security.DataTransitManager'),DeviceAuth:canIUse('SystemCapability.Security.DeviceAuth'),DeviceSecurityLevel:canIUse('SystemCapability.Security.DeviceSecurityLevel'),PinAuth:canIUse('SystemCapability.UserIAM.UserAuth.PinAuth')}));
  } else if(action==='permissions'){
   const actual=await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context,['ohos.permission.DISTRIBUTED_DATASYNC']);
   Journal.record('permission-result',JSON.stringify(actual));
  } else if(action==='native'){
   const result=await native.execute(p.operation as string,p.argument as string,p.account as number,
     context.filesDir+'/native-'+Journal.requestId+'.raw');
   Journal.record('native-result',JSON.stringify(result),result.rc);
  } else if(action==='account-create'){
   const manager=osAccount.getAccountManager();
   const before=await manager.queryAllCreatedOsAccounts();
   Journal.record('accounts-before',JSON.stringify(before));
   if(before.some((i: osAccount.OsAccountInfo)=>i.localName==='services579_'+RUN)){throw new Error('owned account name already exists');}
   const actual=await manager.createOsAccount('services579_'+RUN,osAccount.OsAccountType.NORMAL);
   Driver.account=actual.localId;Journal.record('account-created',JSON.stringify(actual));
  } else if(action==='account-recover'){
   if(Driver.pin){Driver.pin.unregisterInputer();}if(Driver.idm&&Driver.account>=0){Driver.idm.closeSession(Driver.account);}
   const manager=osAccount.getAccountManager();const accounts=await manager.queryAllCreatedOsAccounts();
   const owned=accounts.filter((i:osAccount.OsAccountInfo)=>i.localName==='services579_'+RUN);
   if(owned.length>1||owned.some((i:osAccount.OsAccountInfo)=>i.localId===100)){throw new Error('ambiguous/foreign account');}
   for(let i=0;i<owned.length;i++){await manager.removeOsAccount(owned[i].localId);}
   Driver.account=-1;Journal.record('accounts-recovered',JSON.stringify(await manager.queryAllCreatedOsAccounts()));
  } else if(action==='account-restore'){
   if(Driver.account<0){throw new Error('no owned account in this caller process');}
   await osAccount.getAccountManager().removeOsAccount(Driver.account);
   Journal.record('accounts-after',JSON.stringify(await osAccount.getAccountManager().queryAllCreatedOsAccounts()));
   Driver.account=-1;
  } else if(action==='pin-denied'){
   const inputer=new osAccount.PINAuth();inputer.registerInputer({onGetData:(sub:osAccount.AuthSubType,input:osAccount.IInputData,options:osAccount.GetInputDataOptions)=>Journal.record('unexpected-pin-input',JSON.stringify({sub,options}))});
   inputer.unregisterInputer();Journal.record('pin-denied-unexpected-success');
  } else if(action==='pin-open'){
   const account=p.account as number;
   // An account created by this run is re-associated after real caller restart.
   const owned=(await osAccount.getAccountManager().queryAllCreatedOsAccounts()).filter((i: osAccount.OsAccountInfo)=>i.localId===account&&i.localName==='services579_'+RUN);
   if(owned.length!==1){throw new Error('refuse foreign credential account');}Driver.account=account;
   Driver.pin=new osAccount.PINAuth();Driver.idm=new osAccount.UserIdentityManager();Driver.auth=new osAccount.UserAuth();
   Driver.challenge=await Driver.idm.openSession(account);
   Journal.record('pin-session',JSON.stringify({account,challenge:Driver.hex(Driver.challenge)}));
   Driver.pin.registerInputer({onGetData:(sub: osAccount.AuthSubType,input: osAccount.IInputData,options: osAccount.GetInputDataOptions)=>{
    Driver.input=input;Journal.record('pin-input-request',JSON.stringify({sub,options}),0,Driver.inputRequest,Driver.inputAction);
    if(Driver.pinBytes.length>0){input.onSetData(osAccount.AuthSubType.PIN_SIX,new Uint8Array(Driver.pinBytes));}
   }});
   Journal.record('pin-registered');
  } else if(action==='pin-info'){
   if(!Driver.idm){throw new Error('IDM session required');}
   Journal.record('pin-info',JSON.stringify(await Driver.idm.getAuthInfo({authType:osAccount.AuthType.PIN,accountId:Driver.account})));
  } else if(action==='pin-enroll'){
   if(!Driver.idm){throw new Error('IDM session required');}
   Driver.inputRequest=Journal.requestId;Driver.inputAction=action;
   const request=Journal.requestId;const operation=action;
   Driver.pinBytes=new Uint8Array([49,57,55,51,56,54]);
   // This PIN belongs only to the newly allocated disposable account. It is a
   // real inputer feeding the selected PIN HDI, never a replacement executor.
   Driver.idm.addCredential({credType:osAccount.AuthType.PIN,credSubType:osAccount.AuthSubType.PIN_SIX,
    token:new Uint8Array([]),accountId:Driver.account},{onResult:(code: number,extra: osAccount.RequestResult)=>{
      Journal.record('pin-enrolled',JSON.stringify(extra),code,request,operation);Driver.pinBytes.fill(0);Driver.pinBytes=new Uint8Array([]);
    }});
  } else if(action==='pin-auth'||action==='pin-wrong'||action==='pin-cancel'){
   if(!Driver.auth){throw new Error('real UserAuth required');}
   Driver.pinBytes=action==='pin-cancel'?new Uint8Array([]):new Uint8Array(action==='pin-wrong'?[49,57,55,51,56,55]:[49,57,55,51,56,54]);
   Driver.inputRequest=Journal.requestId;Driver.inputAction=action;
   const challenge=Driver.random(32);const requested=Journal.requestId;const operation=Journal.action;
   Driver.authContext=Driver.auth.auth(challenge,osAccount.AuthType.PIN,osAccount.AuthTrustLevel.ATL3,{accountId:Driver.account},{onResult:(code: number,extra: osAccount.AuthResult)=>{
    Driver.token=extra.token?new Uint8Array(extra.token):new Uint8Array([]);
    Journal.record('pin-auth-result',JSON.stringify({challenge:Driver.hex(challenge),token:Driver.hex(Driver.token),extra}),code,requested,operation);
    Driver.pinBytes.fill(0);Driver.pinBytes=new Uint8Array([]);
   }});
   Journal.record('pin-auth-start',JSON.stringify({challenge:Driver.hex(challenge),context:Driver.hex(Driver.authContext)}));
  } else if(action==='pin-cancel-now'){
   if(!Driver.auth||Driver.authContext.length===0){throw new Error('pending actual auth required');}
   Driver.auth.cancelAuth(Driver.authContext);Journal.record('pin-cancelled');
  } else if(action==='pin-delete'){
   if(!Driver.idm||Driver.token.length===0){throw new Error('fresh actual auth token required');}
   const requested=Journal.requestId;const operation=Journal.action;
   Driver.idm.delUser(Driver.token,{onResult:(code:number,extra:osAccount.RequestResult)=>Journal.record('pin-deleted',JSON.stringify(extra),code,requested,operation)});
  } else if(action==='pin-close'){
   if(Driver.pin){Driver.pin.unregisterInputer();}if(Driver.idm){Driver.idm.closeSession(Driver.account);}
   Journal.record('pin-closed');
  } else if(action==='dfs-connect'){
   const requested=Journal.requestId;const operation=Journal.action;
   await fs.connectDfs(p.network_id as string,{onStatus:(networkId: string,status:number)=>Journal.record('dfs-status',JSON.stringify({networkId,status}),status,requested,operation)});
   Journal.record('dfs-connected',JSON.stringify({network_id:p.network_id,root:context.distributedFilesDir}));
  } else if(action==='dfs-disconnect'){
   await fs.disconnectDfs(p.network_id as string);Journal.record('dfs-disconnected',JSON.stringify({network_id:p.network_id}));
  } else if(action==='dfs-cleanup'){
   const path=context.distributedFilesDir+'/services579-'+RUN+'.bin';let missing=0;
   try{fs.unlinkSync(path);}catch(error){const actual=error as BusinessError;if(actual.code!==13900002){throw error;}missing=actual.code;}
   let disconnectStatus=0;
   if(p.network_id){try{await fs.disconnectDfs(p.network_id as string);}catch(error){const actual=error as BusinessError;if(actual.code!==13600004){throw error;}disconnectStatus=actual.code;}}
   Journal.record('dfs-cleanup-owned',JSON.stringify({path,missing,disconnectStatus,exists:fs.accessSync(path)}));
  } else if(action==='dfs-write'||action==='dfs-read'||action==='dfs-delete'){
   const filename='services579-'+RUN+'.bin';const path=context.distributedFilesDir+'/'+filename;
   if(action==='dfs-write') {const f=fs.openSync(path,fs.OpenMode.CREATE|fs.OpenMode.READ_WRITE|fs.OpenMode.TRUNC);
    const text=p.data as string;try{fs.writeSync(f.fd,text);fs.fsyncSync(f.fd);}finally{fs.closeSync(f);}Journal.record('dfs-written',JSON.stringify({path,data:text}));}
   if(action==='dfs-read') {const f=fs.openSync(path,fs.OpenMode.READ_ONLY);const b=new ArrayBuffer(65536);let n=0;try{n=fs.readSync(f.fd,b);}finally{fs.closeSync(f);}
    Journal.record('dfs-read',JSON.stringify({path,hex:Driver.hex(new Uint8Array(b,0,n))}));}
   if(action==='dfs-delete'){fs.unlinkSync(path);Journal.record('dfs-deleted',JSON.stringify({path}));}
  } else if(action==='exit'){await context.terminateSelf();}
  else {throw new Error('unlisted service action '+action);}
  Journal.record('done');
 }
}
