"""Actual queue budget/scope/post snippets with host seams; not guest IPC proof."""
import unittest

from test_rs_transaction_validation import RS, run_sanitized


PREFIX = r'''#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
#include <sys/types.h>
using ErrCode=int;
constexpr int ERR_OK=0,ERR_INVALID_STATE=-1;
#define RS_LOGW(...) ((void)0)
namespace AppExecFwk { struct EventQueue { enum class Priority { IMMEDIATE }; }; }
namespace RSTaskMessage { using RSTask=std::function<void()>; }
struct Handler {
    bool accepting=true,immediate=false;
    unsigned attempts=0;
    std::vector<std::function<void()>> tasks;
    bool PostTask(std::function<void()> task,AppExecFwk::EventQueue::Priority priority) {
        assert(priority==AppExecFwk::EventQueue::Priority::IMMEDIATE);++attempts;
        if(!accepting) return false;
        if(immediate) task();else tasks.push_back(std::move(task));
        return true;
    }
};
struct RSTransactionData {
    static std::atomic<int> live;
    int index;
    explicit RSTransactionData(int id):index(id) { ++live; }
    ~RSTransactionData() { --live; }
    bool GetDVSyncUpdate() const { return index%2==0; }
    uint64_t GetDVSyncTime() const { return static_cast<uint64_t>(index); }
    uint64_t GetTimestamp() const { return static_cast<uint64_t>(index+100); }
};
std::atomic<int> RSTransactionData::live{0};
struct RSMainThread {
    std::thread::id owner=std::this_thread::get_id();
    std::shared_ptr<Handler> handler_=std::make_shared<Handler>();
    bool singleFrame=false;
    int sfc=0,normal=0,dvsync=0;
    std::vector<int> seen;
    void Check() const { assert(std::this_thread::get_id()==owner); }
    bool TryPostTask(RSTaskMessage::RSTask task);
    void DVSyncUpdate(uint64_t time,uint64_t timestamp) {
        Check();assert(timestamp==time+100);++dvsync;
    }
    bool IsNeedProcessBySingleFrameComposer(std::unique_ptr<RSTransactionData>&) { Check();return singleFrame; }
    void ProcessDataBySingleFrameComposer(std::unique_ptr<RSTransactionData>& data) {
        Check();++sfc;seen.push_back(data->index);
    }
    void RecvRSTransactionData(std::unique_ptr<RSTransactionData>& data) {
        Check();++normal;seen.push_back(data->index);data.reset();
    }
};
struct RSRenderPipeline {
    RSMainThread* main;
    explicit RSRenderPipeline(RSMainThread* thread):main(thread) {}
    RSMainThread* GetMainThread() const { return main; }
};
std::thread::id delegateOwner;
unsigned delegateCalls=0;
struct RsDelegateCompositeCallbackManager {
    static RsDelegateCompositeCallbackManager& GetInstance() { static RsDelegateCompositeCallbackManager m;return m; }
    void PrepareDelegateCompositeCommand(std::unique_ptr<RSTransactionData>& data) {
        assert(data && std::this_thread::get_id()==delegateOwner);++delegateCalls;
    }
};
// A host scheduling seam retains the real packaged_task ownership semantics;
// this does not pretend to link OHOS RefBase, EventHandler or Binder.
namespace ST {
template<class Task> struct ScheduledTask {
    std::packaged_task<std::invoke_result_t<Task>()> task_;
    explicit ScheduledTask(Task&& task):task_(std::move(task)) {}
    static auto Create(Task&& task) {
        auto scheduled=std::make_shared<ScheduledTask>(std::move(task));
        return std::make_pair(scheduled,scheduled->task_.get_future());
    }
    void Run() { task_(); }
};
}
'''


def source(main):
    return (PREFIX + RS.TRY_POST_TASK + RS.COMMIT_PAYLOAD_SCOPE + RS.COMMIT_QUEUE_BUDGET
            + r'''ErrCode Commit(std::shared_ptr<RSRenderPipeline> pipeline,pid_t callingPid,
    std::unique_ptr<RSTransactionData>& transactionData) {
''' + RS.BOUNDED_COMMIT_SUBMIT + '    return ERR_OK;\n}\n' + main)


