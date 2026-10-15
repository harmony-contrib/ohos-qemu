"""Actual statement functions and real SQLite; value/asset decoders are doubles."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_photo_result_set import function

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/distributeddatamgr/relational_store/expression_blob_values'
spec = importlib.util.spec_from_file_location('sqlite_blob_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)


def compile_run(source, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); file = root / 'statement.cpp'; file.write_text(source)
        executable = root / 'statement'
        compiler = shutil.which('clang++')
        if compiler is None:
            raise ValueError('real C++ compiler required')
        child = subprocess.run([compiler, '-std=c++17', '-fsanitize=address,undefined',
            '-fno-omit-frame-pointer', str(file), '-lsqlite3', '-o', str(executable)],
            capture_output=True, text=True)
        if child.returncode:
            raise AssertionError(child.stderr)
        child = subprocess.run([str(executable)], capture_output=True, text=True)
        if child.returncode:
            raise AssertionError(child.stderr)

SUPPORT = r'''
#include <sqlite3.h>
#include <cassert>
#include <algorithm>
#include <cstdint>
#include <memory>
#include <string>
#include <variant>
#include <vector>
constexpr int E_OK=0,E_ERROR=-1,COLUMN_TYPE_INVALID=-1,E_INVALID_COLUMN_TYPE=-2;
enum class ColumnType {TYPE_NULL,TYPE_INTEGER,TYPE_FLOAT,TYPE_STRING,TYPE_BLOB,
 TYPE_ASSET,TYPE_ASSETS,TYPE_FLOAT32_ARRAY,TYPE_BIGINT};
struct Asset{};using Assets=std::vector<Asset>;using Floats=std::vector<float>;struct BigInt{};
struct ValueObject {
 using Asset=::Asset;using Assets=::Assets;using FloatVector=::Floats;using BigInt=::BigInt;
 using Bytes=std::vector<uint8_t>;
 std::variant<std::monostate,int64_t,double,std::string,Bytes,Asset,Assets,FloatVector,BigInt> value;
 ValueObject()=default;template<class T>ValueObject(T item):value(std::move(item)){}
 template<class T>static std::string DeclType(){
  if constexpr(std::is_same_v<T,Asset>)return "ASSET";
  if constexpr(std::is_same_v<T,Assets>)return "ASSETS";
  if constexpr(std::is_same_v<T,FloatVector>)return "FLOATVECTOR";
  return "BIGINT";}
};
struct RawDataParser {template<class T>static void ParserRawData(const uint8_t*,int,T&){assert(false);}};
struct StringUtils {static std::string TruncateAfterFirstParen(std::string s){return s.substr(0,s.find('('));}};
struct SqliteUtils {static std::string StrToUpper(std::string s){
 std::transform(s.begin(),s.end(),s.begin(),[](unsigned char c){return std::toupper(c);});return s;}};
#define LOG_ERROR(...) ((void)0)
struct SqliteStatement {
 sqlite3_stmt* stmt_;mutable std::vector<int32_t> types_;
 explicit SqliteStatement(sqlite3_stmt* stmt):stmt_(stmt),types_(sqlite3_column_count(stmt),COLUMN_TYPE_INVALID){}
 int IsValid(int i)const{return i<0||i>=sqlite3_column_count(stmt_)?E_ERROR:E_OK;}
 std::pair<int32_t,int32_t> GetColumnType(int)const;
 std::pair<int32_t,ValueObject> GetColumn(int)const;
 ValueObject GetValueFromBlob(int32_t,int32_t)const;
};
'''


def source(repaired):
    data = gzip.decompress(base64.b64decode((Path(__file__).with_name('fixtures') /
                                           'sqlite_statement.cpp.gz.b64').read_bytes()))
    if hashlib.sha256(data).hexdigest() != baseline.FILES[0][1]:
        raise ValueError('complete pinned SQLite statement fixture differs')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); target = root / baseline.PROJECT / baseline.FILES[0][0]
        target.parent.mkdir(parents=True);target.write_bytes(data)
        if repaired:
            subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                           check=True, capture_output=True)
            baseline.validate(root, require_patched=True)
        text = target.read_text()
    return ''.join(function(text, signature) for signature in (
        'static int32_t Convert2ColumnType(',
        'std::pair<int32_t, int32_t> SqliteStatement::GetColumnType(',
        'std::pair<int32_t, ValueObject> SqliteStatement::GetColumn(',
        'ValueObject SqliteStatement::GetValueFromBlob('))


class SqliteExpressionBlobTests(unittest.TestCase):
    def test_original_rejects_literal_blob_and_loses_declared_empty_blob_type(self):
        main = r'''
int main(){sqlite3* db=nullptr;sqlite3_stmt* raw=nullptr;assert(sqlite3_open(":memory:",&db)==SQLITE_OK);
 assert(sqlite3_prepare_v2(db,"SELECT X'00117fff' AS b",-1,&raw,nullptr)==SQLITE_OK);
 assert(sqlite3_step(raw)==SQLITE_ROW);SqliteStatement s(raw);
 assert(s.GetColumn(0).first==E_ERROR);sqlite3_finalize(raw);
 assert(sqlite3_exec(db,"CREATE TABLE data(b BLOB);INSERT INTO data VALUES(X'')",nullptr,nullptr,nullptr)==SQLITE_OK);
 assert(sqlite3_prepare_v2(db,"SELECT b FROM data",-1,&raw,nullptr)==SQLITE_OK);
 assert(sqlite3_step(raw)==SQLITE_ROW);SqliteStatement empty(raw);
 auto [code,value]=empty.GetColumn(0);assert(code==E_OK&&std::holds_alternative<std::monostate>(value.value));
 sqlite3_finalize(raw);sqlite3_close(db);}
'''
        compile_run(SUPPORT + source(False) + main, language='c++', extra_flags=['-lsqlite3'])

    def test_repaired_real_sqlite_literals_bound_values_union_null_empty_and_declared_types(self):
        main = r'''
int main(){sqlite3* db=nullptr;sqlite3_stmt* raw=nullptr;assert(sqlite3_open(":memory:",&db)==SQLITE_OK);
 assert(sqlite3_prepare_v2(db,"SELECT 7,1.25,'text',X'00117fff',NULL,X'' UNION ALL SELECT 8,2.5,'next',X'00',NULL,X''",
 -1,&raw,nullptr)==SQLITE_OK);SqliteStatement s(raw);
 for(int row=0;row<2;++row){assert(sqlite3_step(raw)==SQLITE_ROW);
  assert(std::get<int64_t>(s.GetColumn(0).second.value)==7+row);
  assert(std::get<double>(s.GetColumn(1).second.value)==(row?2.5:1.25));
  assert(std::get<std::string>(s.GetColumn(2).second.value)==(row?"next":"text"));
  auto blob=std::get<ValueObject::Bytes>(s.GetColumn(3).second.value);
  assert(blob==(row?ValueObject::Bytes{0}:ValueObject::Bytes{0,17,127,255}));
  blob[0]=255;assert(std::get<ValueObject::Bytes>(s.GetColumn(3).second.value)[0]==0);
  assert(std::holds_alternative<std::monostate>(s.GetColumn(4).second.value));
  assert(std::get<ValueObject::Bytes>(s.GetColumn(5).second.value).empty());}
 sqlite3_finalize(raw);
 assert(sqlite3_prepare_v2(db,"SELECT ?1",-1,&raw,nullptr)==SQLITE_OK);
 const uint8_t bytes[]={0,255,1};assert(sqlite3_bind_blob(raw,1,bytes,3,SQLITE_TRANSIENT)==SQLITE_OK);
 assert(sqlite3_step(raw)==SQLITE_ROW);SqliteStatement bound(raw);
 assert(std::get<ValueObject::Bytes>(bound.GetColumn(0).second.value)==ValueObject::Bytes({0,255,1}));
 assert(bound.GetColumn(-1).first!=E_OK&&bound.GetColumn(1).first!=E_OK);sqlite3_finalize(raw);
 assert(sqlite3_exec(db,"CREATE TABLE data(b BLOB,a ASSET,aa ASSETS,f FLOATVECTOR,bi BIGINT);"
 "INSERT INTO data VALUES(X'',X'01',X'01',X'01',X'01')",nullptr,nullptr,nullptr)==SQLITE_OK);
 assert(sqlite3_prepare_v2(db,"SELECT * FROM data",-1,&raw,nullptr)==SQLITE_OK);
 assert(sqlite3_step(raw)==SQLITE_ROW);SqliteStatement declared(raw);
 assert(std::get<ValueObject::Bytes>(declared.GetColumn(0).second.value).empty());
 for(int i=1;i<5;++i)assert(declared.GetColumnType(i)==std::make_pair(E_OK,int(ColumnType::TYPE_ASSET)+i-1));
 sqlite3_finalize(raw);sqlite3_close(db);}
'''
        compile_run(SUPPORT + source(True) + main, language='c++', extra_flags=['-lsqlite3'])


if __name__ == '__main__':
    unittest.main()
