# SDK spring context state semantics

User approved the three minimum SpringLoadingContext contract repairs.
Use the actual native state to expose undefined dragInfos/currentConfig in
CANCEL, and ignore updateConfiguration outside BEGIN, as the fixed dynamic SDK
requires. BEGIN validation, defaults, truncation and native ownership remain
unchanged. Public signatures, permissions, UDMF and C++ object layout are
unchanged; no callback is synthesized.

This is separate from the real-class export and timer/lifecycle components,
with its own exact project/file pre- and post-hashes. Both dynamic frontend
variants must compile across three ABIs. Host preparation does not close the
actual new-package hover/configuration/abort behavior requirement.
Not included in already frozen R37 build inputs.
