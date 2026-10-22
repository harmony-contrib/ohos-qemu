"""Fixed actual normal telephone DATA projection; no resource or verdict."""
from pathlib import Path
from capability578_owned_io import require
from settings_idle579_bindings import load_ref
from hap_identity_binding import strict_json
from telephony579_tun import product_input,NATIVE_SOURCES


def assemble_telephony(export_ref,*,package,target):
    value=strict_json(load_ref(export_ref).decode())
    require(set(value)=={'schema','source_commit','archive','product','normal_source_context','source_export',
        'installed_runtime_profile','native_sources','library','rtt_source_facts','original_export_receipt',
        'original_profile_receipt','ims_image_inventory'} and value['source_commit']==package['source_commit'] and
        value['archive']==package['archive'] and value['product']==target['product'],
        'finite actual normal new-package telephone inputs only')
    from audio579_common import source_guard,doc
    context=doc(source_guard(value['normal_source_context']))
    require(context['source_commit']==package['source_commit'],'same complete normal source context')
    product_input({'telephony579':{'product_export':export_ref}},package['archive']['sha256'],target['product'])
    profile=strict_json(load_ref(value['installed_runtime_profile']).decode())
    require(profile['arch']==target['arch'] and profile['device']==target['device'],'actual target architecture/profile')
    source=strict_json(load_ref(value['source_export']).decode())
    require(source['source_commit']==package['source_commit'] and source['archive_sha256']==package['archive']['sha256'] and
        source['product']==target['product'] and source['source_kind']=='actual_shared_source_and_out_readonly_export' and
        source['resources_executed'] is True and source['cleanup_verified'] is True and source['failures']==[],
        'actual completed original normal RO source export')
    for logical in NATIVE_SOURCES:
        require(value['native_sources'][logical]==source['files'][logical],'full actual native source belongs to this product')
    for name in ('rtt_source_facts','original_export_receipt','original_profile_receipt','ims_image_inventory'):load_ref(value[name])
    return dict(schema='telephony579-normal-product-inputs/v1',product_export=export_ref,
        normal_source_context=value['normal_source_context'])
