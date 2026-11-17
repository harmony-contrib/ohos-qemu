# ArkWeb synchronous BusinessError codes

`napi_throw_error` creates a string-valued `code`, contrary to the numeric
`BusinessError.code` SDK contract. The shared synchronous error helper now
creates a real JavaScript Error, retaining its message and stack, and assigns
the numeric code and BusinessError name before throwing it.

All existing parameter, lifecycle and permission checks remain in their original
callers. Asynchronous `{code, message}` results are unchanged. This is not an
error-to-success conversion. The ordinary ArkWeb factory probe checks rejected
negative body-stream read size and successful subsequent reads.
