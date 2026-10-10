# Public contact data-record classes

Pinned ContactsData: `c73bd27daa3fcd8ed6099b17cbffbd7021e3873e`.
The public JS facade already exports nine record class names, but the native
initializer only creates classes with static constants, leaving those names
undefined. Register ContactAttributes, Group, Holder, Name, NickName, Note,
Organization, Portrait and Website with real NAPI class constructors.

Use the same data-record constructor as existing Contact/Email/PhoneNumber
classes. Caller-owned properties remain caller-owned; no database values or
service success are fabricated. Holder uses the SDK's documented bundleName
default and the existing CONTACT_PACKAGE_NAME constant. Do not change database
conversion, queries, permissions, provider behavior, enums or C++ object layout.
Registration failure keeps module initialization failed rather than claiming a
complete class surface. Existing pending exceptions are preserved.

Keep the new header and module initializer separate from contacts_api.cpp so
the existing exact ContactSyncMode patch remains independently repeatable.
Require typed ordinary-app construction, property round trips and instance
isolation on a newly packaged guest. This is not a substitute for real contact
database/provider authorization tests. This candidate is not in frozen R34.
