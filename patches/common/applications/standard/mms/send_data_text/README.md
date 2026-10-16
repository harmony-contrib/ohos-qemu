# Reuse the real MMS recipient/draft UI for plain-text sendData

Pinned MMS project 26df98e3738f4219aa45efe6a3e7f6b1be55c051. The component
changes only module.json5, WantUtil.ets and the new SendDataPayload.ets. Original
entry identity, exports, permissions, skills and signature are retained. The new
text/plain MIME-only skill advertises the behavior implemented by this patch.
It does not replace the existing file/UTD skills or claim their unfinished path.

Previously the normal sendData branch required ability.picker.records, while
the ordinary Browser caller sends a text stream directly. The fallback did not
copy that stream into the existing TransmitMsg model. The new path validates a
single non-empty bounded text stream, builds the existing buildThirdParam draft
model, awaits the real DynamicLoader('TransmitMsg'), and navigates to the existing
recipient/preview UI. Only its original user-operated send UI can send a message.
No SMS API, synthetic success or forced destination is added. Incoming arbitrary
recipient, content flags and isRcs values cannot enter this new draft route.

String and single-string-array streams are accepted; empty/multi-text/invalid
text is visibly refused. File URIs, non-text MIME and picker-record payloads
remain on their original source path. Text parsing never opens a URI or treats
it as granted file content. A later Want invalidates the old asynchronous draft
navigation. Loader/validation failure shows an honest error and sends nothing.

The fixed source's original attachment buildTransmitParam body is mostly
commented and can return an empty list; this candidate does not certify file
sharing into MMS. Bluetooth's actual ShareExtension additionally requires the
absent HMS collaboration.systemShare runtime. Those are explicit remaining
backend gaps, not solved by adding a manifest handler or a generic alias.

Main owns MMS source build packaging, all build metadata/GN, unchanged profile
signing/preinstall authorization, real API26 compilation, and fresh phone
recipient/draft/cancel/send validation. Unit fixtures execute the actual patched
parser/router methods but do not prove HAP behavior or telephony delivery.
