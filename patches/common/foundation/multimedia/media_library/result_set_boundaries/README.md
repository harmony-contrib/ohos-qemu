# Real ResultSet boundary repair

The pinned API26 class is already exported. It must be obtained from the real
PhotoAccessHelper.query factory; exporting another constructor is not a fix.
This component rejects missing, extra, nonnumeric, fractional, nonfinite and
out-of-int32 indices before conversion or database access, returns false for an
empty GoToFirstRow result just as GoToNextRow does, and preserves the existing
helper exception when close receives an unwrapped object instead of dereferencing
null. Valid RDB calls, public signatures, permissions, native class layout and
existing Uint8Array BLOB conversion remain unchanged.

The second independent diff converts the RDB variant's real SQL NULL
(`std::monostate`) to JavaScript null. Previously the generic converter returned
a null NAPI handle, yielding undefined for getValue and omitting the getRow
field. Existing numeric/string/bool/BLOB converters are retained.

The source file is pinned CRLF. The reviewable LF diff is mechanically converted
only for this exact file; original/final byte hashes and the common fail-closed
applicator still govern application and repeat application. Apply before GN for
both device profiles and all three ABIs. The separate business_error component
preserves numeric SDK errors and an already pending validation exception.

This is a next-batch candidate, not part of the frozen R39 representative. Host
NAPI fixtures explicitly substitute the RDB backend, and full product TU objects
are not a query factory/provider or new-package runtime acceptance. Do not close
the ResultSet ledger item until actual privileged queries, permission denials,
typed values, cursors, empty results and post-error recovery pass in a new package.
