The new R47 package returned the permission error as the string `"201"` for
`getData` Promise, callback and `getDataSync`. API26 BusinessError requires a
numeric code. The actual three getter journals and strict verifier rejection
are retained under `r47-env-selection-render-diagnostic-04`.

This exact successor of `read_permission_errors` changes the current read API
to opt into numeric errors. Its shared async helper retains the old string
behavior for existing callers using `SetErrInfo`; `SetBusinessErrInfo` selects
the SDK shape for the current read API's permission and concurrent-task errors.
The synchronous permission error creates an Error with a numeric `code` before
throwing. Service authorization and clipboard content remain authoritative.

The parent recognizes only the complete exact three-file successor. Partial or
unknown edits fail before application; repeated package builds remain supported.
Compile both actual TUs and their modified header for every ABI, then build and
run a fresh representative. Compilation and the R47 failure observations do not
prove the repair at runtime or pass the complete first-artifact gate.
