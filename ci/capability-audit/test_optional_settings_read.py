"""Exercise actual optional-query code with explicit DataShare failure doubles."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/netmanager_base/optional_settings_read/0001-distinguish-absent-settings-from-query-failure.patch'


class OptionalSettingsReadTests(unittest.TestCase):
    def test_no_row_is_not_permission_transport_or_result_decode_failure(self):
        sections = patch_sections(PATCH)
        hunks = next(value for name, value in sections.items() if name.endswith('/src/net_datashare_utils.cpp'))
        body = '\n'.join(hunks[0][2][:-3])
        source = r'''
#include <cassert>
#include <memory>
#include <string>
#include <utility>
#include <vector>
using Uri=std::string;
constexpr int NETMANAGER_ERROR=-1, NETMANAGER_SUCCESS=0;
constexpr const char* SETTINGS_DATA_COLUMN_KEYWORD="KEYWORD";
constexpr const char* SETTINGS_DATA_COLUMN_VALUE="VALUE";
int rows=1,failure=0,calls=0,closes=0,releases=0,business=0;
bool missingHelper=false,missingResult=false;
int Step(){return ++calls==failure?-1:0;}
namespace DataShare {
constexpr int E_OK=0;
struct DatashareBusinessError {int GetCode(){return business;}};
struct DataSharePredicates {void EqualTo(const char* column,const std::string& key){
    assert(std::string(column)=="KEYWORD" && key=="mode");
}};
struct Result {
    int GetRowCount(int& count){count=rows;return Step();}
    int GoToFirstRow(){return Step();}
    int GetColumnIndex(const char* name,int& index){assert(std::string(name)=="VALUE");index=3;return Step();}
    int GetString(int index,std::string& value){assert(index==3);value="real-setting";return Step();}
    void Close(){++closes;}
};
struct Helper {
    std::shared_ptr<Result> Query(Uri& uri,DataSharePredicates&,std::vector<std::string>& columns,
        DatashareBusinessError* error){assert(uri=="settings-uri" && columns.empty() && error);
        return missingResult?nullptr:std::make_shared<Result>();}
    void Release(){++releases;}
};
}
struct NetDataShareHelperUtils {
    std::shared_ptr<DataShare::Helper> CreateDataShareHelper(){return missingHelper?nullptr:std::make_shared<DataShare::Helper>();}
    int32_t QueryOptional(Uri&,const std::string&,std::string&,bool&);
};
'''
        main = r'''
int main(){
    NetDataShareHelperUtils helper;Uri uri="settings-uri";
    for(rows=-1;rows<=2;++rows) for(failure=0;failure<=4;++failure) {
        calls=closes=releases=0;std::string value="stale";bool found=true;
        int result=helper.QueryOptional(uri,"mode",value,found);
        bool absent=rows==0 && failure!=1;
        bool present=rows==1 && failure==0;
        assert(result==(absent||present?0:-1));assert(found==present);
        assert(value==(present?"real-setting":""));assert(closes==1 && releases==1);
    }
    rows=1;failure=0;
    for(int scenario=0;scenario<3;++scenario){
        missingHelper=scenario==0;missingResult=scenario==1;business=scenario==2?201:0;
        calls=closes=releases=0;std::string value="stale";bool found=true;
        assert(helper.QueryOptional(uri,"mode",value,found)==-1);
        assert(!found && value.empty() && calls==0);
        assert(closes==(scenario==2?1:0));assert(releases==(scenario==0?0:1));
    }
}
'''
        compile_run(source + body + main, language='c++')


if __name__ == '__main__':
    unittest.main()
