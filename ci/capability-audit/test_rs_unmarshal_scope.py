"""Actual task scope/permit snippets with host thread seams; not guest acceptance."""
import unittest

from test_rs_transaction_validation import RS, run_sanitized


PREFIX = r'''#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <memory>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
using binder_size_t = uint64_t;
#define RSB_EXPORT
#define DISALLOW_COPY_AND_MOVE(Type) \
    Type(const Type&) = delete; Type& operator=(const Type&) = delete; \
    Type(Type&&) = delete; Type& operator=(Type&&) = delete
thread_local bool g_isUnmarshalThread = false;
class AshmemFdWorker;
class AshmemFdContainerScope;
class AshmemFdContainer {
public:
    static AshmemFdContainer& Instance() { thread_local AshmemFdContainer instance; return instance; }
    static void SetIsUnmarshalThread(bool value) { g_isUnmarshalThread=value; }
    void Seed(binder_size_t offset,int fd) { fds_={{offset,fd}};isUseFdContainer_=true; }
    bool Matches(binder_size_t offset,int fd) const {
        const auto found=fds_.find(offset);
        return isUseFdContainer_ && fds_.size()==1 && found!=fds_.end() && found->second==fd;
    }
    bool Empty() const { return fds_.empty() && !isUseFdContainer_; }
private:
    std::unordered_map<binder_size_t,int> fds_;
    bool isUseFdContainer_=false;
    friend class AshmemFdWorker;
    friend class AshmemFdContainerScope;
};
// Only the actual task scope is under test. This stand-in models Merge,
// not a claim that the target Parcel or FD worker has been linked here.
class AshmemFdWorker {
public:
    AshmemFdWorker(binder_size_t offset,int fd):offset_(offset),fd_(fd) {}
    void PushFdsToContainer() {
        assert(g_isUnmarshalThread);
        AshmemFdContainer::Instance().Seed(offset_,fd_);
    }
private:
    binder_size_t offset_;
    int fd_;
};
'''


class RsUnmarshalScopeTests(unittest.TestCase):
    def test_nested_scopes_restore_state_and_error_return_cleans_executing_thread(self):
        main = r'''void ErrorPath(AshmemFdWorker* worker) {
    AshmemFdContainerScope scope(worker);
    assert(g_isUnmarshalThread && AshmemFdContainer::Instance().Matches(4,11));
    return;
}
int main() {
    auto& container=AshmemFdContainer::Instance();assert(container.Empty());
    AshmemFdWorker outer(4,11),nested(28,22);
    {
        AshmemFdContainerScope scope(&outer);
        assert(g_isUnmarshalThread && container.Matches(4,11));
        {
            AshmemFdContainerScope ordinary(nullptr);
            assert(g_isUnmarshalThread && !container.Matches(4,11));
            {
                AshmemFdContainerScope inner(&nested);
                assert(container.Matches(28,22));
            }
            assert(!container.Matches(4,11) && !container.Matches(28,22));
        }
        assert(container.Matches(4,11));
    }
    assert(container.Empty() && !g_isUnmarshalThread);
    ErrorPath(&outer);assert(container.Empty() && !g_isUnmarshalThread);
    container.Seed(52,33);AshmemFdContainer::SetIsUnmarshalThread(true);
    ErrorPath(&outer);assert(container.Matches(52,33) && g_isUnmarshalThread);
}
'''
        run_sanitized(PREFIX + RS.FD_SCOPE_HEADER + RS.FD_SCOPE_SOURCE + main)

    def test_producer_keeps_worker_but_task_thread_has_no_stale_tls_after_execution(self):
        main = r'''int main() {
    auto worker=std::make_shared<AshmemFdWorker>(4,11);
    auto& producer=AshmemFdContainer::Instance();producer.Seed(52,99);
    for(unsigned iteration=0;iteration<128;++iteration) {
        std::thread consumer([worker]() {
            auto& local=AshmemFdContainer::Instance();assert(local.Empty() && !g_isUnmarshalThread);
            { AshmemFdContainerScope scope(worker.get());assert(local.Matches(4,11)); }
            assert(local.Empty() && !g_isUnmarshalThread);
            { AshmemFdContainerScope next(nullptr);assert(local.Empty()); }
            assert(local.Empty() && !g_isUnmarshalThread);
        });
        consumer.join();assert(producer.Matches(52,99) && !g_isUnmarshalThread);
    }
    worker.reset();assert(producer.Matches(52,99) && !g_isUnmarshalThread);
}
'''
        run_sanitized(PREFIX + RS.FD_SCOPE_HEADER + RS.FD_SCOPE_SOURCE + main)

    def test_permit_registered_before_publish_completes_once_even_with_producer_copy_or_cancel(self):
        main = r'''int main() {
    std::atomic<int> count{0};
    for(unsigned iteration=0;iteration<256;++iteration) {
        auto first=std::make_shared<NoWaitTaskPermit>(count);assert(count==1);
        // A wait task must not consume a different task's outstanding permit.
        { NoWaitTaskCompletion wait(nullptr); }assert(count==1);
        std::function<void()> task=[first]() { NoWaitTaskCompletion completion(first); };
        std::thread consumer(task);consumer.join();assert(count==0);
        task=nullptr;first.reset();assert(count==0);
        auto cancelled=std::make_shared<NoWaitTaskPermit>(count);assert(count==1);
        std::function<void()> queued=[cancelled]() { NoWaitTaskCompletion completion(cancelled); };
        cancelled.reset();assert(count==1);queued=nullptr;assert(count==0);
        auto failed=std::make_shared<NoWaitTaskPermit>(count);
        auto second=std::make_shared<NoWaitTaskPermit>(count);assert(count==2);
        { NoWaitTaskCompletion parseFailure(failed); }assert(count==1);
        // Concurrent completion/destruction remains idempotent.
        std::thread a([second]() { second->Complete(); });
        std::thread b([second]() { second->Complete(); });a.join();b.join();
        assert(count==0);failed.reset();second.reset();assert(count==0);
    }
}
'''
        run_sanitized(PREFIX + RS.NO_WAIT_PERMIT + main)

    def test_scope_and_counter_are_applied_at_the_actual_task_lifetime_boundaries(self):
        changes = dict(RS.REPLACEMENTS[RS.UNMARSHAL])
        publication = next(new for old, new in changes.items() if 'RSTaskMessage::RSTask task =' in old)
        self.assertLess(publication.index('make_shared<NoWaitTaskPermit>'),
                        publication.index('RSTaskMessage::RSTask task ='))
        self.assertIn('NoWaitTaskCompletion complete(noWaitPermit)', publication)
        self.assertEqual(changes['    if (!waitUnmarshalling) {\n        noNeedWaitTaskNum_++;\n    }\n'], '')
        cleanup = next(new for old, new in RS.REPLACEMENTS[RS.ASHMEM]
                       if 'AshmemFdContainer::Instance().Clear();' in old)
        self.assertEqual(cleanup, '')
        self.assertTrue(any('AshmemFdContainerScope fdScope(ashmemFdWorker.get());' in new
                            for _, new in RS.REPLACEMENTS[RS.UNMARSHAL]))


if __name__ == '__main__':
    unittest.main()
