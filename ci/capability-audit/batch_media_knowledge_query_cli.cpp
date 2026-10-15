// Host harness for the actual production SQL builder and RANDOM_VOTE implementation.
#include "knowledge_content_query.h"
#include <cassert>
#include <iostream>
#include <sstream>
using namespace OHOS::Media::Knowledge;
static std::string Quote(const std::string &text)
{
    const char *digits="0123456789abcdef";
    std::string result="\"";
    for (unsigned char value : text) {
        if (value=='"' || value=='\\') {result+='\\';result+=value;}
        else if(value<32) {result+="\\u00";result+=digits[value>>4];result+=digits[value&15];}
        else result+=value;
    }
    return result+'"';
}
static std::vector<int32_t> Fields(const std::string &text)
{
    std::vector<int32_t> result;std::istringstream stream(text);std::string field;
    while(std::getline(stream,field,','))result.push_back(std::stoi(field));
    return result;
}
int main(int argc,char **argv)
{
    assert(argc>=2);std::string mode(argv[1]);
    if(mode=="sampling") {
        std::mt19937_64 random(12345);
        int dominant=0;
        for(int i=0;i<10000;++i) {
            std::vector<Entity> values={{1,"zero","zero",{},0},{1,"large","large",{},100},{1,"small","small",{},1}};
            auto next=RandomVote(values,1,random);assert(next.size()==1 && next[0].id!="zero");
            dominant+=next[0].id=="large";
        }
        assert(dominant>9500 && dominant<9999);
        auto chosen=RandomVote({{1,"a","a",{},1},{1,"b","b",{},5}},100,random);
        assert(chosen.size()==2 && chosen[0].id!=chosen[1].id);
        assert(RandomVote({{1,"zero","zero",{},0}},1,random).empty());
        assert(RandomVote({{1,"a","a",{},1}},0,random).empty());
        for(int i=0;i<=8;++i)assert(IsField(i));
        assert(!IsField(-1) && !IsField(9) && !HasProducer(0) && !HasProducer(7));
        std::cout<<"{\"draws\":10000,\"dominant\":"<<dominant<<"}\n";return 0;
    }
    Query query;
    if(mode=="related") {assert(argc==5);query=Related(argv[2],Fields(argv[3]),Fields(argv[4]));}
    else {assert(mode=="suggestions" && argc==3);query=Suggestions(Fields(argv[2]));}
    std::cout<<"{\"sql\":"<<Quote(query.sql)<<",\"args\":[";
    for(size_t i=0;i<query.args.size();++i) {
        if(i)std::cout<<',';
        if(std::holds_alternative<int64_t>(query.args[i]))std::cout<<std::get<int64_t>(query.args[i]);
        else std::cout<<Quote(std::get<std::string>(query.args[i]));
    }
    std::cout<<"]}\n";
}
