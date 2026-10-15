# Preserve OpenVPN control failures and disconnected outputs

Pinned `netmanager_ext`: `8c41289750820fb2ddb347b1205cee9a7b527388`.
Use `apply.sh --source-root OPENHARMONY_ROOT`. Exact CRLF pre/post hashes and
the common installer preserve source bytes and reject partial/unknown edits.

Start validates the configured backend request before entering STARTED and
returns the public internal error when netsys rejects the request. STARTED
remains asynchronous; this path never synthesizes CONNECTED. Invalid config
and missing configuration directories leave a disconnected state. Stop returns
an error when netsys rejects it and does not claim the connection stopped.
Destroy always attempts the existing TUN/network cleanup, preserving its error
or a failed backend stop. A disconnected getter also clears an old caller-owned
configuration pointer rather than leaking stale connected output.

The regression compiles these real method bodies with explicit netsys doubles
and an actual temporary directory. It checks null/missing config, several
backend errors, start request state, failed stop state, cleanup/error precedence
and connected-to-disconnected output reuse. Existing nullable IPC/owner/account
tests also pass. This does not establish a running VPN or close a ledger item.
