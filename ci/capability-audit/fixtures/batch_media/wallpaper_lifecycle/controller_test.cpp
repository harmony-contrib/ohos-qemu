/* Actual proposed controller with explicit host adapter doubles; NOT guest proof. */
#include "host_deps.h"
#include "qemu_wallpaper_renderer.h"
using namespace OHOS;
using namespace OHOS::WallpaperMgrService;
struct Fixture {
    std::shared_ptr<AppExecFwk::EventHandler> handler = std::make_shared<AppExecFwk::EventHandler>();
    std::shared_ptr<QemuWallpaperRenderer> renderer = QemuWallpaperRenderer::Create(handler);
    std::shared_ptr<AAFwk::AbilityManagerClient> client = AAFwk::AbilityManagerClient::GetInstance();
    Fixture() { client->Reset(); AccountSA::OsAccountManager::users = {100}; AccountSA::OsAccountManager::error = 0; }
    ~Fixture() { renderer->Stop(); handler->Drain(); client->Reset(); }
    sptr<IRemoteObject> Complete() {
        sptr<IRemoteObject> remote = new IRemoteObject;
        client->calls.back().connection->OnAbilityConnectDone({}, remote, 0);
        int steps=0;
        while (!handler->queue.empty()) {
            auto next=std::min_element(handler->queue.begin(),handler->queue.end(),[](const auto&a,const auto&b){return a.due<b.due;});
            if(next->due>handler->now) break;
            assert(++steps<40); assert(handler->Next());
        }
        return remote;
    }
};
int main() {
    { Fixture f;
      f.renderer->Request(100); for (int i=0;i<20;++i) f.renderer->Request(100);
      assert(f.handler->Next()); assert(f.client->calls.size()==1);
      for (int i=0;i<20;++i) f.renderer->Request(100);
      auto remote=f.Complete(); assert(remote->deaths.size()==1); f.handler->Drain();
      f.renderer->Request(100); f.handler->Drain(); assert(f.client->calls.size()==1);
      remote->Kill(); f.handler->Drain(); assert(f.client->calls.size()>1); assert(f.client->calls.size()<=6);
    }
    { Fixture f; AccountSA::OsAccountManager::users.clear();
      f.renderer->Request(); f.handler->Drain(); assert(f.client->calls.empty());
      AccountSA::OsAccountManager::users={100}; f.renderer->Request(100); f.handler->Drain();
      assert(!f.client->calls.empty()); assert(f.client->calls.size()<=5);
      // ERR_OK from ConnectExtensionAbility without callback is NOT connected.
      auto count=f.client->calls.size(); f.renderer->Request(100); assert(f.handler->Next());
      assert(f.client->calls.size()==count+1);
    }
    for (int mode=0;mode<5;++mode) {
      Fixture f; f.renderer->Request(100); assert(f.handler->Next());
      sptr<IRemoteObject> remote=new IRemoteObject;
      if(mode==2) remote->dead=true;
      if(mode==3) remote->allowDeath=false;
      auto connection=f.client->calls.back().connection;
      connection->OnAbilityConnectDone(mode==4?AppExecFwk::ElementName("foreign.bundle"):AppExecFwk::ElementName(),
          mode==1?sptr<IRemoteObject>():remote,mode==0?-17:0);
      f.handler->Drain(); assert(f.client->calls.size()>1); assert(remote->deaths.empty());
    }
    { Fixture f; f.renderer->Request(100); assert(f.handler->Next());
      auto old=f.client->calls.back().connection;
      AccountSA::OsAccountManager::users={101}; f.renderer->Request(101);
      for(int i=0;f.client->calls.size()<2;++i){assert(i<10);assert(f.handler->Next());}
      assert(f.client->calls.back().user==101); auto current=f.Complete();
      sptr<IRemoteObject> late=new IRemoteObject; old->OnAbilityConnectDone({},late,0); f.handler->Drain();
      assert(late->deaths.empty()); assert(current->deaths.size()==1);
      auto count=f.client->calls.size(); f.renderer->Request(101); f.handler->Drain(); assert(f.client->calls.size()==count);
    }
    { Fixture f; f.renderer->Request(100); f.renderer->Stop(); f.handler->Drain();
      f.renderer->Request(100); f.handler->Drain(); assert(f.client->calls.empty());
    }
    { Fixture f; f.renderer->Request(100); assert(f.handler->Next()); auto old=f.client->calls.back().connection;
      f.renderer->Stop(); auto count=f.client->calls.size();
      sptr<IRemoteObject> late=new IRemoteObject; old->OnAbilityConnectDone({},late,0); f.handler->Drain();
      f.renderer->Request(100); f.handler->Drain(); assert(f.client->calls.size()==count); assert(late->deaths.empty());
    }
    { Fixture f; f.client->synchronous=true; f.renderer->Request(100); f.handler->Drain();
      assert(f.client->calls.size()==1); // inline callback queued without deadlock.
    }
    { Fixture f; f.renderer->Request(100); assert(f.handler->Next());
      AccountSA::OsAccountManager::users={101}; auto remote=f.Complete(); f.handler->Drain();
      assert(remote->deaths.empty()); // no stale foreground success.
    }
    { Fixture f;
      std::mutex mutex; std::condition_variable condition; bool entered=false, release=false;
      std::atomic<bool> stopping { false }, stopped { false };
      f.client->beforeConnect=[&]{std::unique_lock<std::mutex> lock(mutex); entered=true; condition.notify_all();
          condition.wait(lock,[&]{return release;});};
      f.renderer->Request(100);
      std::thread worker([&]{assert(f.handler->Next());});
      {std::unique_lock<std::mutex> lock(mutex);condition.wait(lock,[&]{return entered;});}
      std::thread stopper([&]{stopping=true;f.renderer->Stop();stopped=true;});
      while(!stopping.load()) std::this_thread::yield();
      assert(!stopped.load());
      {std::lock_guard<std::mutex> lock(mutex);release=true;} condition.notify_all();
      worker.join();stopper.join();assert(stopped.load());
      auto count=f.client->calls.size();f.handler->Drain();f.renderer->Request(100);f.handler->Drain();
      assert(f.client->calls.size()==count);
    }
    { Fixture f; f.handler->reject=true; f.renderer->Request(100); assert(f.client->calls.empty());
      f.handler->reject=false; f.renderer->Request(100); assert(f.handler->Next()); assert(f.client->calls.size()==1);
    }
}
