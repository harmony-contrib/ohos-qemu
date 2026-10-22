"""Normal supplemental producer inputs; no dependency on the final actor.

Root's ordinary source production writes external audio579-SOURCE-CONTEXT.json after selecting the
new complete Kit/normal SOURCE. This is separate from the unchanged SDK17 batch.
"""
from pathlib import Path
import hashlib
import importlib
import json
import sys

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
CANONICAL = ROOT / 'ci/capability-audit'
HERE = Path(__file__).resolve().parent
AUTHORING_BASE = '67765265103a932b9a562face76a882f07bed3e3'
OWN = ('audio579_common.py', 'audio579_project.py', 'audio579_native.py', 'audio579_runtime.py', 'audio579_inputs.py',
       'audio579_provider_runtime.py', 'audio579_midi.cpp', 'usb579_midi_session.inc', 'audio579/AudioAudit.ets', 'audio579/EntryAbility.ets', 'audio579/Index.ets')
SOURCE_CONTEXT = None
DEPENDENCIES = ('capability578_owned_io', 'avc_media_contract', 'batch_system_build_runtime_helpers',
    'hap_identity_binding', 'guest_ui', 'guest_process_identity', 'batch_media_audio_capture_challenge',
    'batch_media_recorder_challenge', 'headposture579_source', 'batch_system_live_mappings')


def need(ok, message):
    if not ok: raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate actual source metadata'); result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite source metadata')))


def ref(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
         not any(row.is_symlink() for row in (path, *path.parents)), 'actual single-path source/artifact')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return dict(path=str(path), sha256=digest.hexdigest())


def checked(value):
    need(type(value) is dict and set(value) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}), 'actual Ref2/3')
    path = Path(value['path'])
    need(ref(path) == {key: value[key] for key in ('path', 'sha256')} and
         ('bytes' not in value or path.stat().st_size == value['bytes']), 'actual source bytes changed')
    return path


def doc(value): return loads(checked(value).read_bytes())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
    return ref(path)


def source_guard(context_ref=None):
    global SOURCE_CONTEXT
    if context_ref is not None:
        path = checked(context_ref)
        need(path.is_relative_to(ROOT / '.tmp') and path.name == 'audio579-SOURCE-CONTEXT.json' and
             (SOURCE_CONTEXT is None or SOURCE_CONTEXT == context_ref), 'one fixed normal source DATA context, no executable selection')
        SOURCE_CONTEXT = dict(context_ref)
    need(SOURCE_CONTEXT is not None, 'Root normal source-production context must be explicitly bound before use')
    context = doc(SOURCE_CONTEXT)
    need(context['schema'] == 'audio579-normal-supplemental-source-context/v1' and
         isinstance(context['source_commit'], str) and len(context['source_commit']) == 40,
         'actual Root normal selected source context')
    normal, snapshot, kit = (doc(context[name]) for name in ('normal_source', 'snapshot', 'kit'))
    two = lambda row: {key: row[key] for key in ('path', 'sha256')}
    need(normal['source_commit'] == snapshot['source_commit'] == context['source_commit'] and
         two(normal['source_kit_manifest']) == context['kit'] and two(normal['canonical_snapshot']) == context['snapshot'],
         'one actual normal SOURCE/Kit/canonical snapshot')
    approved = {row['path']: row['sha256'] for row in context['files']}
    canonical = {row['path']: row['sha256'] for row in snapshot['files']}
    for name in OWN:
        path = HERE / name
        need(approved.get(str(path)) == ref(path)['sha256'], 'finite exact supplemental source must be admitted')
        if name.endswith('.py'):
            old = sys.modules.get(Path(name).stem)
            need(old is None or Path(old.__file__).resolve() == path, 'foreign cached supplemental producer module')
        if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / '.tmp'):
            need(canonical.get(str(path.relative_to(ROOT))) == approved[str(path)], 'new canonical producer belongs to actual package source')
    members = {row['path']: row for row in kit['members']}
    need(doc(context['runtime_sources']) and members['SOURCES377.json']['sha256'] == context['runtime_sources']['sha256'],
         'original complete source pool preserved')
    inherited = {row['path']: row['sha256'] for row in doc(context['runtime_sources'])['files']}
    for name in DEPENDENCIES:
        path = CANONICAL / (name + '.py')
        need(inherited.get(str(path)) == ref(path)['sha256'], 'original fixed producer dependency source')
        old = sys.modules.get(name)
        need(old is None or Path(old.__file__).resolve() == path, 'foreign cached producer dependency')
    return dict(SOURCE_CONTEXT)


def dependency(name):
    need(name in DEPENDENCIES, 'fixed normal supplemental dependency')
    source_guard()
    if str(CANONICAL) not in sys.path: sys.path.insert(0, str(CANONICAL))
    value = importlib.import_module(name)
    need(Path(value.__file__).resolve() == CANONICAL / (name + '.py'), 'original actual producer source origin')
    return value


