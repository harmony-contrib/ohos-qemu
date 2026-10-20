import { common, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import sim from '@ohos.telephony.sim';
import cellular from '@ohos.telephony.data';
import { Journal, Request } from './Journal';
import { ApnRead } from './ApnRead';

// A genuine read captured before the owned UI selection, retained only in this
// caller generation. No request can supply an APN id or write a catalog row.
let remembered: string | undefined = undefined;

interface Snapshot {
  hasSim: boolean; state: sim.SimState; active: boolean;
  accounts: sim.IccAccountInfo[]; defaultSlot: number; dataState: cellular.DataConnectState;
  iccid?: string; operator?: string;
}
async function snapshot(): Promise<Snapshot> {
  const hasSim: boolean = await sim.hasSimCard(0);
  const value: Snapshot = { hasSim, state: await sim.getSimState(0), active: await sim.isSimActive(0),
    accounts: await sim.getActiveSimAccountInfoList(), defaultSlot: await cellular.getDefaultCellularDataSlotId(),
    dataState: await cellular.getCellularDataState() };
  if (hasSim) { value.iccid = await sim.getSimIccId(0); value.operator = await sim.getSimOperatorNumeric(0); }
  return value;
}
export async function run(context: common.UIAbilityContext, want: Want): Promise<void> {
  const request: Request = Journal.request(want);
  Journal.write(context,request,'begin',0,request.action);
  try {
    if (request.action === 'inspect') {
      Journal.write(context,request,'snapshot',0,JSON.stringify(await snapshot()));
    } else if (request.action === 'select-default') {
      Journal.write(context,request,'before',0,JSON.stringify(await snapshot()));
      // These genuine public calls reach Telephony/RadioProtocolController. They
      // neither assign SIM state nor write an account/default-slot database.
      await sim.activateSim(0);
      Journal.write(context,request,'activate.return',0,'native promise resolved');
      await cellular.setDefaultCellularDataSlotId(0);
      Journal.write(context,request,'select.return',0,'native promise resolved');
      Journal.write(context,request,'snapshot',0,JSON.stringify(await snapshot()));
    } else if (request.action === 'apn-read') {
      Journal.write(context,request,'apn',0,await new ApnRead(context).read());
    } else if (request.action === 'apn-remember') {
      if (remembered !== undefined) { throw new Error('APN baseline already remembered'); }
      remembered = await new ApnRead(context).read();
      Journal.write(context,request,'apn',0,remembered);
    } else if (request.action === 'open-apn') {
      await cellular.showSystemApnSettings(context);
      Journal.write(context,request,'open.return',0,'public native promise resolved');
    } else if (request.action === 'restore-preference') {
      if (remembered === undefined) { throw new Error('live original APN baseline missing'); }
      const original = JSON.parse(remembered) as OriginalPreference;
      // Public native CellularDataService::SetPreferApn -> permission checked
      // DataShare service. In particular original -1 is a genuine API value,
      // not a shell/database write or a made-up valid APN row.
      const changed: boolean = await cellular.setPreferredApn(original.preferred);
      Journal.write(context,request,'restore.return',0,JSON.stringify(changed));
      Journal.write(context,request,'apn',0,await new ApnRead(context).read());
    } else if (request.action === 'restore-default') {
      // The binding admits only an original slot0 baseline before any SIM or
      // preference mutation. No API exists to restore absent slot -1 here.
      await cellular.setDefaultCellularDataSlotId(0);
      Journal.write(context,request,'select.return',0,'public native promise resolved');
      Journal.write(context,request,'snapshot',0,JSON.stringify(await snapshot()));
    } else if (request.action === 'deactivate') {
      await sim.deactivateSim(0);
      Journal.write(context,request,'deactivate.return',0,'public native promise resolved');
      Journal.write(context,request,'snapshot',0,JSON.stringify(await snapshot()));
    } else { throw new Error('fixed actual virtual-SIM control action required'); }
    Journal.write(context,request,'done',0,request.action);
  } catch (error) {
    // Actual showSystemApnSettings rejects null for an inactive/default SIM.
    // Preserve that exact payload. -1 is a journal sentinel, not BusinessError.
    if (error === null || error === undefined) {
      Journal.write(context,request,'error',-1,error === null ? 'null' : 'undefined');
      return;
    }
    const actual = error as BusinessError;
    Journal.write(context,request,'error',typeof actual.code === 'number' ? actual.code : -1,
      typeof actual.message === 'string' ? actual.message : JSON.stringify(error));
  }
}

interface OriginalPreference { preferred: number; }
