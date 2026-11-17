Select complete CallSetting, CommunicationSetting and caption sources for the
three QEMU products. The same graph selects the ordinary build's prepared
PortalLogin, MediaController and IntelligentScene HAPs. Their original pinned
payloads and permission profiles are retained while both signatures are bound
to the existing public OpenHarmony OS signer by qemu_ui_providers.py.

All whole-source before/final hashes and actual repository HEADs are fixed.
The source transaction preserves unknown concurrent changes and restores its
own writes on failure. Acceptance requires the newly packaged QEMU image.
