# Final newlines in the fixed Release adapter input headers

TPC WebView revision: `4237e061441ea9392e83a353c0d52cb1c44404b3`.

After the ANGLE extension include paths are repaired, the actual full build
exposes fourteen adapter headers lacking a final newline. ANGLE keeps
`-Wnewline-eof -Werror`; do not suppress these warnings or turn off its backend.

The patch adds exactly one LF to each existing source header. Pre/post checks
compare the entire content with its exact Git blob and reject any other edit
or alias before applying. Signatures, semantics and the generated bridge ABI
are byte-identical apart from the final LF. No new interface file is added.

The official prepare step copies these source inputs to its generated include
tree; that output tree is not edited by this component. Apply before prepare
and repeat through the full-core hook. This is not native/HAP/guest acceptance.
