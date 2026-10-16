// Execute the shipped input source over real Unix sockets with external values.
// The test explicitly authorizes the host UID; the product VDI authorizes UID 0.
#include "qemu_sensor_input.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <limits>
#include <mutex>
#include <random>
#include <stdexcept>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <vector>
using namespace OHOS::HDI::Sensor::Qemu;
using namespace std::chrono_literals;
#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (0)
struct Sink {
    std::mutex mutex;
    std::condition_variable cv;
    std::vector<Acceleration> samples;
    void Add(const Acceleration& value) { std::lock_guard<std::mutex> lock(mutex); samples.push_back(value); cv.notify_all(); }
    size_t Size() { std::lock_guard<std::mutex> lock(mutex); return samples.size(); }
    void Await(size_t count) { std::unique_lock<std::mutex> lock(mutex); CHECK(cv.wait_for(lock, 2s, [&] { return samples.size() >= count; })); }
};
bool Write(int fd, const uint8_t* data, size_t size)
{
    while (size) {
#ifdef MSG_NOSIGNAL
        auto count = send(fd, data, size, MSG_NOSIGNAL);
#else
        auto count = send(fd, data, size, 0);
#endif
        if (count <= 0) return false;
        data += count;
        size -= static_cast<size_t>(count);
    }
    return true;
}
int Connect(const std::string& path, Nonce& nonce, bool authorized = true)
{
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    CHECK(fd >= 0);
    timeval timeout{2, 0};
    CHECK(setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0);
    CHECK(setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) == 0);
#ifdef SO_NOSIGPIPE
    int enabled = 1;
    CHECK(setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &enabled, sizeof(enabled)) == 0);