COMMUNICATION_FUNCTIONS = {'foundation/multimedia/audio_framework/frameworks/js/napi/audiomanager/napi_audio_manager.cpp': 'napi_value NapiAudioManager::SetAudioScene(napi_env env, napi_callback_info info)\n{\n    auto context = std::make_shared<AudioManagerAsyncContext>();\n    if (context == nullptr) {\n        AUDIO_ERR_LOG("SetAudioScene failed : no memory");\n        NapiAudioError::ThrowError(env, "SetAudioScene failed : no memory", NAPI_ERR_NO_MEMORY);\n        return NapiParamUtils::GetUndefinedValue(env);\n    }\n\n    auto inputParser = [env, context](size_t argc, napi_value *argv) {\n        NAPI_CHECK_ARGS_RETURN_VOID(context, argc >= ARGS_ONE, "invalid arguments",\n            NAPI_ERR_INVALID_PARAM);\n        context->status = NapiParamUtils::GetValueInt32(env, context->scene, argv[PARAM0]);\n        NAPI_CHECK_ARGS_RETURN_VOID(context, context->status == napi_ok, "get scene failed",\n            NAPI_ERR_INVALID_PARAM);\n    };\n    context->GetCbInfo(env, info, inputParser);\n\n    auto executor = [context]() {\n        CHECK_AND_RETURN_LOG(CheckContextStatus(context), "context object state is error.");\n        auto obj = reinterpret_cast<NapiAudioManager*>(context->native);\n        ObjectRefMap objectGuard(obj);\n        auto *napiAudioManager = objectGuard.GetPtr();\n        CHECK_AND_RETURN_LOG(CheckAudioManagerStatus(napiAudioManager, context),\n            "audio manager state is error.");\n        context->intValue = napiAudioManager->audioMngr_->SetAudioScene(static_cast<AudioScene>(context->scene));\n        NAPI_CHECK_ARGS_RETURN_VOID(context, context->intValue == SUCCESS, "SetAudioScene failed",\n            NAPI_ERR_SYSTEM);\n    };\n\n    auto complete = [env](napi_value &output) {\n        output = NapiParamUtils::GetUndefinedValue(env);\n    };\n    return NapiAsyncWork::Enqueue(env, context, "SetAudioScene", executor, complete);\n}', 'foundation/multimedia/audio_framework/services/audio_policy/server/service/service_main/src/audio_policy_server.cpp': 'int32_t AudioPolicyServer::SetAudioScene(int32_t audioSceneIn)\n{\n    AudioScene audioScene = static_cast<AudioScene>(audioSceneIn);\n    CHECK_AND_RETURN_RET_LOG(audioScene > AUDIO_SCENE_INVALID && audioScene < AUDIO_SCENE_MAX,\n        ERR_INVALID_PARAM, "param is invalid");\n    bool ret = PermissionUtil::VerifySystemPermission();\n    CHECK_AND_RETURN_RET_LOG(ret, ERR_PERMISSION_DENIED, "No system permission");\n    switch (audioScene) {\n        case AUDIO_SCENE_DEFAULT:\n        case AUDIO_SCENE_RINGING:\n        case AUDIO_SCENE_PHONE_CALL:\n        case AUDIO_SCENE_PHONE_CHAT:\n            return eventEntry_->SetAudioScene(audioScene);\n\n        default:\n            AUDIO_ERR_LOG("param is invalid: %{public}d", audioScene);\n            return ERR_INVALID_PARAM;\n    }\n}\n// LCOV_EXCL_STOP', 'foundation/multimedia/audio_framework/services/audio_service/client/src/audio_system_manager.cpp': 'int32_t AudioSystemManager::SetAudioScene(const AudioScene &scene)\n{\n    return AudioSystemClientPolicyManager::GetInstance().SetAudioScene(scene);\n}', 'foundation/multimedia/audio_framework/services/audio_service/client/src/audio_system_client_policy_manager.cpp': 'int32_t AudioSystemClientPolicyManager::SetAudioScene(const AudioScene &scene)\n{\n    AUDIO_DEBUG_LOG("audioScene_=%{public}d done", scene);\n    return AudioPolicyManager::GetInstance().SetAudioScene(scene);\n}', 'foundation/multimedia/audio_framework/services/audio_policy/client/service/src/audio_policy_manager.cpp': 'int32_t AudioPolicyManager::SetAudioScene(AudioScene scene)\n{\n    const sptr<IAudioPolicy> gsp = GetAudioPolicyManagerProxy();\n    CHECK_AND_RETURN_RET_LOG(gsp != nullptr, -1, "audio policy manager proxy is NULL.");\n    return gsp->SetAudioScene(scene);\n}', 'foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_utils.cpp': 'bool PermissionUtil::VerifyIsSystemApp()\n{\n    uint64_t fullTokenId = IPCSkeleton::GetCallingFullTokenID();\n    WatchTimeout guard("Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID");\n    bool tmp = Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(fullTokenId);\n    CHECK_AND_RETURN_RET(!tmp, true);\n\n    return false;\n}\n\nbool PermissionUtil::VerifySelfPermission()\n{\n    Security::AccessToken::FullTokenID selfToken = IPCSkeleton::GetSelfTokenID();\n\n    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(static_cast<uint32_t>(selfToken));\n\n    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_NATIVE, true);\n\n    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_SHELL, true);\n\n    bool tmp = Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(selfToken);\n    CHECK_AND_RETURN_RET(!tmp, true);\n\n    AUDIO_ERR_LOG("Check self app permission reject");\n    return false;\n}\n\nbool PermissionUtil::VerifyBluetoothPermission()\n{\n    uid_t callingUid = static_cast<uid_t>(IPCSkeleton::GetCallingUid());\n    if (callingUid == UID_MEDIA || callingUid == BOOTUP_MUSIC_UID) {\n        // bootup use media kit\n        return false;\n    }\n#ifdef AUDIO_BUILD_VARIANT_ROOT\n    // root user case for auto test\n    if (callingUid == ROOT_UID) {\n        return true;\n    }\n#endif\n    uint32_t tokenId = IPCSkeleton::GetCallingTokenID();\n\n    int res = Security::AccessToken::AccessTokenKit::VerifyAccessToken(tokenId, "ohos.permission.USE_BLUETOOTH");\n    CHECK_AND_RETURN_RET(res == Security::AccessToken::PermissionState::PERMISSION_GRANTED, false);\n\n    return true;\n}\n\nbool PermissionUtil::VerifySystemPermission()\n{\n    auto tokenId = IPCSkeleton::GetCallingTokenID();\n    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(tokenId);\n\n    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_NATIVE, true);\n#ifdef AUDIO_BUILD_VARIANT_ROOT\n    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_SHELL, true);\n#endif\n    bool tmp = VerifyIsSystemApp();\n    CHECK_AND_RETURN_RET(!tmp, true);\n\n    return false;\n}', 'foundation/multimedia/audio_framework/frameworks/js/napi/common/napi_audio_error.h': 'constexpr int32_t NAPI_ERR_SYSTEM = 6800301;'}
PERMISSION_SOURCE_SHA256 = '64548d0ef53c475ff90d62627b75ceea16f392d74f00253d8baa1da925253c1d'

