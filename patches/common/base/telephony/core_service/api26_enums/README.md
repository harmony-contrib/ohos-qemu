# API26 CoreService enum exports

Expose `NrOptionMode` and `DsdsMode` using the same native constants consumed
by the radio/SIM APIs. Preserve existing flat radio values and all backend,
permission and slot checks. No modem/SIM state is fabricated. The ordinary
runtime-enum probe independently reads every typed and native member; enum
validation does not attest cellular connectivity or DSDS behavior.
