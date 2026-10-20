/* Source for the real public caller. No APN write shortcut is exposed here. */
import common from '@ohos.app.ability.common';
import data from '@ohos.telephony.data';
import sim from '@ohos.telephony.sim';
import dataShare from '@ohos.data.dataShare';
import dataSharePredicates from '@ohos.data.dataSharePredicates';

interface ApnRow {
  id: number;
  name: string;
  apn: string;
  mcc: string;
  mnc: string;
  types: string;
  edited: number;
}

export class ApnRead {
  private context: common.UIAbilityContext;
  constructor(context: common.UIAbilityContext) { this.context = context; }

  async environment(): Promise<string> {
    const slot: number = await data.getDefaultCellularDataSlotId();
    const max: number = sim.getMaxSimCount();
    const active: boolean = slot >= 0 && slot < max ? await sim.isSimActive(slot) : false;
    return JSON.stringify({ slot, max, active });
  }

  async read(): Promise<string> {
    // Query the actual public permission-gated consumer first. Negative roles
    // cannot reach the independent DataShare query through this program.
    const apns = await data.queryAllApns();
    const slot: number = await data.getDefaultCellularDataSlotId();
    const max: number = sim.getMaxSimCount();
    const active: boolean = slot >= 0 && slot < max ? await sim.isSimActive(slot) : false;
    if (!active) { return JSON.stringify({ slot, max, active, apns, rows: [], preferred: -1 }); }
    const account = await sim.getSimAccountInfo(slot);
    const numeric: string = await sim.getSimOperatorNumeric(slot);
    const base: string = 'datashare:///com.ohos.pdpprofileability/net/pdp_profile';
    const helper = await dataShare.createDataShareHelper(this.context, base);
    const rows: ApnRow[] = [];
    let preferred: number = -1;
    try {
      const predicate = new dataSharePredicates.DataSharePredicates();
      predicate.equalTo('mccmnc', numeric);
      const catalog = await helper.query(base + '?simId=' + account.simId, predicate,
        ['profile_id', 'profile_name', 'apn', 'mcc', 'mnc', 'apn_types', 'edited']);
      try {
        if (catalog.rowCount > 10000) { throw new Error('bounded actual APN catalog required'); }
        if (catalog.goToFirstRow()) {
          do {
            rows.push({ id: catalog.getLong(catalog.getColumnIndex('profile_id')),
              name: catalog.getString(catalog.getColumnIndex('profile_name')),
              apn: catalog.getString(catalog.getColumnIndex('apn')),
              mcc: catalog.getString(catalog.getColumnIndex('mcc')),
              mnc: catalog.getString(catalog.getColumnIndex('mnc')),
              types: catalog.getString(catalog.getColumnIndex('apn_types')),
              edited: catalog.getLong(catalog.getColumnIndex('edited')) });
          } while (catalog.goToNextRow());
        }
      } finally { catalog.close(); }
      const selected = await helper.query(base + '/preferapn?Proxy=true&simId=' + account.simId,
        new dataSharePredicates.DataSharePredicates(), ['profile_id']);
      try {
        if (selected.rowCount > 1) { throw new Error('ambiguous actual preferred APN result'); }
        if (selected.goToFirstRow()) { preferred = selected.getLong(selected.getColumnIndex('profile_id')); }
      } finally { selected.close(); }
    } finally { await helper.close(); }
    rows.sort((left: ApnRow, right: ApnRow) => left.id - right.id);
    return JSON.stringify({ slot, max, active, simId: account.simId, numeric, apns, rows, preferred });
  }
}
