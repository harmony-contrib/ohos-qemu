// Fixed real source-registered public calls. No city/expected values are shipped here.
const CASES = [
  {
    "id": "location-1810256",
    "api": "getNumberLocation",
    "numbers": [
      "+8618102560000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1371738",
    "api": "getNumberLocation",
    "numbers": [
      "+8613717380000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1332973",
    "api": "getNumberLocation",
    "numbers": [
      "+8613329730000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1560862",
    "api": "getNumberLocation",
    "numbers": [
      "+8615608620000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1372032",
    "api": "getNumberLocation",
    "numbers": [
      "+8613720320000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1997046",
    "api": "getNumberLocation",
    "numbers": [
      "+8619970460000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1567616",
    "api": "getNumberLocation",
    "numbers": [
      "+8615676160000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1341969",
    "api": "getNumberLocation",
    "numbers": [
      "+8613419690000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1342981",
    "api": "getNumberLocation",
    "numbers": [
      "+8613429810000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-1590719",
    "api": "getNumberLocation",
    "numbers": [
      "+8615907190000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-0086",
    "api": "getNumberLocation",
    "numbers": [
      "008618102560000"
    ],
    "exact": true,
    "route": 1,
    "operation": "location"
  },
  {
    "id": "location-short-exact",
    "api": "getNumberLocation",
    "numbers": [
      "+861810256"
    ],
    "exact": true,
    "route": 1,
    "operation": "empty-location"
  },
  {
    "id": "location-empty",
    "api": "getNumberLocation",
    "numbers": [
      ""
    ],
    "exact": true,
    "route": 1,
    "operation": "empty-location"
  },
  {
    "id": "location-unknown-short",
    "api": "getNumberLocation",
    "numbers": [
      "42"
    ],
    "exact": true,
    "route": 1,
    "operation": "empty-location"
  },
  {
    "id": "locations-batch",
    "api": "getNumberLocations",
    "numbers": [
      "+8618102560000",
      "+8613717380000",
      "+8613329730000",
      "+8615608620000",
      "+8613720320000",
      "+8619970460000",
      "+8615676160000",
      "+8613419690000",
      "+8613429810000",
      "+8615907190000",
      "+8618102560000",
      "42",
      "",
      "008618102560000"
    ],
    "exact": true,
    "route": 1,
    "operation": "locations"
  },
  {
    "id": "yellow-10086",
    "api": "getNumberMarkInfo",
    "numbers": [
      "10086"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "yellow-1008611",
    "api": "getNumberMarkInfo",
    "numbers": [
      "1008611"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "yellow-10010",
    "api": "getNumberMarkInfo",
    "numbers": [
      "10010"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "yellow-10011",
    "api": "getNumberMarkInfo",
    "numbers": [
      "10011"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "yellow-10000",
    "api": "getNumberMarkInfo",
    "numbers": [
      "10000"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "yellow-10001",
    "api": "getNumberMarkInfo",
    "numbers": [
      "10001"
    ],
    "exact": true,
    "route": 2,
    "operation": "yellow"
  },
  {
    "id": "mark-absent-before",
    "api": "getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-absent"
  },
  {
    "id": "mark-create-read",
    "api": "setNumberMarkInfo+getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-create"
  },
  {
    "id": "mark-update-read",
    "api": "setNumberMarkInfo+getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-update"
  },
  {
    "id": "mark-delete-read",
    "api": "setNumberMarkInfo+getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-delete"
  },
  {
    "id": "account-foreign-read",
    "api": "getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-account-empty"
  },
  {
    "id": "account-restored-read",
    "api": "getNumberMarkInfo",
    "numbers": [
      "$owned_number"
    ],
    "exact": true,
    "route": 2,
    "operation": "mark-account-owned"
  }
];
export function request580(caseId, ownedNumber, ownerRun) {
  const matches = CASES.filter((row) => row.id === caseId);
  if (matches.length !== 1 || !/^[0-9a-f]{32}$/.test(ownerRun)) { throw new Error('foreign Number580 request'); }
  const row = matches[0];
  const numbers = row.numbers.map((value) => value === '$owned_number' ? ownedNumber : value);
  return JSON.stringify({caseId, api:row.api, numbers, exact:row.exact, operation:row.operation});
}
function encoded(value) { const text=JSON.stringify(value); return typeof text === 'string' ? text : '<undefined>'; }
export function invoke580(context, requestJSON, ownerRun, step) {
  const request = JSON.parse(requestJSON);
  const number = request.numbers[0];
  const native = requireNapi('telephony.numberidentity');
  if (step === 'write') {
    const kind = request.operation === 'mark-delete' ? 0 : 8;
    const tag = 'number580:' + ownerRun + (request.operation === 'mark-update' ? ':updated' : ':created');
    return native.setNumberMarkInfo(context, number, kind, tag).then(encoded);
  }
  if (request.operation.startsWith('mark-') || request.operation === 'yellow') {
    return native.getNumberMarkInfo(context, number).then(encoded);
  }
  if (request.operation === 'locations') {
    return native.getNumberLocations(context, request.numbers, request.exact).then(encoded);
  }
  return native.getNumberLocation(context, number, request.exact).then(encoded);
}

export function context580() {
  const radio = requireNapi('telephony.radio');
  const sim = requireNapi('telephony.sim');
  const locale = requireNapi('i18n');
  return radio.getPrimarySlotId().then((slotId) => Promise.all([
    radio.getISOCountryCodeForNetwork(slotId), sim.getISOCountryCodeForSim(slotId)
  ]).then((values) => JSON.stringify({slotId,networkIso:values[0],simIso:values[1],systemRegion:locale.System.getSystemRegion()})));
}
