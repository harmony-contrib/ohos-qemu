# Guest fixture preparation

The original four real API26 caller builds remain: applications, Audio/Calendar,
knowledge and live inputs. They compile fourteen real callers used in the new
QEMU guest. The separate NativeStrip scratch replay and its pass receipt are
removed from both preparation and the consumer. The live-input consumer checks
the actual completed Hvigor task log, its produced HAP member bytes and ARM64
ELF ABI instead of running an independent strip experiment.

Seven fixed-before source patches cover the existing private SDK/assembly
execution harness. Apply them to a fresh derived harness, retaining the actual
SDK-batch467 live runner's cancellation/log behavior. The canonical live-input
consumer is the sibling `batch_system_live_inputs_suite.py`. Update actual
source pins after deriving the new committed epoch; no old host pass receipt is
required or created. SDK compilation/signing are prerequisites for the real
guest callers. Only newly packaged QEMU runtime results are acceptance evidence.
