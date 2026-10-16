// Host adapters execute the ACTUAL selection implementation extracted from
// contacts_napi_utils.cpp. They challenge ownership, not real UI scheduling.
#define main RunProtocolChallenges
#include "protocol_test.cpp"
#undef main
#include <deque>
#include <functional>
#include <map>
#include <memory>

#define HILOG_ERROR(...) do {} while (0)
constexpr int NAPI_AUTO_LENGTH = -1;
enum napi_status { napi_ok, napi_generic_failure };
struct Value { Json value; };
struct Env;
using napi_env = Env *;
using napi_value = Value *;
using napi_deferred = Env *;
using napi_ref = int *;
using napi_handle_scope = void *;
static std::thread::id jsThread = std::this_thread::get_id();
static std::mutex queueMutex;
static std::deque<std::function<void()>> queue;
static void Post(std::function<void()> task) { std::lock_guard<std::mutex> lock(queueMutex); queue.push_back(task); }
static void Drain()
{
    while (true) {
        std::function<void()> task;
        { std::lock_guard<std::mutex> lock(queueMutex); if (queue.empty()) { return; }
          task = queue.front(); queue.pop_front(); }
        task();
    }
}
struct Token { bool closed = false; bool pending = false; };
struct uv_loop_t {};
struct uv_handle_t { void *data = nullptr; std::shared_ptr<Token> token = std::make_shared<Token>(); };
struct uv_async_t : uv_handle_t { std::function<void(uv_async_t *)> callback; };
struct uv_timer_t : uv_handle_t { std::function<void(uv_timer_t *)> callback; };
static int initFailure = 0;
static int liveHandles = 0;
static int uv_async_init(uv_loop_t *, uv_async_t *h, void (*cb)(uv_async_t *))
{ if (initFailure == 1) { return -1; } h->callback = cb; ++liveHandles; return 0; }
static int uv_timer_init(uv_loop_t *, uv_timer_t *)
{ if (initFailure == 2) { return -1; } ++liveHandles; return 0; }
static void uv_unref(uv_handle_t *) {}
static int uv_async_send(uv_async_t *h)
{
    std::lock_guard<std::mutex> lock(queueMutex);
    assert(!h->token->closed);
    if (h->token->pending) { return 0; }
    h->token->pending = true;
    queue.push_back([h, token = h->token] {
        if (!token->closed) { token->pending = false; h->callback(h); }
    });
    return 0;
}
static int uv_timer_start(uv_timer_t *h, void (*cb)(uv_timer_t *), uint64_t, uint64_t)
{ h->callback = cb; return initFailure == 3 ? -1 : 0; }
static int uv_timer_stop(uv_timer_t *) { return 0; }
static void uv_close(uv_handle_t *h, void (*callback)(uv_handle_t *))
{ assert(!h->token->closed); h->token->closed = true; --liveHandles; Post([h, callback] { callback(h); }); }
struct Env {
    bool alive = true;
    bool noLoop = false;
    bool noHook = false;
    int settled = 0;
    int callbacks = 0;
    int deletedRefs = 0;
    int scopes = 0;
    Json result;
    std::vector<std::unique_ptr<Value>> values;
    std::vector<std::pair<void (*)(void *), void *>> cleanup;
    uv_loop_t loop;
};
static void Check(Env *env) { assert(env->alive && std::this_thread::get_id() == jsThread); }
static Value *Make(Env *env, Json value)
{ Check(env); env->values.push_back(std::make_unique<Value>(Value {value})); return env->values.back().get(); }
static napi_status napi_get_undefined(Env *e, Value **v) { *v = Make(e, nullptr); return napi_ok; }
static napi_status napi_create_promise(Env *e, Env **deferred, Value **v)
{ Check(e); *deferred = e; *v = Make(e, "promise"); return napi_ok; }
static napi_status napi_add_env_cleanup_hook(Env *e, void (*cb)(void *), void *data)
{ Check(e); if (e->noHook) { return napi_generic_failure; } e->cleanup.emplace_back(cb, data); return napi_ok; }
static napi_status napi_remove_env_cleanup_hook(Env *e, void (*cb)(void *), void *data)
{ Check(e); auto &v = e->cleanup; for (auto it = v.begin(); it != v.end(); ++it) {
  if (*it == std::make_pair(cb, data)) { v.erase(it); return napi_ok; } } return napi_generic_failure; }
