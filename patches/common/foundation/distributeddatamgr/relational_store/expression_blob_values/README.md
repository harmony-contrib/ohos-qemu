# SQLite expression and empty BLOB values

SQLite returns no column declaration for literals, parameters and computed
expressions. Preserve its actual BLOB runtime type instead of rejecting a
legitimate raw byte value. Explicit ASSET/ASSETS/FloatVector/BigInt declarations
retain their existing decoders. Zero-length ordinary BLOBs remain byte arrays,
not SQL NULL. This fixes actual PhotoAccessHelper.query getValue/getRow, and the
shared underlying RDB path. Unknown source edits fail closed.

Validate with real SQLite SQL/parameters, exact source and three actual product
TU commands, then rebuild and run new-package typed ResultSet and RDB callers.
Host checks and object files alone are not the representative behavior gate.
