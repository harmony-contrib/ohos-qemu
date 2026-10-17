Fixture-only follow-up after the complete actual Linux host batch03. Preserve
all previous deliveries and all original failure logs. The GCC diagnostics name
one missing callback type in both baseline/candidate FinalizeRelease, with the
remaining errors cascading from that missing type. The actual production method
uses std::shared_ptr<AudioStreamCallback>, but the host carrier only defined
FakeStreamCallback and declared its weak_ptr with that separate name.

The single fixture edit adds the host-only AudioStreamCallback alias, declares
streamCallback_ as std::weak_ptr<AudioStreamCallback>, and spells the callback's
existing int argument through StateChangeCmdType. The underlying dependency and
method behavior are unchanged. This is not a new public interface or production
implementation. Production methods, full real FutexTool and AudioRingCache,
sanitizers, error/assertion expectations, compiler selection and diagnostics are
unchanged. Static review also covered the fixture IPC acknowledgement carrier,
OHAudioBuffer methods, BufferDesc fields, AppBundle static call, Trace/ClockTime,
securec, queue/handler and position callback dependencies. No further specific
missing declaration was identified; this does not claim a successful compile.

Root's batch03 also stopped host executables at /tmp's noexec boundary and had
an environment PIL dependency failure; root owns those environment repairs.
There is no source change here to bypass execution permissions or suppress that
import. Root must rerun the complete same sanitized Linux batch after fixing the
environment. The HDI method harness passed its compilation step before its
execution was denied, which is not native product or runtime acceptance.

No tests, AST validation, compiler, SDK, Docker, guest/HDC/QMP, signals or Git
operation was performed by media. No product source or manifest was modified.
Delivery03 records exact updated fixture/file hashes and the immutable batch03
log receipt. Old02 remains historical, all capability/native/runtime gaps and
closure count0 remain. Media freezes and releases its reopened lease now.
