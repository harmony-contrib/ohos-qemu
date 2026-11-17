# WithEnv default font scale from the owning view

The API26 ordinary caller observed undefined FONT_SCALE outside a configured
WithEnv scope. The bridge returned no value whenever the environment manager
found no override, including notifications that remove an override.

Resolve the unconfigured font scale from the owning UINode pipeline for both
queries and update notifications. Keep configured values, invalid-value handling,
direction conversion and unsupported keys unchanged. A detached view without
its pipeline still returns no value rather than inventing a configuration.

This candidate requires actual fresh-package runtime validation, including
scope isolation, override removal and distinct window configuration boundaries.
