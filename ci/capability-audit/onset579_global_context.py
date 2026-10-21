"""Explicit source-call seam AFTER Root's original package/kernel admission.

No generic data loader, mode flag, Owner, authority or resource is created.
The fixed implementation review does not replace actual package/kernel/config/boot proof.
"""
from dataclasses import dataclass
import hashlib,json
import onset579_global_clock as clock
from onset579_global_tools import checked


@dataclass(frozen=True)
class GlobalClockContext579:
    domain: clock.ClockDomain
    inventory_io_ref: dict


def from_original_kernel_admission(kernel,*,config_ref,actual_source_refs,inventory_io_ref):
    """Root's fixed source supplies the already-admitted typed kernel identity.

    A JSON file may supply immutable actual bytes, never select an implementation
    or mint the original package/launcher/kernel/Authority admission. Root must
    replay that original raw proof before constructing `kernel` in either actor.
    """
    clock.need(type(kernel) is clock.AdmittedKernelIdentity,'original actual typed kernel admission first')
    config=checked(config_ref).read_bytes()
    clock.need(hashlib.sha256(config).hexdigest()==kernel.actual_config_sha256,'original packaged generated config')
    clock.need(type(actual_source_refs) is dict and set(actual_source_refs)==dict(kernel.actual_source_hashes).keys(),
               'complete original actual source export member set')
    sources={name:checked(ref).read_bytes() for name,ref in actual_source_refs.items()}
    domain=clock.admit_global(kernel=kernel,config_raw=config,actual_sources=sources)
    clock.require_domain(domain)
    io=json.loads(checked(inventory_io_ref).read_text())
    clock.need(io['scope']=='actual_original_Owner_IO_only_NOT_acceptance' and io['closed'] is True and
               io['archive_sha256']==kernel.archive_sha256 and io['boot_id']==kernel.boot_id,
               'same original Root-retained closed inventory IO')
    return GlobalClockContext579(domain,dict(inventory_io_ref))
