# Call public enum contract candidate

Register all five missing API26 enum objects with checked NAPI operations.
Use the existing detailed/application/RTT native values where defined;
public-only constants do not manufacture call events or change internal ABI.
Old DetailedCallState/CallState exports remain intact.

RTT methods require BOTH upstream call-manager and cellular-call product
features. Enabling those implementations is separate from registering pure
protocol constants and does not itself provide an IMS/modem peer.

The enabled call-record path must use IMSCall::IsPrevRtt(), the accessor
actually declared/implemented by the fixed release. Correct the stale
GetIsPrevRtt() caller without changing the detailed/application call state,
RTT history value, non-IMS path, permissions or provider protocol.

The enabled RTT implementation uses ICU UnicodeString/ByteSink. Declare its
existing shared ICU provider in that same feature branch and in the component
dependency manifest. Do not depend on accidental transitive linkage, embed a
second static ICU, disable RTT or replace the UTF-8 implementation. The normal
GN/link and actual new-image behavior remain required separately.

The shared pre-traversal patch plan applies this component to all products.
Object and fixture checks are not new-archive guest or actual telephony
behavior evidence; RTT has to be validated against the real provider separately.
