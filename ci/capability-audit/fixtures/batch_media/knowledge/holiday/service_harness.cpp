// Protocol/permission counterexamples with actual service block/query builder.
// Host doubles only; no claim about IPC tokens, a database or a guest.
#include "knowledge_content_query.h"
#include <cassert>
#include <iostream>
#include <memory>
#include <string>
#include <utility>
#include <variant>
#include <vector>
namespace OHOS::NativeRdb {
struct ValueObject {
    std::variant<int64_t,std::string> value;
    ValueObject(int64_t v):value(v){} ValueObject(const std::string&v):value(v){}
};
struct ResultSet { void Close(); };
}
namespace OHOS::DataShare {
struct ResultSetBridge {
    std::shared_ptr<OHOS::NativeRdb::ResultSet> result;
    explicit ResultSetBridge(std::shared_ptr<OHOS::NativeRdb::ResultSet> value):result(std::move(value)){}
};
struct DataShareResultSet {
    std::shared_ptr<ResultSetBridge> bridge;
    explicit DataShareResultSet(std::shared_ptr<ResultSetBridge>&value):bridge(value){}
};
}
struct DataSharePredicates {
    bool foreign=false;
    std::vector<int> GetOperationList() const {return foreign?std::vector<int>{1}:std::vector<int>{};}
    std::string GetWhereClause() const {return {};}
    std::vector<std::string> GetWhereArgs() const {return {};}
};
struct DatashareBusinessError {int code=0;void SetCode(int value){code=value;}};
struct Uri {std::string value;std::string ToString()const{return value;}};
constexpr const char *MEDIALIBRARY_DATA_URI="host-only-media-owner";
using NativeRdbValue = OHOS::NativeRdb::ValueObject;
using OHOS::DataShare::DataShareResultSet;
static bool systemApp=true,readAllowed=true,storeAvailable=true,queryAvailable=true,bridgeAvailable=true;
static int closes=0,bridges=0;
void OHOS::NativeRdb::ResultSet::Close(){++closes;}
static int queries=0;
static std::string actualSql;
static std::vector<NativeRdbValue> actualArgs;
struct PermissionUtils {
    static bool IsSystemApp(){return systemApp;}
    static bool CheckCallerPermission(const std::string&p){assert(p=="ohos.permission.READ_IMAGEVIDEO");return readAllowed;}
};
struct Store {
    std::shared_ptr<OHOS::NativeRdb::ResultSet> QueryByStep(const std::string&sql,
        const std::vector<NativeRdbValue>&args,bool preCount){
        assert(!preCount);++queries;actualSql=sql;actualArgs=args;
        return queryAvailable?std::make_shared<OHOS::NativeRdb::ResultSet>():nullptr;
    }
};
struct MediaLibraryRdbStore {static std::shared_ptr<Store> GetRaw(){return storeAvailable?std::make_shared<Store>():nullptr;}};
namespace OHOS::RdbDataShareAdapter {
struct RdbUtils {
    static std::shared_ptr<DataShare::ResultSetBridge> ToResultSetBridge(std::shared_ptr<NativeRdb::ResultSet> result){
        ++::bridges;
        return ::bridgeAvailable ? std::make_shared<DataShare::ResultSetBridge>(std::move(result)) : nullptr;
    }
};
}
#define MEDIA_ERR_LOG(...) do {} while (0)
using namespace OHOS::Media;
namespace OHOS::AbilityRuntime {
static std::shared_ptr<DataShareResultSet> Query(const Uri&uri,const DataSharePredicates&predicates,
    std::vector<std::string>&columns,DatashareBusinessError&businessError){
// ACTUAL_SERVICE_QUERY
    assert(false&&"test must select the fixed service route");return nullptr;
}
}
using OHOS::AbilityRuntime::Query;
int main(){
    Uri uri{std::string(MEDIALIBRARY_DATA_URI)+"/knowledge-content"};
    DataSharePredicates predicates;DatashareBusinessError error;
    auto wire=Knowledge::RelatedWire("20261231' OR 1=1 --",{6},{7});
    systemApp=false;readAllowed=true;assert(!Query(uri,predicates,wire,error)&&error.code==202&&queries==0);
    systemApp=true;readAllowed=false;assert(!Query(uri,predicates,wire,error)&&error.code==201&&queries==0);
    readAllowed=true;assert(Query(uri,predicates,wire,error)&&error.code==0&&queries==1);
    assert(actualSql.find("20261231")==std::string::npos);
    assert(actualArgs.size()==4&&std::get<std::string>(actualArgs[1].value)=="20261231' OR 1=1 --");
    predicates.foreign=true;assert(!Query(uri,predicates,wire,error)&&error.code==13900020&&queries==1);
    predicates.foreign=false;auto extra=wire;extra.push_back("SELECT * FROM Photos");
    assert(!Query(uri,predicates,extra,error)&&error.code==13900020&&queries==1);
    storeAvailable=false;assert(!Query(uri,predicates,wire,error)&&error.code==23800301&&queries==1);
    storeAvailable=true;queryAvailable=false;assert(!Query(uri,predicates,wire,error)&&error.code==23800301&&queries==2);
    readAllowed=false;assert(!Query(uri,predicates,wire,error)&&error.code==201&&queries==2);
    readAllowed=true;queryAvailable=true;bridgeAvailable=false;
    const int priorQueries=queries,priorCloses=closes,priorBridges=bridges;
    assert(!Query(uri,predicates,wire,error)&&error.code==23800301);
    assert(queries==priorQueries+1&&closes==priorCloses+1&&bridges==priorBridges+1);
    bridgeAvailable=true;
    auto bridged=Query(uri,predicates,wire,error);
    assert(bridged&&bridged->bridge&&bridged->bridge->result&&error.code==0);
    assert(queries==priorQueries+2&&closes==priorCloses+1&&bridges==priorBridges+2);
    Knowledge::Query output;
    for(auto bad:std::vector<std::vector<std::string>>{{},{"raw-sql","SELECT 1"},
        {"KnowledgeContent.service.v1","related","day","01","6","1","7"},
        {"KnowledgeContent.service.v1","related","day","2","6","6","1","7"},
        {"KnowledgeContent.service.v1","related","day","1","0","1","7"},
        {"KnowledgeContent.service.v1","suggestions","1","7"}}){assert(!Knowledge::DecodeServiceWire(bad,output));}
    assert(!Knowledge::DecodeServiceWire(Knowledge::RelatedWire(std::string(65537,'x'),{6},{7}),output));
    assert(Knowledge::DecodeServiceWire(Knowledge::SuggestionsWire({0,6}),output));
    assert(!output.sql.empty());
    std::cout<<"actual fixed-wire decoder and service guard counterexamples passed (host doubles only)\n";
}
