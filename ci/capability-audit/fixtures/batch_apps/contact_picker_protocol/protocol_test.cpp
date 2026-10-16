/* Host challenge test for the ACTUAL installed header. No device claim. */
#include "contact_picker_protocol.h"
#include <cassert>
#include <climits>
#include <iostream>
#include <thread>
#include <vector>

using OHOS::ContactsApi::ContactPickerProtocol;
using Json = nlohmann::json;
static int cases = 0;

static std::string Chunk(int start, int count)
{
    auto values = Json::array();
    for (int i = 0; i < count; ++i) {
        values.push_back({ {"id", start + i}, {"key", "key-" + std::to_string(start + i)},
            {"name", {{"fullName", "\"中\\文" + std::to_string(start + i)}}} });
    }
    return values.dump();
}

static void FailFrame(bool types, int index, int total, const std::string &data)
{
    ContactPickerProtocol protocol;
    assert(protocol.Receive(types, index, total, data));
    const auto result = protocol.Snapshot();
    assert(result.ready && result.code == ContactPickerProtocol::SYSTEM_ERROR && result.total == 0);
    assert(result.data == "[]");
    assert(!protocol.Finish(0));
    ++cases;
}

int main()
{
    {
        ContactPickerProtocol protocol;
        // Delivery order may differ; indices still determine stable array order.
        assert(!protocol.Receive(true, 2, 205, Chunk(200, 5)));
        assert(!protocol.Receive(true, 0, 205, Chunk(0, 100)));
        assert(!protocol.Receive(true, 1, 205, Chunk(100, 100)));
        assert(protocol.Finish(0));
        auto result = protocol.Snapshot();
        auto all = Json::parse(result.data);
        assert(result.code == 0 && result.total == 205 && all.size() == 205);
        for (int i = 0; i < 205; ++i) { assert(all[i]["id"] == i); }
        assert(!protocol.Receive(true, INT_MAX, INT_MAX, "bad"));
        assert(!protocol.Finish(401) && !protocol.Fail());
        assert(protocol.Snapshot().data == result.data);
        ++cases;
    }
    for (int total : {0, 1, 99, 100, 101, 10000}) {
        ContactPickerProtocol protocol;
        int frames = std::max(1, (total + 99) / 100);
        for (int index = 0; index < frames; ++index) {
            assert(!protocol.Receive(true, index, total, Chunk(index * 100, std::min(100, total - index * 100))));
        }
        assert(protocol.Finish(0));
        assert(protocol.Snapshot().total == total && protocol.Snapshot().code == 0);
        ++cases;
    }
    {
        ContactPickerProtocol protocol;
        assert(protocol.Finish(1));
        auto result = protocol.Snapshot();
        assert(result.code == 1 && result.total == 0 && result.data == "[]");
        ++cases;
    }
    {
        // Cancel with defaults is a real code=0 result, not converted to [].
        ContactPickerProtocol protocol;
        assert(!protocol.Receive(true, 0, 3, Chunk(500, 3)));
        assert(protocol.Finish(0));
        assert(Json::parse(protocol.Snapshot().data)[0]["id"] == 500);
        ++cases;
    }
    FailFrame(false, 0, 1, Chunk(0, 1));
    for (int index : {-1, 100, INT_MAX, INT_MIN}) { FailFrame(true, index, 1, Chunk(0, 1)); }
    for (int total : {-1, 10001, INT_MAX, INT_MIN}) { FailFrame(true, 0, total, "[]"); }
    for (const auto &json : {"", "{", "{}", "null", "[null]", "[[]]", "[1]", "[true]", "[{}] trailing"}) {
        FailFrame(true, 0, 1, json);
    }
    FailFrame(true, 1, 1, Chunk(0, 1));
    FailFrame(true, 0, 101, Chunk(0, 99));
    FailFrame(true, 1, 101, Chunk(100, 2));
    FailFrame(true, 0, 0, "[{}]");
    FailFrame(true, 0, 1, std::string(65, '[') + "{}" + std::string(65, ']'));
    FailFrame(true, 0, 1, "[{}]" + std::string(ContactPickerProtocol::MAX_FRAME_BYTES, ' '));
    {
        ContactPickerProtocol protocol;
        assert(!protocol.Receive(true, 0, 101, Chunk(0, 100)));
        assert(protocol.Receive(true, 0, 101, Chunk(0, 100)));
        assert(protocol.Snapshot().code == ContactPickerProtocol::SYSTEM_ERROR);
        ++cases;
    }
    {
        ContactPickerProtocol protocol;
        assert(!protocol.Receive(true, 0, 101, Chunk(0, 100)));
        assert(protocol.Receive(true, 1, 102, Chunk(100, 2)));
        assert(protocol.Snapshot().code == ContactPickerProtocol::SYSTEM_ERROR);
        ++cases;
    }
    {
        ContactPickerProtocol protocol;
        assert(!protocol.Receive(true, 0, 205, Chunk(0, 100)));
        assert(!protocol.Receive(true, 2, 205, Chunk(200, 5)));
        assert(protocol.Finish(0));
        assert(protocol.Snapshot().code == ContactPickerProtocol::SYSTEM_ERROR);
        ++cases;
    }
    for (int code : {0, -1, 401, 201, 16700101, 16000050}) {
        ContactPickerProtocol protocol;
        assert(protocol.Finish(code));
        assert(protocol.Snapshot().code ==
            (code == 401 || code == 201 || code == 16700101 ? code : ContactPickerProtocol::SYSTEM_ERROR));
        ++cases;
    }
    {
        ContactPickerProtocol protocol;
        assert(!protocol.Receive(true, 0, 1, Chunk(0, 1)));
        assert(protocol.Finish(1));
        assert(protocol.Snapshot().code == ContactPickerProtocol::SYSTEM_ERROR);
        ++cases;
    }
    for (int run = 0; run < 50; ++run) {
        ContactPickerProtocol protocol;
        std::vector<std::thread> threads;
        for (int index = 0; index < 3; ++index) {
            threads.emplace_back([&protocol, index] {
                protocol.Receive(true, index, 205, Chunk(index * 100, index == 2 ? 5 : 100));
            });
        }
        for (auto &thread : threads) { thread.join(); }
        assert(protocol.Finish(0));
        assert(protocol.Snapshot().code == 0);
    }
    ++cases;
    std::cout << cases << " actual protocol challenge cases passed\n";
    return 0;
}
