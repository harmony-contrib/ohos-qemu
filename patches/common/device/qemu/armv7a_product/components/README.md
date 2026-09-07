# armv7a_virt component entry points

Each child directory owns numbered unified patches and an independently
executable `apply.sh`. Pass `--source-root ROOT`; the parent `../apply.sh`
applies all components in dependency order. No legacy overlay marker or entry
point is retained.