class RsCommitQueueTests(unittest.TestCase):
    def test_count_bytes_empty_internal_size_overflow_and_pid_isolation_boundaries(self):
        main = r'''int main() {
    std::vector<std::shared_ptr<RSCommitQueuePermit>> held;
    assert(!RSCommitQueuePermit::Create(0,1));assert(!RSCommitQueuePermit::Create(-1,1));
    assert(!RSCommitQueuePermit::Create(1,SIZE_MAX));
    for(size_t i=0;i<COMMIT_PID_COUNT_LIMIT;++i) {
        auto permit=RSCommitQueuePermit::Create(1,1);assert(permit);held.push_back(permit);
    }
    assert(!RSCommitQueuePermit::Create(1,1));assert(RSCommitQueuePermit::Create(2,1));held.clear();
    for(pid_t pid=1;pid<=4;++pid) for(size_t i=0;i<COMMIT_PID_COUNT_LIMIT;++i) {
        auto permit=RSCommitQueuePermit::Create(pid,1);assert(permit);held.push_back(permit);
    }
    assert(held.size()==COMMIT_QUEUE_COUNT_LIMIT);assert(!RSCommitQueuePermit::Create(5,1));held.clear();
    auto fullPid=RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT);assert(fullPid);
    assert(!RSCommitQueuePermit::Create(1,1));assert(RSCommitQueuePermit::Create(2,1));fullPid.reset();
    for(pid_t pid=1;pid<=4;++pid) {
        auto permit=RSCommitQueuePermit::Create(pid,COMMIT_PID_BYTES_LIMIT);assert(permit);held.push_back(permit);
    }
    assert(!RSCommitQueuePermit::Create(5,1));held.clear();
    // Empty/internal input does not bypass byte or count accounting.
    for(size_t i=0;i<COMMIT_PID_BYTES_LIMIT/COMMIT_INTERNAL_SIZE_CHARGE;++i) {
        auto permit=RSCommitQueuePermit::Create(1,0);assert(permit);held.push_back(permit);
    }
    assert(!RSCommitQueuePermit::Create(1,0));held.clear();
    auto complete=RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT);assert(complete);
    { RSCommitQueueCompletion completion(complete); }
    assert(RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT));
    complete->Complete();complete.reset();assert(RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT));
}
'''
        run_sanitized(source(main))

    def test_parallel_global_admission_and_idempotent_completion(self):
        main = r'''int main() {
    std::atomic<unsigned> ready{0};std::atomic<bool> release{false};
    std::vector<std::thread> producers;
    for(pid_t pid=1;pid<=32;++pid) producers.emplace_back([pid,&ready,&release]() {
        std::vector<std::shared_ptr<RSCommitQueuePermit>> held;
        for(unsigned i=0;i<16;++i) { auto permit=RSCommitQueuePermit::Create(pid,1);assert(permit);held.push_back(permit); }
        ready.fetch_add(1);
        while(!release.load()) std::this_thread::yield();
    });
    while(ready.load()!=32) std::this_thread::yield();
    assert(!RSCommitQueuePermit::Create(33,1));release.store(true);
    for(auto& producer:producers) producer.join();
    for(unsigned i=0;i<128;++i) {
        auto permit=RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT);assert(permit);
        std::thread a([permit] { permit->Complete(); });
        std::thread b([permit] { permit->Complete(); });a.join();b.join();
        assert(RSCommitQueuePermit::Create(1,COMMIT_PID_BYTES_LIMIT));
    }
}
'''
        run_sanitized(source(main))

    def test_actual_post_main_thread_order_sfc_dvsync_failure_cancel_and_producer_retention(self):
        main = r'''int main() {
    RSMainThread main;delegateOwner=std::this_thread::get_id();
    auto pipeline=std::make_shared<RSRenderPipeline>(&main);
    std::thread sender([&] {
        for(int i=0;i<20;++i) {
            const RSScopedCommitPayloadSize bytes(32);
            auto data=std::make_unique<RSTransactionData>(i);assert(Commit(pipeline,77,data)==ERR_OK && !data);
        }
    });sender.join();assert(RSTransactionData::live==20 && main.seen.empty() && delegateCalls==0);
    for(size_t i=0;i<main.handler_->tasks.size();++i) {
        main.singleFrame=i%2==1;main.handler_->tasks[i]();
        assert(RSTransactionData::live==19-static_cast<int>(i));
    }
    assert(main.sfc==10 && main.normal==10 && main.dvsync==10 && delegateCalls==20);
    for(int i=0;i<20;++i) assert(main.seen[static_cast<size_t>(i)]==i);
    // Completed queue entries still exist, but retain neither input nor quota.
    assert(RSCommitQueuePermit::Create(77,COMMIT_PID_BYTES_LIMIT));main.handler_->tasks.clear();
    auto cancelled=std::make_unique<RSTransactionData>(30);assert(Commit(pipeline,77,cancelled)==ERR_OK);
    assert(RSTransactionData::live==1);main.handler_->tasks.clear();
    assert(RSTransactionData::live==0 && RSCommitQueuePermit::Create(77,COMMIT_PID_BYTES_LIMIT));
    main.handler_->accepting=false;
    auto refused=std::make_unique<RSTransactionData>(31);assert(Commit(pipeline,77,refused)==ERR_INVALID_STATE);
    assert(RSTransactionData::live==0 && RSCommitQueuePermit::Create(77,COMMIT_PID_BYTES_LIMIT));
    main.handler_->accepting=true;main.handler_->immediate=true;
    auto immediate=std::make_unique<RSTransactionData>(32);assert(Commit(pipeline,77,immediate)==ERR_OK);
    assert(RSTransactionData::live==0 && RSCommitQueuePermit::Create(77,COMMIT_PID_BYTES_LIMIT));
    pipeline->main=nullptr;
    auto missing=std::make_unique<RSTransactionData>(33);assert(Commit(pipeline,77,missing)==ERR_INVALID_STATE);
    assert(RSTransactionData::live==0 && RSCommitQueuePermit::Create(77,COMMIT_PID_BYTES_LIMIT));
    main.handler_.reset();assert(!main.TryPostTask([]{}));
}
'''
        run_sanitized(source(main))

    def test_payload_scope_nested_threads_and_actual_submission_uses_observed_sizes(self):
        main = r'''int main() {
    assert(RSScopedCommitPayloadSize::Get()==0);
    {
        RSScopedCommitPayloadSize outer(12);assert(RSScopedCommitPayloadSize::Get()==12);
        { RSScopedCommitPayloadSize inner(24);assert(RSScopedCommitPayloadSize::Get()==24); }
        assert(RSScopedCommitPayloadSize::Get()==12);
        std::vector<std::thread> threads;
        for(size_t size=1;size<=32;++size) threads.emplace_back([size]() {
            assert(RSScopedCommitPayloadSize::Get()==0);
            { RSScopedCommitPayloadSize local(size);assert(RSScopedCommitPayloadSize::Get()==size); }
            assert(RSScopedCommitPayloadSize::Get()==0);
        });
        for(auto& thread:threads) thread.join();assert(RSScopedCommitPayloadSize::Get()==12);
    }
    assert(RSScopedCommitPayloadSize::Get()==0);
}
'''
        run_sanitized(source(main))
        self.assertTrue(any('payloadSize(data.GetDataSize())' in new for _, new in RS.REPLACEMENTS[RS.FILE]))
        self.assertTrue(any('payloadSize(parsedParcel->GetDataSize())' in new for _, new in RS.REPLACEMENTS[RS.FILE]))
        self.assertLess(RS.BOUNDED_COMMIT_SUBMIT.index('::Create'), RS.BOUNDED_COMMIT_SUBMIT.index('PostBoundedCommit'))
        self.assertIn('!PostBoundedCommit', RS.BOUNDED_COMMIT_SUBMIT)
        self.assertNotIn('.wait()', RS.COMMIT_QUEUE_BUDGET)
        self.assertNotIn('GetSendingPid', RS.COMMIT_QUEUE_BUDGET)


if __name__ == '__main__':
    unittest.main()
