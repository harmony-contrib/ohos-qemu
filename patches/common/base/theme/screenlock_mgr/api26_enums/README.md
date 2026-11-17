# ScreenLock public enum contract candidate

Share the unchanged native AuthState definition between service/client NAPI;
register AuthState, StrongAuthReasonFlags and UnlockPolicy with checked NAPI
operations. Keep service-only authentication intermediate states and security
enhancement bits out of the public object. Preserve all authentication, caller,
permission and token checks and real lock/unlock/policy behavior.

Propagate original function/enum registration failures instead of reporting
successful module initialization. Host/object checks are not package acceptance
or proof that an ordinary app can perform privileged authentication operations.
