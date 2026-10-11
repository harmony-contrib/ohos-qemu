# Public persistence option records

The API 26 SDK declares `ConnectOptions` and `ConnectOptionsCollections` as
constructible classes, with the latter extending the former. The dynamic
implementation accepts their structural fields but only declares TypeScript
interfaces internally, and exports neither constructor in jsStateManagement.js.

Add actual JavaScript data classes to the module export. Do not change the
existing persistence implementation, field validation, default area selection,
storage paths or permissions. No database or successful persistence is simulated.
These classes only represent caller-supplied options; runtime backend behavior
must still be validated independently.

Pinned ace_engine: e55e178228b9f6388b15d3024e8caf125fa293d7.
KB-first inspection: docs/sdk/ArkUI_SDK_API_Knowledge_Base.md, section 6;
actual dynamic source: engine/jsStateManagement.js and
state_mgmt/src/lib/sdk/v2_persistence.ts (interfaces and globalConnect).
