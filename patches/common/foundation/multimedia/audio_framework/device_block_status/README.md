# Public Audio DeviceBlockStatus values

AudioFramework `6932fa64335b8272ca4a59de7808ab0d6c9eae7a` has the real
`DEVICE_UNBLOCKED`/`DEVICE_BLOCKED` C++ values and the public microphone blocked
callback, but never registers the API26 SDK's `DeviceBlockStatus` object.

This component registers only `UNBLOCKED`/`BLOCKED` through the existing native
enum helper using those original C++ values. The whole source file must match
the fixed pristine or exact final hash; false markers and partial changes are
not accepted. Both profiles and all three ABIs use this common component.

No callback, service, permission, hardware or routing behavior is changed.
Object presence or compilation is not proof of microphone blocking/events.
Actual ordinary-app enum member values and the backend require separate new
package evidence; no missing capability is closed from this patch alone.
