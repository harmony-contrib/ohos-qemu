// Protocol/permission counterexamples with actual service block/query builder.
// Host doubles only; no claim about IPC tokens, a database or a guest.
#include "knowledge_content_query.h"
#include <cassert>
#include <iostream>
#include <memory>
#include <string>
#include <variant>
#include <vector>
namespace NativeRdb {
struct ValueObject {
    std::variant<int64_t,std::string> value;
    ValueObject(int64_t v):value(v){} ValueObject(const std::string&v):value(v){}
};
struct ResultSet { void Close(){} };
}
struct DataShareResultSet {
    explicit DataShareResultSet(std::shared_ptr<NativeRdb::ResultSet>&){}
};
struct DataSharePredicates {
    bool foreign=false;
    std::vector<int> GetOperationList() const {return foreign?std::vector<int>{1}:std::vector<int>{};}
    std::string GetWhereClause() const {return {};}
    std::vector<std::string> GetWhereArgs() const {return {};}
};
struct DatashareBusinessError {int code=0;void SetCode(int value){code=value;}};
struct Uri {std::string value;std::string ToString()const{return value;}};
constexpr const char *MEDIALIBRARY_DATA_URI="host-only-media-owner";
static bool systemApp=true,readAllowed=true,storeAvailable=true,queryAvailable=true;
static int queries=0;
static std::string actualSql;
static std::vector<NativeRdb::ValueObject> actualArgs;
struct PermissionUtils {
    static bool IsSystemApp(){return systemApp;}
    static bool CheckCallerPermission(const std::string&p){assert(p=="ohos.permission.READ_IMAGEVIDEO");return readAllowed;}
};
struct Store {
    std::shared_ptr<NativeRdb::ResultSet> QueryByStep(const std::string&sql,
        const std::vector<NativeRdb::ValueObject>&args,bool preCount){
        assert(!preCount);++queries;actualSql=sql;actualArgs=args;
        return queryAvailable?std::make_shared<NativeRdb::ResultSet>():nullptr;
    }
};
struct MediaLibraryRdbStore {static std::shared_ptr<Store> GetRaw(){return storeAvailable?std::make_shared<Store>():nullptr;}};
struct RdbUtils {static std::shared_ptr<NativeRdb::ResultSet> ToResultSetBridge(const std::shared_ptr<NativeRdb::ResultSet>&r){return r;}};
#define MEDIA_ERR_LOG(...) do {} while (0)
using namespace OHOS::Media;
static std::shared_ptr<DataShareResultSet> Query(const Uri&uri,const DataSharePredicates&predicates,
    std::vector<std::string>&columns,DatashareBusinessError&businessError){
// ACTUAL_SERVICE_QUERY
    assert(false&&"test must select the fixed service route");return nullptr;
}
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
