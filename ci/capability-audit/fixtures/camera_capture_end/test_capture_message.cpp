#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>
#include <iostream>
#include <stdexcept>
#include <algorithm>
#include <set>
#include <limits>
#define private public
#include "capture_message.h"
#undef private
using namespace OHOS::Camera;

void Require(bool value, const char* message)
{
    if (!value) throw std::runtime_error(message);
}

std::shared_ptr<ICaptureMessage> End(int stream, int capture, uint64_t timestamp, uint32_t peers = 1)
{
    return std::make_shared<CaptureEndedMessage>(stream, capture, timestamp, peers, 7);
}

struct Collector {
    std::vector<MessageGroup> received;
    CaptureMessageOperator op{[this](MessageGroup& group) { received.push_back(group); }};
    void Queue(std::shared_ptr<ICaptureMessage> message) { op.SendMessage(message); }
    void Drain()
    {
        Require(op.wakeup_, "expected a ready group");
        op.running_ = true;
        op.HandleMessage();
        op.running_ = false;
    }
};

int main(int argc, char** argv)
{
    const bool repaired = argc == 2 && std::string(argv[1]) == "--repaired";
    Collector baseline;
    baseline.Queue(End(11, 101, 1000));
    baseline.Drain();
    Require(baseline.received.size() == 1, "single-stream baseline callback missing");

    Collector peers;
    peers.Queue(End(11, 101, 1000, 2));
    Require(!peers.op.wakeup_, "composite callback prematurely ready");
    peers.Queue(End(12, 101, 1000, 2));
    peers.Drain();
    Require(peers.received.size() == 1 && peers.received[0].size() == 2,
            "legitimate two-stream composite callback missing");

    Collector duplicate;
    duplicate.Queue(End(11, 101, 1000));
    duplicate.Queue(End(11, 101, 1000));
    duplicate.Drain();
    if (!repaired) {
        Require(duplicate.received.empty(), "original duplicate poisoning no longer reproduced");
    } else {
        Require(duplicate.received.size() == 1 && duplicate.received[0].size() == 1,
                "duplicate same-stream message must not poison readiness");
    }

    Collector collision;
    collision.Queue(End(11, 101, 1000));
    collision.Queue(End(12, 102, 1000));
    collision.Drain();
    if (!repaired) {
        Require(collision.received.empty(), "original cross-capture collision no longer reproduced");
    } else {
        Require(collision.received.size() == 2,
                "independent captures sharing a timestamp must not merge");
    }

    Collector repeatedComposite;
    repeatedComposite.Queue(End(11, 101, 1000, 2));
    repeatedComposite.Queue(End(11, 101, 1000, 2));
    if (!repaired) {
        repeatedComposite.Drain();
        Require(repeatedComposite.received.size() == 1 &&
                repeatedComposite.received[0][0]->GetStreamId() ==
                    repeatedComposite.received[0][1]->GetStreamId(),
                "original premature same-stream composite completion not reproduced");
    } else {
        Require(!repeatedComposite.op.wakeup_, "duplicate stream must not satisfy two-peer count");
        repeatedComposite.Queue(End(12, 101, 1000, 2));
        repeatedComposite.Drain();
        Require(repeatedComposite.received.size() == 1 && repeatedComposite.received[0].size() == 2,
                "composite duplicate blocked legitimate peer completion");
    }

    Collector mismatch;
    mismatch.Queue(End(11, 101, 1000, 2));
    mismatch.Queue(End(12, 101, 1000, 1));
    if (!repaired) {
        mismatch.Drain();
        Require(mismatch.received.size() == 1 && mismatch.received[0].size() == 2,
                "original peer-count mismatch contamination not reproduced");
    } else {
        mismatch.Drain();
        Require(mismatch.received.size() == 1 && mismatch.received[0].size() == 1,
                "inconsistent peer counts must not contaminate composite group");
        mismatch.Queue(End(13, 101, 1000, 2));
        mismatch.Drain();
        Require(mismatch.received.size() == 2 && mismatch.received[1].size() == 2,
                "consistent peer group failed after mismatch");
    }

    Collector kinds;
    std::shared_ptr<ICaptureMessage> start = std::make_shared<CaptureStartedMessage>(11, 101, 1000, 1);
    kinds.Queue(start);
    kinds.Queue(End(11, 101, 1000));
    kinds.Drain();
    Require(kinds.received.size() == 2, "start/end types must remain independent");

    Collector empty;
    empty.Queue(nullptr);
    Require(empty.op.messageBox_.empty(), "null input must not create a group");

    if (repaired) {
        Collector malformed;
        malformed.Queue(End(11, 101, 0, 0));
        malformed.Queue(End(-1, 101, 0));
        malformed.Queue(End(11, -1, 0));
        malformed.Queue(std::make_shared<ICaptureMessage>(11, 101, 0, 1));
        Require(malformed.op.messageBox_.empty(), "malformed identity/count/type must be rejected");

        Collector unknownCount;
        unknownCount.Queue(End(11, 101, 0, std::numeric_limits<uint32_t>::max()));
        Require(!unknownCount.op.wakeup_, "incomplete unknown peer count must not be made ready");

        Collector zeroTimestamp;
        zeroTimestamp.Queue(End(11, 101, 0));
        zeroTimestamp.Queue(End(12, 102, 0));
        zeroTimestamp.Drain();
        Require(zeroTimestamp.received.size() == 2,
                "initial timestamp=0 captures must preserve separate completion");

        Collector collisionBatch;
        for (int capture = 1; capture <= 128; ++capture) {
            collisionBatch.Queue(End(11, capture, 0));
            collisionBatch.Queue(End(11, capture, 0));
        }
        collisionBatch.Drain();
        std::set<int> unique;
        for (const auto& group : collisionBatch.received) {
            Require(group.size() == 1, "duplicate poisoned batched group size");
            Require(unique.insert(group[0]->GetCaptureId()).second, "duplicate batched capture delivered");
        }
        Require(unique.size() == 128, "colliding timestamp batch lost completions");

        Collector compositeBatch;
        for (int capture = 1; capture <= 32; ++capture) {
            compositeBatch.Queue(End(11, capture, 0, 2));
            compositeBatch.Queue(End(11, capture, 0, 2));
        }
        Require(!compositeBatch.op.wakeup_, "same-stream batch must not complete composite captures");
        for (int capture = 32; capture >= 1; --capture) {
            compositeBatch.Queue(End(12, capture, 0, 2));
        }
        compositeBatch.Drain();
        Require(compositeBatch.received.size() == 32, "reversed composite peer order lost completion");
        for (const auto& group : compositeBatch.received) {
            Require(group.size() == 2 && group[0]->GetCaptureId() == group[1]->GetCaptureId() &&
                    group[0]->GetStreamId() != group[1]->GetStreamId(), "composite identity contaminated");
        }
    }

    std::cout << (repaired ? "repaired" : "original")
              << ": actual capture_message.cpp baseline/composite PASS; "
              << (repaired ? "duplicate/collision/count regressions PASS" :
                  "duplicate poison/cross-capture loss/premature composite/count contamination REPRODUCED")
              << std::endl;
}
