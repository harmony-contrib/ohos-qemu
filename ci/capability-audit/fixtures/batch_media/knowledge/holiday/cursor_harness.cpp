#include "knowledge_content_query.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <vector>
using napi_async_work=void*;using napi_deferred=void*;using napi_env=void*;
enum napi_valuetype {napi_undefined,napi_null,napi_boolean,napi_number,napi_string,napi_object};
enum napi_status {napi_ok,napi_invalid_arg};
struct Value {napi_valuetype type=napi_number;double number=0;bool array=false;std::vector<Value*>items;};using napi_value=Value*;
static napi_status napi_typeof(napi_env,napi_value value,napi_valuetype *type){if(!value)return napi_invalid_arg;*type=value->type;return napi_ok;}
static napi_status napi_get_value_double(napi_env,napi_value value,double *number){if(!value||value->type!=napi_number)return napi_invalid_arg;*number=value->number;return napi_ok;}
static napi_status napi_is_array(napi_env,napi_value value,bool *array){if(!value)return napi_invalid_arg;*array=value->array;return napi_ok;}
static napi_status napi_get_array_length(napi_env,napi_value value,uint32_t *length){if(!value||!value->array)return napi_invalid_arg;*length=static_cast<uint32_t>(value->items.size());return napi_ok;}
static napi_status napi_get_element(napi_env,napi_value value,uint32_t i,napi_value *element){if(!value||i>=value->items.size())return napi_invalid_arg;*element=value->items[i];return napi_ok;}
static int permissionError=0;
namespace OHOS::NativeRdb {
constexpr int E_OK=0,E_ERROR=-1,E_ROW_OUT_RANGE=1;
struct Row {int field;std::string id,name,alias;int64_t votes;};
struct ResultSet {std::vector<Row> rows;int position=-1;int failAt=-1;int revokeAt=-1;int steps=0;
 int GoToNextRow(){++steps;if(position+1==failAt)return E_ERROR;++position;if(position==revokeAt)permissionError=201;return position>=static_cast<int>(rows.size())?E_ROW_OUT_RANGE:E_OK;}
 int GetInt(int column,int &value){assert(column==0);value=rows.at(position).field;return E_OK;}
 int GetString(int column,std::string &value){const Row&r=rows.at(position);value=column==1?r.id:column==2?r.name:r.alias;return E_OK;}
 int GetLong(int column,int64_t &value){assert(column==4||column==2);value=rows.at(position).votes;return E_OK;}
};}
namespace OHOS::Media {
constexpr int32_t PERMISSION=201,INTERNAL=23800301;
constexpr size_t SUGGESTION_TYPE_COUNT=7;
constexpr size_t MAX_RESULT_BYTES=8*1024*1024,MAX_STRING_BYTES=64*1024;
int32_t AccessError(){return permissionError;}
// ACTUAL_DECLARATIONS
// ACTUAL_FUNCTIONS
}
int main(){using namespace OHOS::Media;
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();for(int i=0;i<25;++i)cursor->rows.push_back({7,std::to_string(i),"holiday",{},i+1});Work work;assert(work.count==std::numeric_limits<size_t>::max());ReadEntities(cursor,work);assert(work.error==0&&work.entities.size()==25&&cursor->steps==26);std::mt19937_64 random(1);auto ordered=Knowledge::RandomVote(work.entities,work.count,random);assert(ordered.size()==25);auto zero=Knowledge::RandomVote(work.entities,0,random);assert(zero.empty());}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{1,"id","name","alias",1},{1,"id","name","alias",1},{1,"id","name","alias2",1}};Work work;ReadEntities(cursor,work);assert(work.error==0&&work.entities.size()==1&&work.entities[0].aliases.size()==2);}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();Work work;ReadEntities(cursor,work);assert(work.error==0&&work.entities.empty());}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{1,"id","name",{},1}};cursor->failAt=0;Work work;ReadEntities(cursor,work);assert(work.error==INTERNAL&&work.entities.empty());}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{1,"id","name",{},1},{1,"id2","name",{},1}};cursor->revokeAt=0;Work work;ReadEntities(cursor,work);assert(work.error==PERMISSION&&cursor->steps==1);permissionError=0;}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{1,"id","name",{},1}};Work work;work.resultBytes=MAX_RESULT_BYTES-1;ReadEntities(cursor,work);assert(work.error==INTERNAL&&work.entities.empty()&&cursor->steps==1);}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{1,"id",std::string(MAX_STRING_BYTES+1,'x'),{},1}};Work work;ReadEntities(cursor,work);assert(work.error==INTERNAL&&work.entities.empty());}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{0,"actual suggestion",{},{},12}};Work work;ReadSuggestions(cursor,work);assert(work.error==0&&work.suggestions.size()==1&&work.suggestions[0].count==12);}
 {auto cursor=std::make_shared<OHOS::NativeRdb::ResultSet>();cursor->rows={{0,"actual suggestion",{},{},std::numeric_limits<int64_t>::max()}};Work work;ReadSuggestions(cursor,work);assert(work.error==INTERNAL&&work.suggestions.empty());}
 {Value none;none.number=0;Value holiday;holiday.number=7;Value array;array.type=napi_object;array.array=true;array.items={&none,&holiday};std::vector<int32_t> fields;assert(!IntegerArray(nullptr,&array,fields,false));array.items={&holiday};fields.clear();assert(IntegerArray(nullptr,&array,fields,false)&&fields==std::vector<int32_t>{7});fields.clear();assert(!IntegerArray(nullptr,&array,fields,true));}
 for(double n:{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),1.5,2147483648.0}){Value v;v.number=n;int32_t result=0;assert(!Number(nullptr,&v,result));}
 std::cout<<"actual streaming cursor/default-count/NONE/HOLIDAY/number/error/budget functions passed\n";
}
