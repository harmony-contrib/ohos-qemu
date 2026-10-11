# MediaLibrary numeric BusinessError

On fixed Release source the shared sync throw functions and async error-object
factory use NAPI's string-valued error code. The SDK requires BusinessError.code
to be a number. Build the existing Error/message with a numeric code property,
publish it only after all NAPI operations succeed, and preserve an already
pending helper exception rather than overwriting its specific validation code
with an enclosing wrapper's generic failure. Both existing sync overloads and
the shared async factory use the repair.

This does not change any error-code value, message construction, public API,
permission check, query, database or native layout. It is separate from the real
ResultSet index/close repair. It is not a query success or all MediaLibrary API
acceptance claim, and it is not in the frozen R39 package. Real new-package
factory, rejection and post-error recovery checks remain mandatory.
