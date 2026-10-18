// Link the COMPLETE actual player NAPI CPP + its actual private header, complete
// common CPP and complete callback CPP. Only external native/NAPI APIs are controlled.
#include "prelude.h"
#include "audio_haptic_player_napi.h"
#include "audio_haptic_player_impl.h"
using namespace OHOS;
using namespace OHOS::Media;
static_assert(std::is_same<decltype(AudioHapticPlayerAsyncContext::status),int32_t>::value,
    "actual private async member must retain signed native error code, never bool");

static int32_t PublicCode(int32_t native)
{
    if (native==MSERR_OPEN_FILE_FAILED) return NAPI_ERR_IO_ERROR;
    if (native==MSERR_SERVICE_DIED) return NAPI_ERR_SERVICE_DIED;
    if (native==MSERR_UNSUPPORT_FILE) return NAPI_ERR_UNSUPPORTED_FORMAT;
    return NAPI_ERR_OPERATE_NOT_ALLOWED;
}

int main()
{
    QaNapiEnv state;
    auto env=&state;
    AudioHapticPlayerAsyncContext initialized{};
    assert(initialized.status==MSERR_OK);
    napi_value exports=nullptr;
    napi_create_object(env,&exports);
    assert(AudioHapticPlayerNapi::Init(env,exports)==exports);
    auto native=std::make_shared<AudioHapticPlayerImpl>();
    std::shared_ptr<AudioHapticPlayer> publicNative=native;
    auto player=AudioHapticPlayerNapi::CreatePlayerInstance(env,publicNative);
    assert(player && player->native);
    const int32_t results[]={MSERR_OK,MSERR_OPEN_FILE_FAILED,MSERR_SERVICE_DIED,
        MSERR_UNSUPPORT_FILE,MSERR_INVALID_OPERATION,-123456789,
        std::numeric_limits<int32_t>::min(),std::numeric_limits<int32_t>::max(),1};
    for (const auto &name : {"start","stop","release"}) {
        for (int32_t result:results) {
            native->startResult=result; native->stopResult=result; native->releaseResult=result;
            state.rejected=nullptr; state.resolved=nullptr; state.thrown=nullptr;
            state.rejectedCount=0; state.resolvedCount=0;
            state.thisValue=player; state.arguments.clear();
            bool actualWorkerObserved=false;
            state.beforeComplete=[&](void *data) {
                // Reads the REAL production private context after the REAL worker,
                // before the REAL completion destroys it. A bool regression fails
                // at compile-time and at this assertion, not just public-code output.
                auto context=static_cast<AudioHapticPlayerAsyncContext *>(data);
                assert(context->status==result);
                actualWorkerObserved=true;
            };
            auto promise=player->methods.at(name)(env,nullptr);
            assert(promise && state.pending.size()==1 && !actualWorkerObserved);
            const int deletedBefore=state.deletedWork;
            state.Drain();
            assert(actualWorkerObserved && state.deletedWork==deletedBefore+1);
            if (result==MSERR_OK) {
                assert(state.resolvedCount==1 && state.rejectedCount==0 && state.resolved);
                assert(!state.rejected);
            } else {
                assert(state.rejectedCount==1 && state.resolvedCount==0 && state.rejected);
                auto code=state.rejected->properties.at("code");
                assert(code->numeric && code->number==PublicCode(result));
                assert(!state.rejected->properties.at("message")->text.empty());
            }
        }
    }
    assert(native->starts==9 && native->stops==9 && native->releases==9);
    assert(state.createdWork==27 && state.queuedWork==27 && state.deletedWork==27);
    state.beforeComplete=nullptr;
    // Existing public201 path: actual permission query + actual numeric reject.
    // The unchanged manager CreatePlayer-before-queue ordering is also checked
    // by the Python source regression; this is not a complete manager CPP test.
    using OHOS::Security::AccessToken::AccessTokenKit;
    IPCSkeleton::token=1; AccessTokenKit::result=-1;
    assert(!AudioHapticCommonNapi::VerifyVibratePermission());
    state.rejected=nullptr;
    const int queuesBefore=state.queuedWork;
    AudioHapticCommonNapi::PromiseReject(env,env,NAPI_ERR_VIBRATE_PERMISSION_DENIED);
    assert(state.rejected->properties.at("code")->numeric);
    assert(state.rejected->properties.at("code")->number==201);
    assert(state.queuedWork==queuesBefore);
    AccessTokenKit::result=0;
    assert(AudioHapticCommonNapi::VerifyVibratePermission());
    IPCSkeleton::token=0;
    assert(!AudioHapticCommonNapi::VerifyVibratePermission());
    // Release the real allocated NAPI wrapper via its actual public destructor.
    // The external fake JS engine does not run the production finalizer.
    delete static_cast<AudioHapticPlayerNapi *>(player->native);
    player->native=nullptr;
}
