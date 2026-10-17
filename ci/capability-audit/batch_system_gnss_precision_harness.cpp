// Pending root native validation; not compiled/executed by the staging agent.
// Reuse unchanged V1 setup/Unix helpers and the actual shipped Provider class.
#define main ExistingV1GnssHarnessMain
#include "batch_system_gnss_harness.cpp"
#undef main

namespace {
std::mutex precisionMutex;
std::vector<uint32_t> precisionWords;
void CapturePrecision(V::GnssLocation* value)
{
    uint32_t word = 0;
    static_assert(sizeof(value->horizontalAccuracy) == sizeof(word));
    std::memcpy(&word, &value->horizontalAccuracy, sizeof(word));
    { std::lock_guard<std::mutex> lock(precisionMutex); precisionWords.push_back(word); }
    current->Add(value);
}
Frame Probe(const Nonce& nonce)
{
    Frame frame{};
    std::memcpy(frame.data(), "QGP2", 4); WriteLe(frame.data() + 4, 2, 4);
    std::memcpy(frame.data() + 8, nonce.data(), nonce.size());
    return frame;
}
void PrecisionReady(int fd, const Nonce& nonce)
{
    auto probe = Probe(nonce);
    CHECK(Write(fd, probe.data(), probe.size()));
    std::array<uint8_t, HELLO_SIZE> ack{};
    size_t done = 0;
    while (done < ack.size()) {
        auto count = recv(fd, ack.data() + done, ack.size() - done, 0);
        CHECK(count > 0); done += static_cast<size_t>(count);
    }
    CHECK(std::memcmp(ack.data(), "QGA2", 4) == 0 && ReadLe(ack.data() + 4, 4) == 2);
    CHECK(std::memcmp(ack.data() + 8, nonce.data(), nonce.size()) == 0);
    CHECK(ReadLe(ack.data() + 24, 4) == FRAME_SIZE && ReadLe(ack.data() + 28, 4) == 1);
}
Frame Precision(const Nonce& nonce, uint64_t sequence = 1, uint32_t word = 0, bool valid = false)
{
    auto frame = Encode(nonce, sequence);
    std::memcpy(frame.data(), "QGF2", 4); WriteLe(frame.data() + 4, 2, 4);
    WriteLe(frame.data() + 64, word, 4); WriteLe(frame.data() + 84, valid ? 1 : 0, 4);
    return frame;
}
} // namespace

int main(int argc, char** argv)
{
    try {
        CHECK(argc == 3);
        const std::string scenario = argv[1], path = argv[2];
        Sink sink; current = &sink;
        Provider provider({path, geteuid()});
        auto callbacks = Callbacks(); callbacks.gnssCallback.locationUpdate = CapturePrecision;
        CHECK(provider.Enable(&callbacks) == 0 && provider.Start(1) == 0);
        Nonce nonce; int fd = Connect(path, nonce);
        if (scenario == "bits") {
            PrecisionReady(fd, nonce);
            const uint32_t words[] = {0x00000000u, 0x80000000u, 0x3f800000u, 0xbf800000u,
                0x7f800000u, 0xff800000u, 0x7fc01234u, 0xffc05678u, 0x7f800001u,
                0x00000001u, 0x7f7fffffu, 0x80000001u};
            size_t ordinal = 0;
            for (uint32_t word : words) for (bool valid : {false, true}) {
                auto frame = Precision(nonce, ordinal + 1, word, valid);
                CHECK(Write(fd, frame.data(), frame.size())); sink.Await(++ordinal);
                { std::lock_guard<std::mutex> lock(precisionMutex); CHECK(precisionWords.back() == word); }
                { std::lock_guard<std::mutex> lock(sink.mutex);
                    CHECK(sink.values.back().fieldValidity == (1u | 2u | 512u | 1024u | (valid ? 32u : 0u)));
                    CHECK(sink.values.back().timeSinceBoot > 0);
                }
            }
        } else if (scenario == "v2_before_probe") {
            auto frame = Precision(nonce); CHECK(Write(fd, frame.data(), frame.size())); Closed(fd);
            CHECK(sink.Size() == 0);
        } else if (scenario == "bad_probe_version" || scenario == "bad_probe_nonce" || scenario == "bad_probe_payload") {
            auto frame = Probe(nonce);
            if (scenario == "bad_probe_version") WriteLe(frame.data() + 4, 3, 4);
            if (scenario == "bad_probe_nonce") frame[8] ^= 1;
            if (scenario == "bad_probe_payload") frame[24] = 1;
            CHECK(Write(fd, frame.data(), frame.size())); Closed(fd); CHECK(sink.Size() == 0);
        } else if (scenario == "probe_after_v1") {
            auto frame = Encode(nonce); CHECK(Write(fd, frame.data(), frame.size())); sink.Await(1);
            frame = Probe(nonce); CHECK(Write(fd, frame.data(), frame.size())); Closed(fd); CHECK(sink.Size() == 1);
        } else {
            PrecisionReady(fd, nonce);
            auto frame = Precision(nonce);
            size_t expected = 0;
            if (scenario == "v1_after_v2") frame = Encode(nonce);
            else if (scenario == "duplicate_probe") frame = Probe(nonce);
            else if (scenario == "bad_v2_version") WriteLe(frame.data() + 4, 3, 4);
            else if (scenario == "bad_v2_nonce") frame[8] ^= 1;
            else if (scenario == "unknown_precision_flags") WriteLe(frame.data() + 84, 2, 4);
            else if (scenario == "unknown_optional_flags") WriteLe(frame.data() + 80, 32, 4);
            else if (scenario == "zero_sequence") WriteLe(frame.data() + 24, 0, 8);
            else if (scenario == "repeat_sequence" || scenario == "repeat_utc") {
                CHECK(Write(fd, frame.data(), frame.size())); sink.Await(1); expected = 1;
                if (scenario == "repeat_utc") WriteLe(frame.data() + 24, 2, 8);
            } else if (scenario == "stale_utc") WriteLe(frame.data() + 32, UtcMs() - 11000, 8);
            else if (scenario == "future_utc") WriteLe(frame.data() + 32, UtcMs() + 2000, 8);
            else if (scenario == "latitude") Number(frame.data() + 40, 90.0001);
            else if (scenario == "longitude") Number(frame.data() + 48, -180.0001);
            else if (scenario == "other_nonfinite") Number(frame.data() + 56, std::numeric_limits<double>::infinity());
            else if (scenario == "stop_reconnect_old_nonce") {
                CHECK(Write(fd, frame.data(), frame.size())); sink.Await(1);
                CHECK(provider.Stop(1) == 0); Closed(fd); close(fd);
                CHECK(provider.Start(1) == 0); Nonce next; fd = Connect(path, next); CHECK(next != nonce);
                frame = Probe(nonce); CHECK(Write(fd, frame.data(), frame.size())); Closed(fd);
                CHECK(sink.Size() == 1); provider.Disable(); close(fd); return 0;
            } else throw std::runtime_error("unknown native precision scenario");
            CHECK(Write(fd, frame.data(), frame.size())); Closed(fd); CHECK(sink.Size() == expected);
        }
        CHECK(provider.Disable() == 0); close(fd);
        std::cout << "HOST_NATIVE_ONLY " << scenario << " passed; no HDI/business/package closure\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
