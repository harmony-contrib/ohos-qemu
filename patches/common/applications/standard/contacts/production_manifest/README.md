# Contacts production manifest

Merge the duplicated MainAbility skill `uris` keys so the intended tel and
calllog/voice/main handlers both survive JSON5 parsing. Remove the test-only
Hypium development dependency from production preparation; ohosTest is not a
product HAP target. No production source imports Hypium. Preserve the historical
pickerSheet dependency until the official SDK compiled import audit establishes
whether it is unused. All abilities, permissions and profiles remain unchanged.
This is source preparation, not BMS or picker runtime acceptance.
