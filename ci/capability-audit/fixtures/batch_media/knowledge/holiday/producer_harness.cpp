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
#define open TestOpen
#define fstat TestFstat
#define read TestRead
// ACTUAL_PRODUCER
#undef open
#undef fstat
#undef read
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
 std::this_thread::sleep_for(std::chrono::milliseconds(30));assert(!stopped);
 weak=store;store.reset();assert(!weak.expired());
 {std::lock_guard<std::mutex> lock(mutex);release=true;}wake.notify_all();
 stopper.join();assert(stopped);assert(weak.expired());
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
