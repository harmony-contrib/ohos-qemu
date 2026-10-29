# Register the existing AvisMetadata class

Pinned image_framework: `711db218c8d1c4d6546b28d8cf466059644dfa77`.
`InitAvisMetadata` already defines the native class, retains its constructor and
registers its environment cleanup. The factory calls it on a private exports
object when necessary, but the public image module omitted it from startup.

Add that existing initializer beside the other metadata initializers, within
the same non-Android/non-iOS branch. No parser, constructor, fields, default
values, error mapping, permissions, other-language interfaces or C++ ABI change.
User explicitly approved this narrowly scoped registration. The image framework
binding and metadata knowledge guides were read before implementation.

Do not treat real AVIS factory reads as proof of a public constructor export.
Require a newly packaged guest to exercise ordinary typed construction,
instance isolation and factory-instance identity, alongside actual AVIS reads
and existing image regression. No matching dynamic XTS constructor test has yet
been located in the pinned image test trees; static tests are not substituted.
This component is not in frozen R34. No guest or six-package closure is claimed.
