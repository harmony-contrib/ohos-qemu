#include <cassert>
#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
using std::string;
struct Value {int number=0;std::string text;int code=0;};
struct Promise {int settles=0;bool rejected=false;int number=0;int code=0;};
struct Env {
 std::thread::id thread=std::this_thread::get_id();
 std::vector<std::unique_ptr<Value>> values;
 std::vector<std::unique_ptr<Promise>> promises;
 std::vector<std::function<void()>> events;
 std::map<void*,void(*)(void*)> hooks;
 bool failPromise=false,failHook=false,failSend=false,failScope=false,alive=true;
 int scopes=0,opened=0,closed=0,sends=0;
};
using napi_env=Env*;using napi_value=Value*;using napi_deferred=Promise*;using napi_status=int;using napi_handle_scope=void*;
constexpr int napi_ok=0,napi_closing=16,napi_eprio_high=1,NAPI_AUTO_LENGTH=-1,NO_ERROR=0,INTERNAL_ERROR=23900004,INVALID_EVENT_ID=-1;
#define LOG_ERROR(...) ((void)0)
struct ContextBase {int status=napi_ok;struct {std::string message;int code=NO_ERROR;} error;};
void js(Env* e){assert(e->alive);assert(e->thread==std::this_thread::get_id());}
napi_value value(Env* e){js(e);e->values.emplace_back(std::make_unique<Value>());return e->values.back().get();}
int napi_create_promise(Env* e,Promise** p,Value** v){js(e);if(e->failPromise)return 1;e->promises.emplace_back(std::make_unique<Promise>());*p=e->promises.back().get();*v=value(e);return 0;}
int napi_create_int32(Env* e,int n,Value** v){assert(e->scopes>0);*v=value(e);(*v)->number=n;return 0;}
int napi_create_string_utf8(Env* e,const char* s,int,Value** v){assert(e->scopes>0);*v=value(e);(*v)->text=s;return 0;}
int napi_create_error(Env* e,Value*,Value* s,Value** v){assert(e->scopes>0);*v=value(e);(*v)->text=s->text;return 0;}
int napi_set_named_property(Env* e,Value* v,const char*,Value* code){js(e);assert(e->scopes>0);v->code=code->number;return 0;}
int napi_resolve_deferred(Env* e,Promise* p,Value* v){js(e);assert(e->scopes>0);assert(p);p->settles++;p->number=v->number;return 0;}
int napi_reject_deferred(Env* e,Promise* p,Value* v){js(e);assert(e->scopes>0);assert(p);p->settles++;p->rejected=true;p->code=v->code;return 0;}
int napi_throw_error(Env* e,const char*,const char*){js(e);return 0;}
int napi_open_handle_scope(Env* e,void** scope){js(e);if(e->failScope)return 1;e->scopes++;e->opened++;*scope=e;return 0;}
int napi_close_handle_scope(Env* e,void*){js(e);assert(e->scopes>0);e->scopes--;e->closed++;return 0;}
int napi_add_env_cleanup_hook(Env* e,void(*hook)(void*),void* arg){js(e);if(e->failHook)return 1;e->hooks[arg]=hook;return 0;}
int napi_remove_env_cleanup_hook(Env* e,void(*hook)(void*),void* arg){js(e);assert(e->hooks.at(arg)==hook);e->hooks.erase(arg);return 0;}
int napi_send_event(Env* e,std::function<void()> fn,int){assert(e->alive);e->sends++;if(e->failSend)return 1;e->events.push_back(std::move(fn));return 0;}
void drain(Env& e){while(!e.events.empty()){auto events=std::move(e.events);e.events.clear();for(auto& f:events)f();}}
void cleanup(Env& e){js(&e);auto hooks=std::move(e.hooks);e.hooks.clear();for(auto [arg,fn]:hooks)fn(arg);e.alive=false;}
void uiCall(std::function<void()> fn){std::thread t(std::move(fn));t.join();}
namespace AAFwk {struct WantParams{};struct Want{std::map<std::string,int> ints;void SetElementName(const std::string&,const std::string&){};void SetParam(const std::string&,const std::string&){};int GetIntParam(const std::string& k,int d)const{auto i=ints.find(k);return i==ints.end()?d:i->second;}};}
namespace Ace {
struct ModalUIExtensionProxy{};
struct ModalUIExtensionCallbacks {std::function<void(int)> onRelease;std::function<void(int,const AAFwk::Want&)> onResult;std::function<void(const AAFwk::WantParams&)> onReceive;std::function<void(int,const std::string&,const std::string&)> onError;std::function<void(const std::shared_ptr<ModalUIExtensionProxy>&)> onRemoteReady;std::function<void()> onDestroy;};
struct ModalUIExtensionConfig{bool isProhibitBack=false;};
struct UIContent {
 ModalUIExtensionCallbacks cb;int session=7,closes=0;bool destroyed=false;std::function<void()> duringCreate;
 int CreateModalUIExtension(const AAFwk::Want&,const ModalUIExtensionCallbacks& callbacks,const ModalUIExtensionConfig&){cb=callbacks;if(duringCreate)duringCreate();return session;}
 void CloseModalUIExtension(int id){assert(!destroyed);assert(id==session);closes++;}
};
}
namespace AbilityRuntime {struct AbilityContext{Ace::UIContent* content=nullptr;Ace::UIContent* GetUIContent(){return content;}};}
class CalendarManagerNapi {public:
// INSERT_CONTEXT
static void CleanupEditorEnvironment(void*);
static void CloseEditorSession(const std::shared_ptr<EditEventContext>&);
static void QueueEditorResult(const std::shared_ptr<EditEventContext>&,bool,int32_t,const std::string&,int32_t,bool);
static void FinishEditor(const std::shared_ptr<EditEventContext>&,uint64_t,bool,int32_t,const std::string&,int32_t,bool);
static napi_value LaunchEditorPage(napi_env,std::shared_ptr<EditEventContext>);
};
// INSERT_FUNCTIONS
int main(){
 for(const std::string scenario: {"success","cancel","error","destroy","no_session","null_ui","invalid_context","zero_id","provider_error","sync_result","sync_error","sync_destroy","promise_failure","hook_failure","queued_destroy","cleanup_queued","send_failure","host_replaced","host_expired","scope_failure","two_sessions","sync_send_failure","concurrent_cleanup"}){
  Env env;Ace::UIContent ui;auto host=std::make_shared<AbilityRuntime::AbilityContext>();host->content=&ui;
  auto ctx=std::make_shared<CalendarManagerNapi::EditEventContext>();ctx->_uiContent=&ui;ctx->hostContext=host;
  if(scenario=="no_session")ui.session=0;
  if(scenario=="null_ui")ctx->_uiContent=nullptr;
  if(scenario=="invalid_context")ctx->error={"bad",401};
  if(scenario=="sync_result")ui.duringCreate=[&]{uiCall([&]{AAFwk::Want result;result.ints["eventId"]=64;ui.cb.onResult(0,result);});};
  if(scenario=="sync_error")ui.duringCreate=[&]{uiCall([&]{ui.cb.onError(901,"","no UI");});};
  if(scenario=="sync_send_failure"){env.failSend=true;ui.duringCreate=[&]{uiCall([&]{ui.cb.onRelease(0);});};}
  if(scenario=="sync_destroy")ui.duringCreate=[&]{uiCall([&]{ui.cb.onDestroy();ui.destroyed=true;host->content=nullptr;});};
  if(scenario=="promise_failure")env.failPromise=true;
  if(scenario=="hook_failure")env.failHook=true;
  auto promise=CalendarManagerNapi::LaunchEditorPage(&env,ctx);
  if(scenario=="promise_failure"){assert(promise==nullptr);continue;}
  assert(promise);auto p=env.promises.back().get();
  if(scenario=="send_failure")env.failSend=true;
  if(scenario=="scope_failure")env.failScope=true;
  if(scenario=="host_replaced")host->content=nullptr;
  if(scenario=="host_expired")host.reset();
  if(scenario=="two_sessions"){
   Ace::UIContent other;other.session=8;auto otherHost=std::make_shared<AbilityRuntime::AbilityContext>();otherHost->content=&other;
   auto ctx2=std::make_shared<CalendarManagerNapi::EditEventContext>();ctx2->_uiContent=&other;ctx2->hostContext=otherHost;
   CalendarManagerNapi::LaunchEditorPage(&env,ctx2);auto p2=env.promises.back().get();
   uiCall([&]{ui.cb.onRelease(0);});drain(env);assert(ui.closes==1&&other.closes==0&&p2->settles==0);
   uiCall([&]{AAFwk::Want result;result.ints["eventId"]=81;other.cb.onResult(0,result);});drain(env);assert(other.closes==1&&p2->number==81);
   other.cb={};ctx2.reset();
  }
  if(scenario=="success"||scenario=="zero_id"||scenario=="provider_error"||scenario=="queued_destroy"||scenario=="cleanup_queued"||scenario=="host_replaced"||scenario=="host_expired"||scenario=="scope_failure"||scenario=="send_failure"){
   uiCall([&]{AAFwk::Want result;result.ints["eventId"]=scenario=="zero_id"?0:73;result.ints["errorCode"]=401;ui.cb.onResult(scenario=="provider_error"?401:0,result);});
   assert(p->settles==0);
  }
  if(scenario=="cancel")uiCall([&]{ui.cb.onRelease(0);});
  if(scenario=="error")uiCall([&]{ui.cb.onError(201,"","permission denied");});
  if(scenario=="destroy"||scenario=="queued_destroy")uiCall([&]{ui.cb.onDestroy();ui.destroyed=true;host->content=nullptr;});
  if(scenario=="cleanup_queued")cleanup(env);
  if(scenario=="concurrent_cleanup"){
   std::atomic<bool> start=false;
   std::thread producer([&]{start=true;AAFwk::Want result;result.ints["eventId"]=73;ui.cb.onResult(0,result);});
   while(!start.load())std::this_thread::yield();
   cleanup(env);producer.join();
  }
  drain(env);
  if(scenario=="cleanup_queued"||scenario=="concurrent_cleanup"||scenario=="send_failure"||scenario=="sync_send_failure"||scenario=="scope_failure")assert(p->settles==0);
  else assert(p->settles==1);
  if(scenario=="success")assert(p->number==73&&!p->rejected&&ui.closes==1);
  if(scenario=="cancel")assert(p->number==-1&&!p->rejected&&ui.closes==1);
  if(scenario=="error")assert(p->rejected&&p->code==201&&ui.closes==1);
  if(scenario=="destroy"||scenario=="queued_destroy"||scenario=="sync_destroy")assert(p->number==-1&&!p->rejected&&ui.closes==0);
  if(scenario=="zero_id"||scenario=="provider_error"||scenario=="null_ui"||scenario=="no_session"||scenario=="invalid_context"||scenario=="hook_failure")assert(p->rejected);
  if(scenario=="sync_result")assert(p->number==64&&!p->rejected&&ui.closes==1);
  if(scenario=="sync_error")assert(p->rejected&&p->code==901&&ui.closes==1);
  if(scenario=="host_replaced"||scenario=="host_expired")assert(ui.closes==0);
  if(scenario=="send_failure"||scenario=="sync_send_failure")assert(ui.closes==1);
  if(ui.cb.onDestroy){uiCall([&]{ui.cb.onDestroy();ui.cb.onRelease(0);ui.cb.onError(1,"","duplicate");AAFwk::Want late;late.ints["eventId"]=100;ui.cb.onResult(0,late);});drain(env);}
  assert(env.scopes==0&&env.opened==env.closed);
  std::weak_ptr<CalendarManagerNapi::EditEventContext> weak=ctx;ui.cb={};ctx.reset();assert(weak.expired());
  if(env.alive)cleanup(env);assert(env.hooks.empty());
 }
}