static napi_status napi_get_uv_event_loop(Env *e, uv_loop_t **loop)
{ Check(e); *loop = e->noLoop ? nullptr : &e->loop; return napi_ok; }
static napi_status napi_open_handle_scope(Env *e, void **scope)
{ Check(e); ++e->scopes; *scope = e; return napi_ok; }
static napi_status napi_close_handle_scope(Env *e, void *) { Check(e); --e->scopes; return napi_ok; }
static napi_status napi_create_object(Env *e, Value **v) { *v = Make(e, Json::object()); return napi_ok; }
static napi_status napi_create_int32(Env *e, int v, Value **out) { *out = Make(e, v); return napi_ok; }
static napi_status napi_create_string_utf8(Env *e, const char *s, size_t n, Value **v)
{ *v = Make(e, std::string(s, n)); return napi_ok; }
static napi_status napi_set_named_property(Env *e, Value *v, const char *name, Value *property)
{ Check(e); v->value[name] = property->value; return napi_ok; }
static napi_status napi_resolve_deferred(Env *e, Env *, Value *value)
{ Check(e); assert(e->scopes == 1); ++e->settled; e->result = value->value; return napi_ok; }
static napi_status napi_get_reference_value(Env *e, int *, Value **v) { *v = Make(e, "function"); return napi_ok; }
static napi_status napi_delete_reference(Env *e, int *ref)
{ Check(e); ++e->deletedRefs; delete ref; return napi_ok; }
static napi_status napi_call_function(Env *e, Value *, Value *, size_t, Value *args[], Value **)
{ Check(e); assert(e->scopes == 1); ++e->callbacks; e->result = args[1]->value; return napi_ok; }
static napi_status napi_throw_error(Env *e, const char *, const char *) { Check(e); return napi_ok; }
static void Cleanup(Env &e)
{ auto hooks = e.cleanup; e.cleanup.clear(); for (auto [cb, data] : hooks) { cb(data); } e.alive = false; }

namespace OHOS {
namespace AAFwk {
struct Param { int kind; };
struct IInteger { static Param *Query(Param *p) { return p && p->kind == 0 ? p : nullptr; } };
struct IString { static Param *Query(Param *p) { return p && p->kind == 1 ? p : nullptr; } };
struct WantParams {
    int index = 0;
    int total = 1;
    std::string data = "[{}]";
    mutable Param integer {0};
    mutable Param string {1};
    bool valid = true;
    Param *GetParam(const std::string &key) const { return !valid ? nullptr : key == "pickerData" ? &string : &integer; }
    int GetIntParam(const std::string &key, int) const { return key == "index" ? index : total; }
    std::string GetStringParam(const std::string &) const { return data; }
};
struct Want { bool dismiss = false; bool GetBoolParam(const char *, bool) const { return dismiss; } };
}
namespace Ace {
struct ModalUIExtensionProxy {};
struct ModalUIExtensionConfig {
    bool isProhibitBack = false;
    bool prohibitedRemoveByRouter = false;
    bool prohibitedRemoveByNavigation = true;
};
struct ModalUIExtensionCallbacks {
    std::function<void(int32_t)> onRelease;
    std::function<void(int32_t, const AAFwk::Want &)> onResult;
    std::function<void(const AAFwk::WantParams &)> onReceive;
    std::function<void(int32_t, const std::string &, const std::string &)> onError;
    std::function<void(const std::shared_ptr<ModalUIExtensionProxy> &)> onRemoteReady;
    std::function<void()> onDestroy;
};
struct UIContent {
    int next = 10;
    int startup = 0;
    ModalUIExtensionConfig lastConfig;
    std::map<int, ModalUIExtensionCallbacks> windows;
    std::vector<int> closed;
    int CreateModalUIExtension(const AAFwk::Want &, const ModalUIExtensionCallbacks &cb, const ModalUIExtensionConfig &cfg)
    { lastConfig = cfg; if (startup == 1) { return 0; } windows[++next] = cb;
      if (startup == 2) { cb.onError(-1, "", ""); } return next; }
    void CloseModalUIExtension(int id) { closed.push_back(id); }
};
}
namespace AbilityRuntime {
struct AbilityContext { Ace::UIContent *content; Ace::UIContent *GetUIContent() { return content; } };
struct UIExtensionContext { Ace::UIContent *content; Ace::UIContent *GetUIContent() { return content; } };
}
namespace ContactsApi {
class ContactsNapiUtils {
public:
    static napi_value StartContactSelection(napi_env, const std::shared_ptr<AbilityRuntime::AbilityContext> &,
        const std::shared_ptr<AbilityRuntime::UIExtensionContext> &, const AAFwk::Want &, napi_ref);
};
// Generated by the Python runner from contacts_napi_utils.cpp, not a rewrite.
#include "actual_selection_impl.inc"
}
}

