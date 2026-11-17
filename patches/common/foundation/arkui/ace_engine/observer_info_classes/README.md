# Dynamic observer info classes and density context

Pinned ace_engine: `e55e178228b9f6388b15d3024e8caf125fa293d7`.

Exports API 26 DensityInfo and WindowSizeLayoutBreakpointInfo constructors.
Real density and breakpoint callbacks use these classes, not plain objects.
Density callbacks also carry the real current container UIContext, using the
same frontend path as routerPageUpdate. No fake context or density is created.
Constructor references are environment-owned and cleaned on runtime shutdown.
Incomplete objects are not delivered after a NAPI allocation/property failure.
Original listener registration, mutation-safe dispatch and removal are retained.

One shared product entry applies the exact four-file component for phone/2in1.
The compiler fixture checks all three real TUs and the changed header on each ABI.
Lifecycle sanitizer tests execute the patched constructor code. The ordinary
observer-info HAP changes only its own window's density at both public bounds,
requires actual context/prototype/getter agreement, tests two subscribers and
two generations of specific/all removal, then restores its initial density.
The package gate requires that HAP's real archive-bound evidence. Host tests and
compilation alone do not close either contract.