#endif
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    CHECK(path.size() < sizeof(address.sun_path));
    std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
    CHECK(connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0);
    std::array<uint8_t, HELLO_SIZE> hello{};
    size_t offset = 0;
    while (offset < hello.size()) {
        auto count = recv(fd, hello.data() + offset, hello.size() - offset, 0);
        if (!authorized) { CHECK(count == 0 || (count < 0 && errno == ECONNRESET)); return fd; }
        CHECK(count > 0);
        offset += static_cast<size_t>(count);
    }
    CHECK(std::memcmp(hello.data(), "QSN1", 4) == 0);
    CHECK(ReadLe(hello.data() + 4, 4) == 1 && ReadLe(hello.data() + 24, 4) == 1);
    CHECK(ReadLe(hello.data() + 28, 4) == 0);
    std::memcpy(nonce.data(), hello.data() + 8, nonce.size());
    return fd;
}
Frame Encode(const Nonce& nonce, uint64_t sequence, float x, float y, float z)
{
    Frame frame{};
    std::memcpy(frame.data(), "QSF1", 4);
    WriteLe(frame.data() + 4, 1, 4);
    std::memcpy(frame.data() + 8, nonce.data(), nonce.size());
    WriteLe(frame.data() + 24, sequence, 8);
    const float values[]{x, y, z};
    for (size_t i = 0; i < 3; ++i) {
        uint32_t bits;
        std::memcpy(&bits, &values[i], 4);
        WriteLe(frame.data() + 32 + 4 * i, bits, 4);
    }
    return frame;
}
void Closed(int fd)
{
    uint8_t byte;
    auto count = recv(fd, &byte, 1, 0);
    CHECK(count == 0 || (count < 0 && errno == ECONNRESET));
}
int main(int argc, char** argv)
{
    try {
        CHECK(argc == 3);
        const std::string scenario(argv[1]), path(argv[2]);
        if (scenario == "callback_destroy") {
            Sink result;
            int identity = 0;
            auto heap = std::make_unique<SensorInput>(InputConfig{path, geteuid()});
            CHECK(heap->Start());
            CHECK(heap->Register(&identity, [&](const Acceleration& value) { heap.reset(); result.Add(value); }));
            CHECK(heap->Enable());
            Nonce nonce;
            int fd = Connect(path, nonce);
            auto frame = Encode(nonce, 1, 1.0F, 2.0F, 3.0F);
            CHECK(Write(fd, frame.data(), frame.size())); result.Await(1); close(fd);
            for (int i = 0; i < 200 && access(path.c_str(), F_OK) == 0; ++i) std::this_thread::sleep_for(5ms);
            CHECK(!heap && access(path.c_str(), F_OK) != 0);
            std::cout << scenario << ": pass\n";
            return 0;
        }
        SensorInput input({path, static_cast<uid_t>(geteuid() + (scenario == "unauthorized" ? 1 : 0))});
        Sink sink;
        int owner = 0;
        if (scenario == "file_protection" || scenario == "symlink_protection") {
            std::ofstream(path + ".external") << "preserve";
            if (scenario == "file_protection") std::ofstream(path) << "preserve";
            else CHECK(symlink((path + ".external").c_str(), path.c_str()) == 0);
            CHECK(!input.Start());
            std::ifstream file(path); std::string text; file >> text; CHECK(text == "preserve");
            unlink(path.c_str()); unlink((path + ".external").c_str());
        } else {
            if (scenario == "stale_path") {
                int stale = socket(AF_UNIX, SOCK_STREAM, 0);
                sockaddr_un address{}; address.sun_family = AF_UNIX;
                std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
                CHECK(bind(stale, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0);
                close(stale);
            }
            CHECK(!input.Enable() && !input.SetBatch(MIN_INTERVAL_NS, 0));
            CHECK(input.Start() && input.IsRunning() && input.Start());
            struct stat metadata{};
            CHECK(lstat(path.c_str(), &metadata) == 0 && (metadata.st_mode & 0777) == 0600);
            CHECK(input.Register(&owner, [&](const Acceleration& value) { sink.Add(value); }));
            CHECK(input.SetBatch(MIN_INTERVAL_NS, 0) && !input.SetBatch(0, 0));
            CHECK(!input.SetBatch(MIN_INTERVAL_NS, -1) && !input.SetBatch(MAX_INTERVAL_NS + 1, 0));
            CHECK(input.Enable());
            std::this_thread::sleep_for(10ms);
            CHECK(sink.Size() == 0); // No source means no generated sensor readings.
            if (scenario == "external_controller") {
                std::cout << "READY\n" << std::flush;
                sink.Await(3);
                input.Disable();
                std::lock_guard<std::mutex> lock(sink.mutex);
                CHECK(sink.samples.size() == 3);
                for (const auto& value : sink.samples) {
                    std::cout << std::setprecision(9) << value.x << ' ' << value.y << ' '
                              << value.z << ' ' << value.timestamp << '\n';
                }
            } else if (scenario == "active_path_protection" || scenario == "stale_path") {
                if (scenario == "active_path_protection") {
                    SensorInput other({path, geteuid()});
                    CHECK(!other.Start());
                }
            } else if (scenario == "path_replacement") {
                CHECK(rename(path.c_str(), (path + ".moved").c_str()) == 0);
                std::ofstream(path) << "preserve";
                input.Stop();
                std::ifstream file(path); std::string text; file >> text; CHECK(text == "preserve");
                unlink(path.c_str()); unlink((path + ".moved").c_str());
            } else if (scenario == "callback_limit") {
                int identities[32]{};
                for (size_t i = 0; i < 31; ++i) CHECK(input.Register(&identities[i], [](const Acceleration&) {}));
                CHECK(!input.Register(&identities[31], [](const Acceleration&) {}));
            } else if (scenario == "unauthorized") {
                Nonce nonce;
                int fd = Connect(path, nonce, false);
                close(fd);
                CHECK(sink.Size() == 0);
            } else if (scenario == "callback_reentry") {
                CHECK(input.Unregister(&owner));
                CHECK(input.Register(&owner, [&](const Acceleration& value) {
                    CHECK(input.Disable());
                    CHECK(input.Unregister(&owner));
                    sink.Add(value);
                }));
                Nonce nonce;
                int fd = Connect(path, nonce);
                auto frame = Encode(nonce, 1, 1.25F, -2.5F, 3.75F);
                CHECK(Write(fd, frame.data(), frame.size()));
                sink.Await(1);
                Closed(fd); close(fd);
                CHECK(input.Register(&owner, [&](const Acceleration& value) { sink.Add(value); }));
                CHECK(input.Enable());
                fd = Connect(path, nonce);
                frame = Encode(nonce, 1, -4.0F, 5.0F, -6.0F);
                CHECK(Write(fd, frame.data(), frame.size())); sink.Await(2); close(fd);
            } else if (scenario == "disable_backpressure") {
                CHECK(input.Unregister(&owner));
                std::mutex mutex;
                std::condition_variable cv;
                bool entered = false, release = false;
                CHECK(input.Register(&owner, [&](const Acceleration& value) {
                    { std::unique_lock<std::mutex> lock(mutex); entered = true; cv.notify_all(); cv.wait(lock, [&] { return release; }); }
                    sink.Add(value);
                }));
                Nonce nonce;
                int fd = Connect(path, nonce);
                auto frame = Encode(nonce, 1, 1.0F, 2.0F, 3.0F);
                CHECK(Write(fd, frame.data(), frame.size()));
                { std::unique_lock<std::mutex> lock(mutex); CHECK(cv.wait_for(lock, 2s, [&] { return entered; })); }
                CHECK(fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK) == 0);
                size_t bytes = 0;
                for (uint64_t sequence = 2; bytes < 1024 * 1024; ++sequence) {
                    frame = Encode(nonce, sequence, 40.0F, 50.0F, 60.0F);
                    auto count = send(fd, frame.data(), frame.size(), 0);
                    if (count < 0) { CHECK(errno == EAGAIN || errno == EWOULDBLOCK); break; }
                    bytes += static_cast<size_t>(count);
                }
                CHECK(bytes < 1024 * 1024); // Kernel backpressure; no unbounded driver queue.
                std::atomic<bool> done{false};
                std::thread disabling([&] { CHECK(input.Disable()); done = true; });
                std::this_thread::sleep_for(20ms); CHECK(!done);
                { std::lock_guard<std::mutex> lock(mutex); release = true; cv.notify_all(); }
                disabling.join();
                CHECK(done && sink.Size() == 1);
                close(fd);
                CHECK(input.Enable());
                fd = Connect(path, nonce);
                frame = Encode(nonce, 1, -10.0F, -20.0F, -30.0F);
                CHECK(Write(fd, frame.data(), frame.size())); sink.Await(2);
                CHECK(sink.samples.back().x == -10.0F && sink.Size() == 2); close(fd);
            } else {
                Nonce nonce;
                int fd = Connect(path, nonce);
                Frame frame = Encode(nonce, 1, 1.0F, 2.0F, 3.0F);
                if (scenario == "roundtrip" || scenario == "fragmented" || scenario == "range_edges" ||
                    scenario == "duplicate_register" || scenario == "sampling_limit") {
                    if (scenario == "duplicate_register") {
                        CHECK(input.Register(&owner, [](const Acceleration&) { throw std::runtime_error("duplicate replaced callback"); }));
                    }
                    if (scenario == "sampling_limit") CHECK(input.SetBatch(100000000, 100000000));
                    std::mt19937 random(std::random_device{}());
                    std::uniform_real_distribution<float> value(-100.0F, 100.0F);
                    float x = value(random), y = value(random), z = value(random);
                    if (scenario == "range_edges") { x = MAX_ACCELERATION; y = -MAX_ACCELERATION; z = -0.0F; }
                    frame = Encode(nonce, 1, x, y, z);
                    if (scenario == "fragmented") {
                        for (size_t i = 0; i < frame.size(); ++i) CHECK(Write(fd, frame.data() + i, 1));
                    } else CHECK(Write(fd, frame.data(), frame.size()));
                    sink.Await(1);
                    CHECK(sink.samples[0].x == x && sink.samples[0].y == y && sink.samples[0].z == z);
                    CHECK(sink.samples[0].timestamp > 0);
                    if (scenario == "sampling_limit") {
                        frame = Encode(nonce, 2, 150.0F, 150.0F, 150.0F);
                        CHECK(Write(fd, frame.data(), frame.size()));
                        std::this_thread::sleep_for(30ms); CHECK(sink.Size() == 1);
                        std::this_thread::sleep_for(100ms);
                    }
                    std::this_thread::sleep_for(3ms);
                    frame = Encode(nonce, scenario == "sampling_limit" ? 3 : 2, -x, -y, -z);
                    CHECK(Write(fd, frame.data(), frame.size())); sink.Await(2);
                    CHECK(sink.samples[1].timestamp > sink.samples[0].timestamp);
                } else if (scenario == "disconnect_replay" || scenario == "disable_replay") {
                    const Nonce old = nonce;
                    if (scenario == "disable_replay") { CHECK(input.Disable()); CHECK(input.Enable()); }
                    close(fd);
                    fd = Connect(path, nonce);
                    CHECK(nonce != old);
                    frame = Encode(old, 1, 1.0F, 2.0F, 3.0F);
                    CHECK(Write(fd, frame.data(), frame.size())); Closed(fd); close(fd);
                    CHECK(sink.Size() == 0);
                    fd = Connect(path, nonce);
                    frame = Encode(nonce, 1, 7.0F, 8.0F, 9.0F);
                    CHECK(Write(fd, frame.data(), frame.size())); sink.Await(1);
                } else {
                    if (scenario == "wrong_nonce") frame[8] ^= 1;
                    else if (scenario == "wrong_magic") frame[0] ^= 1;
                    else if (scenario == "wrong_version") frame[4] = 2;
                    else if (scenario == "zero_sequence") WriteLe(frame.data() + 24, 0, 8);
                    else if (scenario == "nan") frame = Encode(nonce, 1, std::numeric_limits<float>::quiet_NaN(), 0, 0);
                    else if (scenario == "infinity") frame = Encode(nonce, 1, 0, std::numeric_limits<float>::infinity(), 0);
                    else if (scenario == "out_of_range") frame = Encode(nonce, 1, MAX_ACCELERATION + 1, 0, 0);
                    else if (scenario == "repeated_sequence") {
                        CHECK(Write(fd, frame.data(), frame.size())); sink.Await(1);
                    } else if (scenario != "short_frame") throw std::runtime_error("unknown scenario");
                    if (scenario == "short_frame") {
                        CHECK(Write(fd, frame.data(), 10)); shutdown(fd, SHUT_WR);
                    } else CHECK(Write(fd, frame.data(), frame.size()));
                    Closed(fd);
                    CHECK(sink.Size() == (scenario == "repeated_sequence" ? 1U : 0U));
                }
                close(fd);
            }
            input.Stop();
            CHECK(!input.IsRunning() && access(path.c_str(), F_OK) != 0);
            CHECK(input.Start()); input.Stop(); // Listener lifecycle can be recreated.
        }
        std::cout << scenario << ": pass\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << argv[1] << ": " << error.what() << '\n';
        return 1;
    }
}