def communication_napi(inputs):
    """Exact selected-product source maps system-app rejection to JS6800301.

    Preserve 201/202 requirements for the other independent protected APIs.
    The source export must include these full actual selected source files.
    A foreign implementation requires review; any generic runtime6800301 does
    not by itself prove an authorization denial.
    """
    source_guard();export=doc(inputs['source_export']);commit=doc(source_guard())['source_commit']
    need(export['source_commit']==commit and export['archive_sha256']==inputs['archive']['sha256'] and
         export['resources_executed'] is True and export['cleanup_verified'] is True and export['failures']==[],
         'actual completed selected-product native source export')
    files={}
    for logical,function in COMMUNICATION_FUNCTIONS.items():
        actual=export['files'][logical];body=checked(actual).read_text()
        need(body.count(function)==1,'actual whole native function/code must match reviewed permission/mapping order')
        files[logical]=actual
    # The actual product graph must also show that the compiled permission
    # TU includes the reviewed real full-token checks, even with root macro set.
    # Preserve explicit native/shell/UID-root routes; only HAP bypasses change.
    # Reuse the same real complete product compdb/Ninja log already exported
    # for Graphics3D; never guess this from the device/profile label.
    import shlex
    product=doc(inputs['graphics3d']);need(product['source_export']==inputs['source_export'] and product['source_commit']==commit and
        product['archive_sha256']==inputs['archive']['sha256'],'same actual whole product compilation graph')
    database=doc(product['complete_compile_commands']);source_root=Path(product['source_root']);build=Path(product['build_directory'])
    permission_logical='foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_utils.cpp'
    entries=[row for row in database if (Path(row['directory'])/row['file']).resolve()==source_root/permission_logical]
    need(entries,'actual permission TU must exist in full original product compdb')
    compiled=[];ninja=checked(product['complete_ninja_log']).read_text().splitlines()
    for entry in entries:
        argv=entry.get('arguments') or shlex.split(entry['command'])
        need(Path(entry['directory'])==build and '-o' in argv and not any(a.startswith('@') for a in argv),'actual expanded product permission compile command')
        target=Path(argv[argv.index('-o')+1]);absolute=target if target.is_absolute() else build/target
        relative=str(absolute.relative_to(build));lines=[line for line in ninja if len(line.split('\t'))>=4 and line.split('\t')[3]==relative]
        if not lines:continue
        need(export['files'][permission_logical]['sha256']==PERMISSION_SOURCE_SHA256,'same actual compiled source includes both real full-token HAP checks')
        object_ref=export['files'][str(absolute.relative_to(source_root))];checked(object_ref)
        compiled.append(dict(command=argv,object=object_ref,object_logical=str(absolute),ninja_log=lines[-1]))
    need(compiled,'actual built permission TU/source/object and complete Ninja evidence required')
    return dict(actual_selected_sources=files,actual_permission_compilation=compiled,ordinary_system_app_denial=6800301,
        native_system_check_before_scene_write=True,other_permission_codes=[201,202],
        source_only_not_runtime_authorization_pass=True)
