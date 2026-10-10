"""Actual patched snapshot/publication bodies with explicit host worker doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/commonlibrary/ets_utils/thread_info_snapshot'
PATCH = COMPONENT / '0001-publish-only-initialized-taskpool-thread-snapshots.patch'


def repaired_hunks():
    hunks, current = [], None
    for line in PATCH.read_text().splitlines():
        if line.startswith('@@ '):
            current = []
            hunks.append(current)
        elif line.startswith('diff --git'):
            current = None
        elif current is not None and line[:1] in (' ', '+') and not line.startswith('+++'):
            current.append(line[1:])
    return ['\n'.join(lines) + '\n' for lines in hunks]


class TaskpoolThreadInfoTests(unittest.TestCase):
    def test_publication_and_snapshot_use_matching_synchronization(self):
        snapshot, publish, header = repaired_hunks()
        self.assertIn('threadInfoReady_.load(std::memory_order_acquire)', snapshot)
        self.assertIn('threadInfoReady_.store(true, std::memory_order_release)', publish)
        self.assertIn('std::atomic<bool> threadInfoReady_ {false}', header)
        self.assertIn('std::atomic<Priority> priority_', header)
        self.assertNotIn('workerEnv_', snapshot)
        self.assertLess(snapshot.index('currentTaskIdMutex_'), snapshot.index('for (auto& id'))
        self.assertIn('workersMutex_', snapshot)

    def test_actual_snapshot_body_pending_ready_live_mutation_and_idle(self):
        snapshot, publish, header = repaired_hunks()
        fields = '\n'.join(line for line in header.splitlines() if any(value in line for value in (
            'priority_', 'threadInfoReady_', 'tid_', 'currentTaskId_', 'currentTaskIdMutex_')))
        harness = r'''#include <atomic>
#include <cassert>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_set>
#include <vector>
#include <sys/types.h>
enum class Priority { HIGH=0, DEFAULT=1, LOW=2, IDLE=3 };
struct Worker {
    void* workerEnv_ = nullptr; // explicit runtime double, not a NAPI engine
''' + fields + r'''
};
struct ThreadInfo { pid_t tid; Priority priority; std::vector<unsigned> currentTaskId; };
// Explicit host hash avoids coupling this snapshot-body test to the host
// toolchain's pointer-hash ABI. Production container/hash code is unchanged.
struct HostPointerHash {
    size_t operator()(const std::unique_ptr<ThreadInfo>& value) const noexcept {
        return reinterpret_cast<size_t>(value.get());
    }
};
using InfoSet=std::unordered_set<std::unique_ptr<ThreadInfo>, HostPointerHash>;
struct TaskManager {
    std::recursive_mutex workersMutex_;
    std::vector<Worker*> workers_;
    int expandingCount_=1;
    void NotifyWorkerIdle(Worker*) {} // scheduling is outside this host test
    void NotifyWorkerCreated(Worker*);
    InfoSet Snapshot() {
        InfoSet threadInfoSet;
''' + snapshot + r'''
        return threadInfoSet;
    }
};
''' + publish + r'''
int main() {
    Worker worker;
    TaskManager manager;
    manager.workers_.push_back(&worker);
    assert(manager.Snapshot().empty());
    worker.workerEnv_=reinterpret_cast<void*>(1);
    assert(manager.Snapshot().empty()); // formerly exposed tid=0 here
    worker.tid_=1234;
    assert(manager.Snapshot().empty()); // runtime startup not published yet
    manager.NotifyWorkerCreated(&worker);
    auto first=manager.Snapshot();
    assert(first.size()==1 && (*first.begin())->tid==1234);
    std::atomic<bool> done{false};
    std::thread writer([&] {
        for (unsigned i=1; i<10000; ++i) {
            worker.priority_=static_cast<Priority>(i%4);
            std::lock_guard<std::mutex> guard(worker.currentTaskIdMutex_);
            worker.currentTaskId_.clear();
            worker.currentTaskId_.push_back(i);
            worker.currentTaskId_.push_back(i+1);
        }
        done.store(true);
    });
    do {
        auto infos=manager.Snapshot();
        assert(infos.size()==1);
        const auto& info=**infos.begin();
        assert(info.tid==1234);
        assert(static_cast<int>(info.priority)>=0 && static_cast<int>(info.priority)<=3);
        assert(info.currentTaskId.empty() || (info.currentTaskId.size()==2 &&
               info.currentTaskId[1]==info.currentTaskId[0]+1));
    } while (!done.load());
    writer.join();
    { std::lock_guard<std::mutex> guard(worker.currentTaskIdMutex_); worker.currentTaskId_.clear(); }
    assert((*manager.Snapshot().begin())->currentTaskId.empty());
    worker.tid_=0; // malformed published double must not create a synthetic thread
    assert(manager.Snapshot().empty());
}
'''
        with tempfile.TemporaryDirectory(prefix='taskpool-thread-info-') as directory:
            source = Path(directory) / 'snapshot.cpp'
            binary = Path(directory) / 'snapshot'
            source.write_text(harness)
            compiled = subprocess.run(['clang++', '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=20)

    def test_shared_recipe_and_pinned_crlf_baseline(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${TASKPOOL_THREAD_INFO_COMPONENT_SCRIPT}" --source-root'), 1)
        self.assertIn('common/commonlibrary/ets_utils/thread_info_snapshot/apply.sh', recipe)
        baseline = (COMPONENT / 'verify_source.py').read_text()
        self.assertIn('37cafe4c6d96858e976107d41d4f723adfde4a61', baseline)
        self.assertIn('CRLF_FILES', baseline)
        self.assertIn('apply_exact_component.py', (COMPONENT / 'apply.sh').read_text())


if __name__ == '__main__':
    unittest.main()
