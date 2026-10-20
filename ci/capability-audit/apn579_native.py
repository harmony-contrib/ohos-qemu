"""Explicit additional helper selection in root's existing platform C builder."""
from pathlib import Path
HERE=Path(__file__).resolve().parent

def helper_recipes():
    return {'apn579_modem_peer':{'fixture':'../apn579_modem_peer.c','source_file':str(HERE/'apn579_modem_peer.c'),
        'language':'c','anchors':[{'graph':'obj/base/telephony/ril_adapter/services/vendor/ril_vendor.ninja',
          'object':'obj/base/telephony/ril_adapter/services/vendor/src/ril_vendor/vendor_adapter.o',
          'source':'base/telephony/ril_adapter/services/vendor/src/vendor_adapter.c',
          'header':'base/telephony/ril_adapter/services/vendor/include/vendor_adapter.h'}],
        'libraries':[],'headers':[],'extra_includes':[]}}
