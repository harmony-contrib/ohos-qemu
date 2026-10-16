#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>
using std::string;
struct Value {int number=0;std::string text;int code=0;};
struct Promise {int settles=0;bool rejected=false;int number=0;int code=0;};
struct Env {std::vector<std::unique_ptr<Value>> values;std::vector<std::unique_ptr<Promise>> promises;bool failPromise=false;};
using napi_env=Env*;using napi_value=Value*;using napi_deferred=Promise*;using napi_status=int;
constexpr int napi_ok=0, NAPI_AUTO_LENGTH=-1, NO_ERROR=0, INTERNAL_ERROR=23900004, INVALID_EVENT_ID=-1;
struct ContextBase {int status=napi_ok;struct {std::string message;int code=NO_ERROR;} error;};
napi_value value(Env* e){e->values.emplace_back(std::make_unique<Value>());return e->values.back().get();}
int napi_create_promise(Env* e,Promise** p,Value** v){if(e->failPromise)return 1;e->promises.emplace_back(std::make_unique<Promise>());*p=e->promises.back().get();*v=value(e);return 0;}
int napi_create_int32(Env* e,int n,Value** v){*v=value(e);(*v)->number=n;return 0;}
int napi_create_string_utf8(Env* e,const char* s,int,Value** v){*v=value(e);(*v)->text=s;return 0;}
int napi_create_error(Env* e,Value*,Value* s,Value** v){*v=value(e);(*v)->text=s->text;return 0;}
int napi_set_named_property(Env*,Value* v,const char*,Value* code){v->code=code->number;return 0;}
int napi_resolve_deferred(Env*,Promise* p,Value* v){p->settles++;p->number=v->number;return 0;}
int napi_reject_deferred(Env*,Promise* p,Value* v){p->settles++;p->rejected=true;p->code=v->code;return 0;}
int napi_throw_error(Env*,const char*,const char*){return 0;}
namespace AAFwk {struct WantParams{};struct Want{std::map<std::string,int> ints;void SetElementName(const std::string&,const std::string&){};void SetParam(const std::string&,const std::string&){};int GetIntParam(const std::string& k,int d)const{auto i=ints.find(k);return i==ints.end()?d:i->second;}};}
namespace Ace {
struct ModalUIExtensionProxy{};
struct ModalUIExtensionCallbacks {std::function<void(int)> onRelease;std::function<void(int,const AAFwk::Want&)> onResult;std::function<void(const AAFwk::WantParams&)> onReceive;std::function<void(int,const std::string&,const std::string&)> onError;std::function<void(const std::shared_ptr<ModalUIExtensionProxy>&)> onRemoteReady;std::function<void()> onDestroy;};
struct ModalUIExtensionConfig{bool isProhibitBack=false;};
struct UIContent{ModalUIExtensionCallbacks cb;int session=7,closes=0;std::function<void()> duringCreate;bool destroyOnClose=true;int CreateModalUIExtension(const AAFwk::Want&,const ModalUIExtensionCallbacks& callbacks,const ModalUIExtensionConfig&){cb=callbacks;if(duringCreate)duringCreate();return session;}void CloseModalUIExtension(int id){assert(id>0);closes++;if(destroyOnClose)cb.onDestroy();}};
}
class CalendarManagerNapi {public:
// INSERT_CONTEXT
static void FinishEditor(napi_env,std::shared_ptr<EditEventContext>,napi_deferred,bool,int32_t,const std::string&,bool);
static napi_value LaunchEditorPage(napi_env,std::shared_ptr<EditEventContext>);
};
// INSERT_FUNCTIONS
int main(){
 for(const std::string scenario: {"success","cancel","error","destroy","no_session","null_ui","invalid_context","zero_id","provider_error","sync_result","sync_error","sync_destroy","promise_failure"}){
  Env env;Ace::UIContent ui;auto ctx=std::make_shared<CalendarManagerNapi::EditEventContext>();ctx->_uiContent=&ui;
  if(scenario=="no_session")ui.session=0;
  if(scenario=="null_ui")ctx->_uiContent=nullptr;
  if(scenario=="invalid_context")ctx->error={"bad",401};
  if(scenario=="sync_result")ui.duringCreate=[&]{AAFwk::Want result;result.ints["eventId"]=64;ui.cb.onResult(0,result);};
  if(scenario=="sync_error")ui.duringCreate=[&]{ui.cb.onError(901,"","no UI");};
  if(scenario=="sync_destroy")ui.duringCreate=[&]{ui.cb.onDestroy();};
  if(scenario=="promise_failure")env.failPromise=true;
  auto promise=CalendarManagerNapi::LaunchEditorPage(&env,ctx);
  if(scenario=="promise_failure"){assert(promise==nullptr);continue;}
  assert(promise!=nullptr);auto p=env.promises.back().get();
  if(scenario=="success"){AAFwk::Want result;result.ints["eventId"]=73;ui.cb.onResult(0,result);assert(p->number==73&&!p->rejected);assert(ui.closes==1);}
  if(scenario=="cancel"){ui.cb.onRelease(0);assert(p->number==-1&&!p->rejected);assert(ui.closes==1);}
  if(scenario=="error"){ui.cb.onError(201,"","permission denied");assert(p->rejected&&p->code==201);assert(ui.closes==1);}
  if(scenario=="destroy"){ui.cb.onDestroy();assert(p->number==-1&&!p->rejected);assert(ui.closes==0);}
  if(scenario=="zero_id"){AAFwk::Want result;result.ints["eventId"]=0;ui.cb.onResult(0,result);assert(p->rejected);}
  if(scenario=="provider_error"){AAFwk::Want result;result.ints["errorCode"]=401;ui.cb.onResult(401,result);assert(p->rejected&&p->code==401);}
  if(scenario=="null_ui"||scenario=="no_session"||scenario=="invalid_context")assert(p->rejected);
  if(scenario=="sync_result"){assert(p->number==64&&!p->rejected);assert(ui.closes==1);}
  if(scenario=="sync_error"){assert(p->rejected&&p->code==901);assert(ui.closes==1);}
  if(scenario=="sync_destroy"){assert(p->number==-1&&!p->rejected);assert(ui.closes==0);}
  assert(p->settles==1);
  if(ui.cb.onDestroy){ui.cb.onDestroy();ui.cb.onRelease(0);ui.cb.onError(1,"","duplicate");AAFwk::Want late;late.ints["eventId"]=100;ui.cb.onResult(0,late);assert(p->settles==1);}
 }
}
