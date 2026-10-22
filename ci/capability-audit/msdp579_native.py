"""One explicit product-toolchain C++ NAPI helper, actual selected GN only."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
ANCHORS=(dict(graph='obj/base/msdp/device_status/interfaces/innerkits/devicestatus_client.ninja',
 object='obj/base/msdp/device_status/frameworks/native/src/devicestatus_client/stationary_manager.o',
 source='base/msdp/device_status/frameworks/native/src/stationary_manager.cpp',
 header='base/msdp/device_status/interfaces/innerkits/include/stationary_manager.h'),)
def helper_recipes():
 return {'msdp579_napi':dict(fixture='../msdp579/native/Algorithms.cpp',source_file=str(HERE/'msdp579/native/Algorithms.cpp'),
  kind='shared_napi',output_basename='libmsdp579.so',anchors=[dict(a) for a in ANCHORS],
  libraries=['msdp/device_status/libdevicestatus_client.z.so','arkui/napi/libace_napi.z.so','communication/ipc/libipc_single.z.so'],
  headers=[a['header'] for a in ANCHORS]+['base/msdp/device_status/interfaces/innerkits/include/devicestatus_callback_stub.h'],
  extra_includes=['base/msdp/device_status/interfaces/innerkits/include','base/msdp/device_status/utils/common/include','foundation/arkui/napi/interfaces/kits'])}


def prepared_input(build_ref,*,archive,product):
 from msdp579_contract import doc,ref,need,checked
 from production579_target import archive_manifest
 from msdp579_admission import admit
 report=doc(build_ref);target=archive_manifest(checked(archive))['context']
 need(report['product']==product==target['product'] and set(report['helpers'])=={'msdp579_napi'},'actual normal single-helper product')
 row=report['helpers']['msdp579_napi'];binary=ref(row['binary'])
 need(binary['sha256']==row['binary_sha256'],'actual normal addon changed')
 result=dict(binary=binary,build={k:build_ref[k] for k in ('path','sha256')},abi=target['abi'])
 admit(result,archive_sha256=archive['sha256'],arch=target['arch'])
 return result
