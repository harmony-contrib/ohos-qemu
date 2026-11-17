# API26 depth-data contracts

Register the public depth accuracy values using native CameraStandard constants
and quality levels using the existing SDK/metadata wire contract (0/1/2).
Exclude the internal invalid accuracy sentinel. Correct the DepthData getter
spelling to dataAccuracy, forwarding the same real per-object accuracy value.

Propagate every new NAPI registration error. Do not change camera eligibility,
stream metadata, permissions or hardware capability advertisement. This patch
does not create a depth camera or synthesize successful depth measurements;
export/compile fixtures are not depth-output or new-package acceptance.
