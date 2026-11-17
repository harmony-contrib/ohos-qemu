# Standard VPN component entry points

Each child directory owns numbered unified patches and one independently
executable `apply.sh`. All accept `--source-root ROOT` and repeated
`--product PRODUCT` arguments. Generated helpers and signed assets live in the
owning component's `files/` or `assets/` directory. The parent `../apply.sh`
applies the components in dependency order.
