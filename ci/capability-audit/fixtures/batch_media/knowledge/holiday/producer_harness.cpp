#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cassert>
#include <fstream>
#include <iostream>
#include <sstream>
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <chrono>
#include <pthread.h>
#include <set>
static int TestOpen(const char *path,int flags)
{
 assert(std::strcmp(path,"/system/etc/knowledge-content")==0);
 const char *redirect=std::getenv("BATCH_MEDIA_TEST_RESOURCE_DIRECTORY");assert(redirect);
 if(std::getenv("BATCH_MEDIA_TEST_DIRECTORY_EACCES")){errno=EACCES;return -1;}
 return ::open(redirect,flags);
}
static int TestFstat(int fd,struct stat *info)
{
 int result=::fstat(fd,info);
 if(result==0){info->st_uid=std::getenv("BATCH_MEDIA_TEST_BAD_OWNER")?501:0;}
 return result;
}
static ssize_t TestRead(int fd,void *bytes,size_t length)
{
 if(std::getenv("BATCH_MEDIA_TEST_READ_EIO")){errno=EIO;return -1;}
 ssize_t result=::read(fd,bytes,length);
 if(result>0&&std::getenv("BATCH_MEDIA_TEST_CHANGE_DURING_READ")) {
  struct stat info{};assert(::fstat(fd,&info)==0);
#if defined(__APPLE__)
  timespec times[2]={info.st_atimespec,info.st_mtimespec};
#else
  timespec times[2]={info.st_atim,info.st_mtim};
#endif
  times[1].tv_nsec=(times[1].tv_nsec+1)%1000000000;assert(futimens(fd,times)==0);
 }
 return result;
}
// Only the actual producer's pthread calls are redirected. Failures are true
// return-code callouts; the host's own control threads keep real pthread calls.
static std::atomic<int> failMutexInit{0},failConditionInit{0},failCreate{0},failJoin{0},failWait{0},failCancelWake{0},failJoinNotify{0};
static std::atomic<int> loggedErrors{0},detachCalls{0};
static std::mutex resourceMutex;
static std::set<pthread_mutex_t*> liveMutexes;
static std::set<pthread_cond_t*> liveConditions;
static void TestMediaLog(const char *format,...) {(void)format;++loggedErrors;}
static int TestMutexInit(pthread_mutex_t *mutex,const pthread_mutexattr_t *attributes)
{
 if(failMutexInit.exchange(0))return ENOMEM;
 const int result=::pthread_mutex_init(mutex,attributes);
 if(result==0){std::lock_guard<std::mutex> lock(resourceMutex);assert(liveMutexes.insert(mutex).second);}
 return result;
}
static int TestMutexDestroy(pthread_mutex_t *mutex)
{
 const int result=::pthread_mutex_destroy(mutex);
 if(result==0){std::lock_guard<std::mutex> lock(resourceMutex);liveMutexes.erase(mutex);}
 return result;
}
static int TestConditionInit(pthread_cond_t *condition,const pthread_condattr_t *attributes)
{
 if(failConditionInit.exchange(0))return ENOMEM;
 const int result=::pthread_cond_init(condition,attributes);
 if(result==0){std::lock_guard<std::mutex> lock(resourceMutex);assert(liveConditions.insert(condition).second);}
 return result;
}
static int TestConditionDestroy(pthread_cond_t *condition)
{
 const int result=::pthread_cond_destroy(condition);
 if(result==0){std::lock_guard<std::mutex> lock(resourceMutex);liveConditions.erase(condition);}
 return result;
}
static int TestThreadCreate(pthread_t *thread,const pthread_attr_t *attributes,void *(*entry)(void*),void *argument)
{
 if(failCreate.exchange(0))return EAGAIN;
 return ::pthread_create(thread,attributes,entry,argument);
}
static int TestThreadJoin(pthread_t thread,void **result)
{
 if(failJoin.exchange(0))return EINVAL;
 return ::pthread_join(thread,result);
}
static int TestThreadDetach(pthread_t thread) {++detachCalls;return ::pthread_detach(thread);}
static int TestConditionWait(pthread_cond_t *condition,pthread_mutex_t *mutex,const timespec *deadline)
{
 if(failWait.exchange(0))return EINVAL;
 return ::pthread_cond_timedwait(condition,mutex,deadline);
}
static int TestConditionBroadcast(pthread_cond_t *condition)
{
 {std::lock_guard<std::mutex> lock(resourceMutex);
  if(liveConditions.count(condition)) {if(failCancelWake.exchange(0))return EINVAL;}
  else if(failJoinNotify.exchange(0))return EINVAL;
 }
 return ::pthread_cond_broadcast(condition);
}
#define pthread_cond_broadcast TestConditionBroadcast
#define pthread_mutex_init TestMutexInit
#define pthread_mutex_destroy TestMutexDestroy
#define pthread_cond_init TestConditionInit
#define pthread_cond_destroy TestConditionDestroy
#define pthread_create TestThreadCreate
#define pthread_join TestThreadJoin
#define pthread_detach TestThreadDetach
#define pthread_cond_timedwait TestConditionWait
#define open TestOpen
#define fstat TestFstat
#define read TestRead
// ACTUAL_PRODUCER
#undef open
#undef fstat
#undef read
#undef pthread_cond_broadcast
#undef pthread_mutex_init
#undef pthread_mutex_destroy
#undef pthread_cond_init
#undef pthread_cond_destroy
#undef pthread_create
#undef pthread_join
#undef pthread_detach
#undef pthread_cond_timedwait
static void AssertReleased()
{
 std::lock_guard<std::mutex> lock(resourceMutex);assert(liveMutexes.empty()&&liveConditions.empty());
}
static bool WaitUntil(const std::function<bool()> &predicate,int milliseconds=7000)
{
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(milliseconds);
 while(!predicate()&&std::chrono::steady_clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(10));
 return predicate();
}
static int ObserverFailureTests(const char *path)
{
 using OHOS::Media::KnowledgeHolidayIndex;
 using OHOS::NativeRdb::RdbStore;
 auto store=std::make_shared<RdbStore>(path);
 assert(KnowledgeHolidayIndex::Refresh(*store)==0);
 // Each failed stage must release initialized resources and permit a real retry.
 for(auto *failure:{&failMutexInit,&failConditionInit,&failCreate}) {
  failure->store(1);assert(KnowledgeHolidayIndex::Observe(store)!=0);AssertReleased();
  assert(KnowledgeHolidayIndex::StopObserver()==0);
  assert(KnowledgeHolidayIndex::Observe(store)==0);assert(KnowledgeHolidayIndex::StopObserver()==0);AssertReleased();
 }
 assert(KnowledgeHolidayIndex::Observe(store)==0);failJoin=1;
 assert(KnowledgeHolidayIndex::StopObserver()!=0);
 // Join failure cannot falsely mark the generation reaped. Retry owns that join.
 assert(KnowledgeHolidayIndex::StopObserver()==0);AssertReleased();
 for(auto *failure:{&failCancelWake,&failJoinNotify}) {
  assert(KnowledgeHolidayIndex::Observe(store)==0);failure->store(1);
  assert(KnowledgeHolidayIndex::StopObserver()!=0);
  assert(KnowledgeHolidayIndex::StopObserver()==0);AssertReleased();
 }
 int errors=loggedErrors.load();failWait=1;
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 assert(WaitUntil([&]{return loggedErrors.load()>errors;}));
 assert(KnowledgeHolidayIndex::StopObserver()==0);AssertReleased();
 // Real transaction return failure is logged, rolled back and retried by poller.
 std::atomic<int> attempts{0};
 OHOS::NativeRdb::testTransactionCallout=[&](const std::string &sql) {if(sql=="DELETE FROM KnowledgeHoliday")++attempts;};
 assert(setenv("BATCH_MEDIA_TEST_FAIL_STATEMENT","5",1)==0);errors=loggedErrors.load();
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 assert(WaitUntil([&]{return loggedErrors.load()>errors;}));assert(attempts==1);
 assert(unsetenv("BATCH_MEDIA_TEST_FAIL_STATEMENT")==0);
 assert(WaitUntil([&]{return attempts.load()>=2;}));
 assert(KnowledgeHolidayIndex::StopObserver()==0);AssertReleased();
 sqlite3_stmt *rows=nullptr;assert(sqlite3_prepare_v2(store->db,"SELECT COUNT(*) FROM KnowledgeHoliday",-1,&rows,nullptr)==SQLITE_OK);
 assert(sqlite3_step(rows)==SQLITE_ROW&&sqlite3_column_int(rows,0)==2);assert(sqlite3_finalize(rows)==SQLITE_OK);
 // Destruction from its own RDB callback detaches only the independent state.
 auto local=std::make_unique<OHOS::Media::ObserverOwner>();std::atomic<bool> destroyed{false};
 std::weak_ptr<RdbStore> weak=store;const int previousDetach=detachCalls;
 OHOS::NativeRdb::testTransactionCallout=[&](const std::string &sql) {
  if(sql=="DELETE FROM KnowledgeHoliday") {local.reset();destroyed=true;}
 };
 assert(local->Start(store)==0);assert(WaitUntil([&]{return destroyed.load();}));
 store.reset();assert(WaitUntil([&]{return weak.expired();}));
 assert(WaitUntil([&]{std::lock_guard<std::mutex> lock(resourceMutex);return liveMutexes.empty()&&liveConditions.empty();}));
 assert(detachCalls==previousDetach+1);OHOS::NativeRdb::testTransactionCallout={};AssertReleased();
 std::cout<<"actual -fno-exceptions pthread producer: init/create/join/wait/wake/notification failures, retry, weak DB, rollback and callback-owned destruction passed\n";
 return 0;
}
static int ObserverTests(const char *path)
{
 using OHOS::Media::KnowledgeHolidayIndex;
 using OHOS::NativeRdb::RdbStore;
 auto store=std::make_shared<RdbStore>(path);
 assert(KnowledgeHolidayIndex::Refresh(*store)==0);
 assert(KnowledgeHolidayIndex::Observe(nullptr)!=0);
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 const auto before=std::chrono::steady_clock::now();
 assert(KnowledgeHolidayIndex::StopObserver()==0);
 assert(std::chrono::steady_clock::now()-before<std::chrono::milliseconds(500));
 // Reopen cancels and joins the preceding generation before publishing the next.
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 std::weak_ptr<RdbStore> weak=store;store.reset();assert(weak.expired());
 assert(KnowledgeHolidayIndex::StopObserver()==0);
 store=std::make_shared<RdbStore>(path);
 std::mutex mutex;std::condition_variable wake;bool inside=false,release=false;
 std::atomic<bool> stopped{false};
 OHOS::NativeRdb::testTransactionCallout=[&](const std::string &sql) {
  if(sql!="DELETE FROM KnowledgeHoliday")return;
  std::unique_lock<std::mutex> lock(mutex);inside=true;wake.notify_all();
  wake.wait(lock,[&]{return release;});
  lock.unlock();assert(KnowledgeHolidayIndex::StopObserver()!=0);
 };
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 {std::unique_lock<std::mutex> lock(mutex);assert(wake.wait_for(lock,std::chrono::seconds(7),[&]{return inside;}));}
 std::thread stopper([&]{assert(KnowledgeHolidayIndex::StopObserver()==0);stopped=true;});
 std::atomic<bool> alsoStopped{false};
 std::thread otherStopper([&]{assert(KnowledgeHolidayIndex::StopObserver()==0);alsoStopped=true;});
 std::this_thread::sleep_for(std::chrono::milliseconds(30));assert(!stopped&&!alsoStopped);
 weak=store;store.reset();assert(!weak.expired());
 {std::lock_guard<std::mutex> lock(mutex);release=true;}wake.notify_all();
 stopper.join();otherStopper.join();assert(stopped&&alsoStopped);assert(weak.expired());
 // A reentrant native callout cancels without joining/destroying its own thread.
 store=std::make_shared<RdbStore>(path);std::atomic<bool> reentered{false};
 OHOS::NativeRdb::testTransactionCallout=[&](const std::string &sql) {
  if(sql=="DELETE FROM KnowledgeHoliday") {assert(KnowledgeHolidayIndex::StopObserver()!=0);reentered=true;}
 };
 assert(KnowledgeHolidayIndex::Observe(store)==0);
 const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(7);
 while(!reentered&&std::chrono::steady_clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(10));
 assert(reentered);assert(KnowledgeHolidayIndex::StopObserver()==0);
 OHOS::NativeRdb::testTransactionCallout={};
 // Reopening after reentrant shutdown remains usable.
 assert(KnowledgeHolidayIndex::Observe(store)==0);assert(KnowledgeHolidayIndex::StopObserver()==0);
 return 0;
}
int main(int argc,char **argv)
{
 assert(argc==3);
 if(std::string(argv[2])=="observer-tests")return ObserverTests(argv[1]);
 if(std::string(argv[2])=="observer-failure-tests")return ObserverFailureTests(argv[1]);
 OHOS::NativeRdb::RdbStore store(argv[1]);
 const int status=OHOS::Media::KnowledgeHolidayIndex::Refresh(store);
 std::cout<<"producer_status="<<status<<"\n";
 if(std::string(argv[2])=="trust-tests") {
  struct stat info{};info.st_mode=S_IFREG|0644;info.st_uid=0;assert(OHOS::Media::Trusted(info,false));
  info.st_uid=1000;assert(OHOS::Media::Trusted(info,false));info.st_uid=501;assert(!OHOS::Media::Trusted(info,false));
  info.st_uid=0;info.st_mode=S_IFREG|0666;assert(!OHOS::Media::Trusted(info,false));info.st_mode=S_IFLNK|0644;assert(!OHOS::Media::Trusted(info,false));
 }
 return status==OHOS::NativeRdb::E_OK?0:1;
}
