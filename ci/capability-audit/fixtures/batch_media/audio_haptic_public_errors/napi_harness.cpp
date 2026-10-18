// Full production callback class/CPP and actual common class/methods; only external API transport is controlled.
#include "host_prelude.h"
#include "audio_haptic_player_callback_napi.h"
using namespace OHOS;
using namespace OHOS::Media;
int main()
{
    QaNapiEnv state;
    auto env = &state;
    AudioHapticCommonNapi::PromiseReject(env, nullptr, 5400102);
    assert(state.rejected && state.rejected->properties.at("code")->numeric);
    assert(state.rejected->properties.at("code")->number == 5400102);
    assert(!state.rejected->properties.at("message")->text.empty());
    AudioHapticCommonNapi::PromiseReject(env, nullptr, 201);
    assert(state.rejected->properties.at("code")->number == 201);
    using OHOS::Security::AccessToken::AccessTokenKit;
    IPCSkeleton::token = 1; AccessTokenKit::result = 0;
    assert(AudioHapticCommonNapi::VerifyVibratePermission());
    AccessTokenKit::result = -1; assert(!AudioHapticCommonNapi::VerifyVibratePermission());
    int queries = AccessTokenKit::queries;
    IPCSkeleton::token = 0; assert(!AudioHapticCommonNapi::VerifyVibratePermission());
    assert(AccessTokenKit::queries == queries);
    int eos = 0, interrupts = 0;
    auto eosFunction = state.Make(); eosFunction->function = [&] { ++eos; };
    auto interruptFunction = state.Make(); interruptFunction->function = [&] { ++interrupts; };
    auto callback = std::make_shared<AudioHapticPlayerCallbackNapi>(env);
    callback->SaveCallbackReference("endOfStream", eosFunction);
    callback->SaveCallbackReference("audioInterrupt", interruptFunction);
    // These isolated NAPI boundary cases use a controlled producer token. Real backend
    // provenance/admission is separately exercised by the complete native class harness.
    for (auto retired : {AudioHapticSessionEnd::STOPPED, AudioHapticSessionEnd::RELEASED,
                         AudioHapticSessionEnd::REPLACED, AudioHapticSessionEnd::START_FAILED}) {
        auto session = std::make_shared<AudioHapticPlaybackSession>(std::shared_ptr<Player>());
        session->playConfirmed = true; session->end = AudioHapticSessionEnd::ENDED;
        callback->OnSessionEndOfStream(session, false);
        session->end = retired; state.Drain(); assert(eos == 0);
        session->end = AudioHapticSessionEnd::INTERRUPTED;
        callback->OnSessionInterrupt(session, AudioStandard::InterruptEvent{});
        session->end = retired; state.Drain(); assert(interrupts == 0);
    }
    auto session = std::make_shared<AudioHapticPlaybackSession>(std::shared_ptr<Player>());
    session->playConfirmed = true; session->end = AudioHapticSessionEnd::LIVE;
    callback->OnSessionEndOfStream(session, true); state.Drain(); assert(eos == 1);
    session->end = AudioHapticSessionEnd::ENDED;
    callback->OnSessionEndOfStream(session, false); state.Drain(); assert(eos == 2);
    session->end = AudioHapticSessionEnd::INTERRUPTED;
    callback->OnSessionInterrupt(session, AudioStandard::InterruptEvent{}); state.Drain(); assert(interrupts == 1);
    // Fast/legacy path deliberately unchanged: it carries no normal-session claim.
    callback->OnEndOfStream(); callback->OnInterrupt(AudioStandard::InterruptEvent{}); state.Drain();
    assert(eos == 3 && interrupts == 2);
    // User callback may reenter reference/lifecycle-related methods: no native queue lock is held.
    eosFunction->function = [&] { ++eos; callback->RemoveCallbackReference("endOfStream"); };
    callback->OnEndOfStream(); state.Drain(); assert(eos == 4);
}
