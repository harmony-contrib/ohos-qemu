// Host-only dependency adapter: actual production producer executes against real SQLite transactions.
#ifndef BATCH_MEDIA_KNOWLEDGE_RDB_SHIM_H
#define BATCH_MEDIA_KNOWLEDGE_RDB_SHIM_H
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <variant>
#include <vector>
#include <cstdlib>
#include <functional>
#include <sqlite3.h>
namespace OHOS::NativeRdb {
constexpr int E_OK=0,E_ERROR=-1;
class ValueObject {public: std::variant<int64_t,std::string> value;ValueObject():value(int64_t(0)){} ValueObject(const std::string &s):value(s){} ValueObject(int64_t n):value(n){};};
using Values=std::vector<ValueObject>;
inline std::function<void(const std::string &)> testTransactionCallout;
inline std::pair<int32_t,ValueObject> ExecuteOn(sqlite3 *db,const std::string &sql,const Values &args)
{
 sqlite3_stmt *statement=nullptr;
 if(sqlite3_prepare_v2(db,sql.c_str(),-1,&statement,nullptr)!=SQLITE_OK)return {E_ERROR,{}};
 for(size_t i=0;i<args.size();++i){int result;
  if(std::holds_alternative<int64_t>(args[i].value))result=sqlite3_bind_int64(statement,static_cast<int>(i)+1,std::get<int64_t>(args[i].value));
  else {const auto&s=std::get<std::string>(args[i].value);result=sqlite3_bind_text(statement,static_cast<int>(i)+1,s.c_str(),static_cast<int>(s.size()),SQLITE_TRANSIENT);}
  if(result!=SQLITE_OK){sqlite3_finalize(statement);return {E_ERROR,{}};}
 }
 const int status=sqlite3_step(statement);sqlite3_finalize(statement);return {status==SQLITE_DONE?E_OK:E_ERROR,{}};
}
class Transaction {public:
 enum {DEFERRED,IMMEDIATE,EXCLUSIVE};sqlite3 *db;bool active=true;int statements=0;
 explicit Transaction(sqlite3 *database):db(database){}
 std::pair<int32_t,ValueObject> Execute(const std::string &sql,const Values &args={}){
  if(testTransactionCallout)testTransactionCallout(sql);
  ++statements;const char *failure=std::getenv("BATCH_MEDIA_TEST_FAIL_STATEMENT");if(failure&&statements==std::atoi(failure))return {E_ERROR,{}};
  return ExecuteOn(db,sql,args);
 }
 int32_t Commit(){if(std::getenv("BATCH_MEDIA_TEST_FAIL_COMMIT"))return E_ERROR;int r=sqlite3_exec(db,"COMMIT",nullptr,nullptr,nullptr);if(r==SQLITE_OK)active=false;return r==SQLITE_OK?E_OK:E_ERROR;}
 int32_t Rollback(){int r=sqlite3_exec(db,"ROLLBACK",nullptr,nullptr,nullptr);active=false;return r==SQLITE_OK?E_OK:E_ERROR;}
 int32_t Close(){if(active)Rollback();return E_OK;}
 ~Transaction(){if(active)Rollback();}
};
class RdbStore {public:
 sqlite3 *db=nullptr;
 explicit RdbStore(const char *path){if(sqlite3_open(path,&db)!=SQLITE_OK)std::abort();}
 ~RdbStore(){sqlite3_close(db);}
 std::pair<int32_t,ValueObject> Execute(const std::string &sql,const Values &args={}){return ExecuteOn(db,sql,args);}
 std::pair<int32_t,std::shared_ptr<Transaction>> CreateTransaction(int32_t mode){if(mode!=Transaction::IMMEDIATE)std::abort();if(sqlite3_exec(db,"BEGIN IMMEDIATE",nullptr,nullptr,nullptr)!=SQLITE_OK)return {E_ERROR,nullptr};return {E_OK,std::make_shared<Transaction>(db)};}
};
}
#endif