using OHOS::ContactsApi::ContactsNapiUtils;
struct Fixture {
    Env env;
    OHOS::Ace::UIContent content;
    std::shared_ptr<OHOS::AbilityRuntime::AbilityContext> host =
        std::make_shared<OHOS::AbilityRuntime::AbilityContext>();
    Fixture() { host->content = &content; }
    void Start(bool dismiss = false, bool callback = false)
    { ContactsNapiUtils::StartContactSelection(&env, host, nullptr, {dismiss}, callback ? new int(1) : nullptr); }
    auto &Callbacks() { return content.windows.rbegin()->second; }
    void Complete(int code = 0) { Callbacks().onResult(code, {}); }
    void Frame(int index = 0, int total = 1, std::string data = "[{}]")
    { OHOS::AAFwk::WantParams p; p.index = index; p.total = total; p.data = data; Callbacks().onReceive(p); }
    ~Fixture() { if (env.alive) { Cleanup(env); } content.windows.clear(); Drain(); assert(liveHandles == 0); }
};

int main()
{
    RunProtocolChallenges();
    int cases = 0;
    {
        Fixture f; f.Start(); f.Frame(); f.Complete(); f.Callbacks().onRelease(0); Drain();
        assert(f.env.settled == 1 && f.env.result["total"] == 1);
        f.Complete(401); f.Callbacks().onDestroy(); Drain();
        assert(f.env.settled == 1 && f.content.closed == std::vector<int> {11});
        ++cases;
    }
    {
        Fixture f; f.Start(true, true); f.Frame(); f.Complete(); Drain();
        assert(f.env.callbacks == 1 && f.env.deletedRefs == 1 && f.env.settled == 0);
        assert(!f.content.lastConfig.prohibitedRemoveByRouter && !f.content.lastConfig.prohibitedRemoveByNavigation);
        ++cases;
    }
    {
        Fixture f; f.Start(); assert(f.content.lastConfig.prohibitedRemoveByRouter);
        f.Callbacks().onError(16000050, "error", "failed"); Drain();
        assert(f.env.settled == 1 && f.env.result["resultCode"] == 16700001); ++cases;
    }
    for (int failure : {1, 2, 3}) {
        Fixture f; initFailure = failure; f.Start(); initFailure = 0; Drain();
        assert(f.env.settled == 1 && f.env.result["resultCode"] == 16700001); ++cases;
    }
    for (int startup : {1, 2}) {
        Fixture f; f.content.startup = startup; f.Start(); Drain();
        assert(f.env.settled == 1 && f.env.result["resultCode"] == 16700001); ++cases;
    }
    for (int failure : {0, 1, 2}) {
        Fixture f; f.env.noLoop = failure == 0; f.env.noHook = failure == 1;
        if (failure == 2) { f.host->content = nullptr; }
        f.Start(); Drain(); assert(f.env.settled == 1); ++cases;
    }
    {
        Fixture f; f.Start(); f.Frame(); f.Complete(); Cleanup(f.env); Drain();
        assert(f.env.settled == 0 && liveHandles == 0); ++cases;
    }
    {
        Fixture f; f.Start(); auto callbacks = f.Callbacks();
        callbacks.onDestroy(); f.host->content = nullptr; Drain();
        assert(f.env.settled == 1 && f.env.result["resultCode"] == 16700001 && f.content.closed.empty());
        callbacks.onReceive({}); callbacks.onResult(0, {}); Drain(); assert(f.env.settled == 1); ++cases;
    }
    {
        Fixture f; f.Start(); f.Frame(); f.Complete(); f.host->content = nullptr; f.Callbacks().onDestroy(); Drain();
        assert(f.env.settled == 1 && f.content.closed.empty()); ++cases;
    }
    {
        Fixture f; f.Start(); auto first = f.Callbacks(); f.Start();
        f.Frame(0, 2, "[{},{}]"); f.Complete(); first.onError(-1, "", ""); Drain();
        assert(f.env.settled == 2 && f.content.closed.size() == 2);
        assert(f.content.closed[0] == 12 && f.content.closed[1] == 11); ++cases;
    }
    {
        Fixture f; f.Start();
        auto state = static_cast<std::weak_ptr<OHOS::ContactsApi::SelectionRequest> *>(f.env.cleanup[0].second)->lock();
        state->deadline->callback(state->deadline); Drain();
        assert(f.env.settled == 1 && f.env.result["resultCode"] == 16700001); ++cases;
    }
    {
        Fixture f; f.Start(); auto cb = f.Callbacks();
        std::thread ui([cb] { cb.onReceive({}); cb.onResult(0, {}); cb.onRelease(0); });
        ui.join(); Drain(); assert(f.env.settled == 1 && f.env.result["total"] == 1); ++cases;
    }
    std::cout << cases << " actual native lifecycle adapter scenarios passed\n";
}
