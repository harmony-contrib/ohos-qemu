#!/usr/bin/env python3
"""Generate the scoped caller protocol component from the pinned source snapshot."""
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contact_picker_protocol'
META = json.loads((FIX / 'inspection.json').read_text())
PROJECT = META['project']
COMPONENT = ROOT / 'patches/common' / PROJECT / 'picker_result_protocol'


def original(relative):
    record = META['files'][relative]
    raw = gzip.decompress(base64.b64decode(record['gzip_base64']))
    assert hashlib.sha256(raw).hexdigest() == record['sha256']
    return raw


def change(text, before, after):
    assert text.count(before) == 1, before[:160]
    return text.replace(before, after)


js = original('contacts/src/contact.js').decode()
js = change(js, 'contact.startContactsPicker(gContext, config)', 'contact.startContactsPicker(context, config)')
js = change(js, '    if (option.filter !== undefined) {', '''    if (option.isAutoDismissOnNavigation !== undefined) {
      config.parameters.isAutoDismissOnNavigation = option.isAutoDismissOnNavigation;
    }
    if (option.filter !== undefined) {''')
a = js.index('function checkSelectParameter(')
b = js.index('export default {', a)
js = js[:a] + (FIX / 'select_impl.js').read_text() + '\n' + js[b:]

header = original('contacts/include/contacts_napi_utils.h').decode()
header = change(header, '    static napi_value ToInt32Value', '''    static napi_value StartContactSelection(napi_env env,
        const std::shared_ptr<OHOS::AbilityRuntime::AbilityContext> &ability,
        const std::shared_ptr<OHOS::AbilityRuntime::UIExtensionContext> &extension,
        const OHOS::AAFwk::Want &want, napi_ref callback);
    static napi_value ToInt32Value''')

utils = original('contacts/src/contacts_napi_utils.cpp').decode()
utils = change(utils, '#include "want.h"', '''#include "want.h"
#include "contact_picker_protocol.h"
#include "int_wrapper.h"
#include "string_wrapper.h"
#include "modal_ui_extension_config.h"
#include <uv.h>''')
utils = change(utils, 'ModalUICallback::ModalUICallback(', (FIX / 'selection_native.cpp.txt').read_text() + '\nModalUICallback::ModalUICallback(')

api = original('contacts/src/contacts_api.cpp').decode()
a = api.index('napi_value ContactsPickerSelect(')
b = api.index('napi_value ContactsPickerSave(', a)
api = api[:a] + '''napi_value ContactsPickerSelect(napi_env env, napi_callback_info info)
{
    size_t argc = MAX_PARAMS;
    napi_value argv[MAX_PARAMS] = {0};
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok) { return nullptr; }
    const bool valid = (argc == ARGS_TWO &&
        ContactsNapiUtils::MatchParameters(env, argv, { napi_object, napi_object })) ||
        (argc == ARGS_THREE &&
        ContactsNapiUtils::MatchParameters(env, argv, { napi_object, napi_object, napi_function }));
    if (!valid) {
        napi_throw(env, ContactsNapiUtils::CreateError(env, PARAMETER_ERROR));
        return nullptr;
    }
    auto context = std::make_unique<OHOS::ContactsApi::BaseContext>();
    context->env = env;
    if (!ParseAbilityContextReq(env, argv[0], context->context, context->uiExtensionContext)) {
        napi_throw(env, ContactsNapiUtils::CreateError(env, PARAMETER_ERROR));
        return nullptr;
    }
    OHOS::AAFwk::Want want;
    if (!AppExecFwk::UnwrapWant(env, argv[1], want)) {
        napi_throw(env, ContactsNapiUtils::CreateError(env, PARAMETER_ERROR));
        return nullptr;
    }
    want.SetElementName(CONTACT_PACKAGE_NAME, CONTACT_UI_EXT_ABILITY_NAME);
    want.SetParam(UI_EXT_TYPE, std::string(CONTACT_UI_EXT_TYPE));
    want.SetParam(UI_EXT_TARGETURL, std::string("BatchSelectContactsPage"));
    NAPI_CALL(env, ContactsNapiUtils::GetParamCallback(env, context, argc, argv));
    // Transfer the optional native callback reference exactly once. Public JS
    // uses this Promise and dispatches its own callback overloads consistently.
    napi_ref callback = context->callbackRef;
    context->callbackRef = nullptr;
    return ContactsNapiUtils::StartContactSelection(env, context->context, context->uiExtensionContext, want, callback);
}

''' + api[b:]

payloads = {
    'contacts/src/contact.js': js.encode(),
    'contacts/src/contacts_api.cpp': api.encode(),
    'contacts/src/contacts_napi_utils.cpp': utils.encode(),
    'contacts/include/contacts_napi_utils.h': header.encode(),
    'contacts/include/contact_picker_protocol.h': (FIX / 'contact_picker_protocol.h').read_bytes(),
}
COMPONENT.mkdir(parents=True, exist_ok=True)
patch = []
rows = []
for relative, raw in payloads.items():
    before = original(relative) if relative in META['files'] else None
    path = PROJECT + '/' + relative
    rows.append((relative, hashlib.sha256(before).hexdigest() if before is not None else None,
                 hashlib.sha256(raw).hexdigest()))
    patch.append(f'diff --git a/{path} b/{path}\n')
    if before is None: patch.append('new file mode 100644\n')
    patch.extend(difflib.unified_diff((before or b'').decode().splitlines(keepends=True),
                                    raw.decode().splitlines(keepends=True),
                                    fromfile='a/' + path if before is not None else '/dev/null', tofile='b/' + path))
(COMPONENT / '0001-validate-and-complete-public-contact-selection.patch').write_text(''.join(patch))
(COMPONENT / 'verify_source.py').write_text('''#!/usr/bin/env python3
"""Require the exact sync_mode predecessor or complete picker protocol final state."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
''' + f'PROJECT = {PROJECT!r}\nREVISION = {META["revision"]!r}\nFILES = (\n' +
    ''.join('    ' + repr(row) + ',\n' for row in rows) + ''')

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
''')
(COMPONENT / 'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
(FIX / 'candidate-hashes.json').write_text(json.dumps({PROJECT + '/' + row[0]: row[2] for row in rows}, indent=2) + '\n')
print('generated 5 exact contact picker caller targets; sync_mode predecessor required')
