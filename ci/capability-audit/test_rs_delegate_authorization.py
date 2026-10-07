"""Actual repaired delegate/type guards with host seams; not guest security proof."""
import unittest

from test_rs_transaction_validation import RS, run_sanitized


class RsDelegateAuthorizationTests(unittest.TestCase):
    def test_delegate_preserves_denied_commands_and_checks_again_at_execution(self):
        extraction = RS.REPLACEMENTS[RS.DELEGATE][1][1]
        execution = RS.REPLACEMENTS[RS.DELEGATE][0][1]
        source = r'''#include <cassert>
#include <cstdint>
#include <memory>
#include <queue>
#include <tuple>
#include <vector>
struct RSCommand {
    bool valid;
    int id;
    bool IsCallingPidValid() const { return valid; }
    void Process(std::vector<int>& context) { assert(valid);context.push_back(id); }
};
using Payload=std::vector<std::tuple<uint64_t,uint8_t,std::unique_ptr<RSCommand>>>;
void Extract(Payload& processPayload,std::queue<std::unique_ptr<RSCommand>>& cmdQueue,size_t cap) {
    for(auto it=processPayload.begin();it!=processPayload.end();) {
        auto& command=std::get<2>(*it);
''' + extraction + r'''        cmdQueue.push(std::move(command));it=processPayload.erase(it);
        if(cmdQueue.size()>=cap) break;
    }
}
void Execute(std::queue<std::unique_ptr<RSCommand>>& cmdqueue,std::vector<int>& context) {
    while(!cmdqueue.empty()) {
        auto cmd=std::move(cmdqueue.front());cmdqueue.pop();
''' + execution + r'''        }
    }
}
int main() {
    for(size_t cap:{1,2,64}) {
        Payload payload;
        // Null defensive boundary, own/system-rejected, foreign-node rejected,
        // then two valid ordinary/UIExtension commands.
        payload.emplace_back(0,0,nullptr);
        for(int id=1;id<=4;++id) payload.emplace_back(0,0,std::make_unique<RSCommand>(RSCommand{id>=3,id}));
        std::queue<std::unique_ptr<RSCommand>> queue;
        std::vector<int> seen;
        Extract(payload,queue,cap);Execute(queue,seen);
        if(cap==1) { assert(seen==std::vector<int>{3});Extract(payload,queue,cap);Execute(queue,seen); }
        assert((seen==std::vector<int>{3,4}));assert(payload.size()==3);
        assert(!std::get<2>(payload[0]));
        assert(!std::get<2>(payload[1])->IsCallingPidValid());
        assert(!std::get<2>(payload[2])->IsCallingPidValid());
        // Reject a command invalidated after extraction too.
        queue.push(std::make_unique<RSCommand>(RSCommand{false,5}));queue.push(nullptr);
        Execute(queue,seen);assert((seen==std::vector<int>{3,4}));
    }
}
'''
        self.assertNotIn('SetCallingPidValid(true)', extraction)
        run_sanitized(source)

    def test_registration_uses_kernel_pid_not_client_pid_and_bounds_routing_only(self):
        source = r'''#include <cassert>
#include <climits>
#include <cstdint>
#include <initializer_list>
#include <sys/types.h>
constexpr int ERR_INVALID_STATE=-1;
struct MessageOption { static constexpr int TF_ASYNC=1; };
struct Option { int flags;int GetFlags() const { return flags; } };
pid_t caller;
pid_t GetCallingPid() { return caller; }
int Register(Option option,int32_t pid,uint32_t tid,uint64_t listenerId) {
''' + RS.DELEGATE_REGISTRATION + r'''    return 0;
}
int main() {
    for(pid_t real:{-1,0,1,111,65535,65536,70000}) {
        caller=real;
        const uint64_t id=((static_cast<uint64_t>(real)&0xFFFF)<<48)|42;
        for(uint32_t tid:{0U,1U,111U,static_cast<uint32_t>(INT32_MAX),UINT32_MAX}) {
            assert((Register({0},real,tid,id)==0)==(real>0 && tid>0 && tid<=INT32_MAX));
            assert(Register({MessageOption::TF_ASYNC},real,tid,id)==ERR_INVALID_STATE);
            assert(Register({0},real+1,tid,id)==ERR_INVALID_STATE);
            assert(Register({0},real,tid,id^(1ULL<<48))==ERR_INVALID_STATE);
        }
    }
}
'''
        run_sanitized(source)

    def test_freeze_screen_parent_uses_existing_type_checked_cast(self):
        source = r'''#include <cassert>
#include <memory>
#include <vector>
enum class Type { OTHER,DISPLAY,SCREEN };
struct RSBaseRenderNode {
    Type type;
    explicit RSBaseRenderNode(Type value):type(value) {}
    virtual ~RSBaseRenderNode()=default;
    template<class T> static std::shared_ptr<T> ReinterpretCast(std::shared_ptr<RSBaseRenderNode> node) {
        return node && node->type==T::TYPE?std::static_pointer_cast<T>(node):nullptr;
    }
};
struct RSScreenRenderNode:RSBaseRenderNode {
    static constexpr Type TYPE=Type::SCREEN;
    bool frozen=false;
    RSScreenRenderNode():RSBaseRenderNode(TYPE) {}
    void SetForceFreeze(bool value) { frozen=value; }
};
struct Display:RSBaseRenderNode {
    std::weak_ptr<RSBaseRenderNode> parent;
    Display():RSBaseRenderNode(Type::DISPLAY) {}
    std::weak_ptr<RSBaseRenderNode> GetParent() const { return parent; }
};
bool Freeze(std::shared_ptr<Display> displayNode) {
''' + RS.FREEZE_SCREEN_PARENT + r'''    if(!screenNode) return false;
    screenNode->SetForceFreeze(true);return true;
}
int main() {
    assert(!Freeze(nullptr));auto display=std::make_shared<Display>();assert(!Freeze(display));
    auto other=std::make_shared<RSBaseRenderNode>(Type::OTHER);display->parent=other;assert(!Freeze(display));
    auto logical=std::make_shared<Display>();display->parent=logical;assert(!Freeze(display));
    auto screen=std::make_shared<RSScreenRenderNode>();display->parent=screen;
    assert(Freeze(display) && screen->frozen);screen.reset();assert(!Freeze(display));
}
'''
        self.assertNotIn('static_pointer_cast', RS.FREEZE_SCREEN_PARENT)
        run_sanitized(source)


if __name__ == '__main__':
    unittest.main()
