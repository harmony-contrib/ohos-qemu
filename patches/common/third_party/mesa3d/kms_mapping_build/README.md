# ARMv7 Mesa action inputs

Apply after generated ARMv7 product/Mesa configuration, before traversal.
Track the shared historical-source mapping helper and its numbered patch as
actual GN action inputs. Leave all flags, outputs, dependencies and non-QEMU
Mesa providers unchanged.

Complete generated-before/repaired hashes reject unknown edits. A checkout
without the generated ARMv7 action may skip only the exact pinned official
GN source, never an arbitrary file that happens to lack the action string.
