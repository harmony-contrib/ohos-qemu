# Public ResultSet constructor

PhotoAccessHelper.query already returns the real Native ResultSet instance,
but the public JavaScript facade omits its constructor. Forward the original
native constructor so the SDK class and factory instance share their actual
prototype. No replacement constructor, prototype mutation, provider, permission
or SQL behavior is introduced. Apply after the complete Photo/Fusion/search,
recent-info and record-class facade stack; unknown wrapper bytes fail closed.

Validate the actual wrapper ABC and new-package query, values, cursor, NULL,
index/close errors and all three caller roles. Static forwarding alone is not
runtime acceptance.
