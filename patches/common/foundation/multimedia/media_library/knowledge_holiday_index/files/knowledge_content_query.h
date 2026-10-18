/*
 * Copyright (C) 2026 OpenHarmony Contributors.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef OHOS_MEDIA_KNOWLEDGE_CONTENT_QUERY_H
#define OHOS_MEDIA_KNOWLEDGE_CONTENT_QUERY_H
#include <cstddef>
#include <cstdint>
#include <random>
#include <string>
#include <variant>
#include <vector>
namespace OHOS::Media::Knowledge {
using Argument = std::variant<int64_t, std::string>;
// Every original Account() row costs at least two int32s and one std::string.
// The extra sentinel row makes a possible truncation an explicit resource error.
constexpr size_t MIN_ACCOUNTED_ROW_BYTES = 2 * sizeof(int32_t) + sizeof(std::string);
constexpr size_t SERVICE_ROW_LIMIT = (8 * 1024 * 1024) / MIN_ACCOUNTED_ROW_BYTES;

struct Query {
    std::string sql;
    std::vector<Argument> args;
};
struct Entity {
    int32_t field = 0;
    std::string id;
    std::string name;
    std::vector<std::string> aliases;
    int64_t votes = 0;
};
// NONE is an enum sentinel and is rejected as a query field with parameter error.
// HOLIDAY joins the real service-maintained KnowledgeHoliday civil-date index.
bool IsField(int32_t field);
bool HasProducer(int32_t field);
Query Related(const std::string &topic, const std::vector<int32_t> &topicFields,
    const std::vector<int32_t> &suggestionFields);
Query Suggestions(const std::vector<int32_t> &types);
// Fixed internal DataShare protocol. No raw SQL, database path or bind expression
// crosses IPC. The service reconstructs the same query from bounded typed data.
std::vector<std::string> RelatedWire(const std::string &topic, const std::vector<int32_t> &topicFields,
    const std::vector<int32_t> &suggestionFields);
std::vector<std::string> SuggestionsWire(const std::vector<int32_t> &types);
bool DecodeServiceWire(const std::vector<std::string> &wire, Query &query);

std::vector<Entity> RandomVote(std::vector<Entity> candidates, size_t count, std::mt19937_64 &random);
} // namespace OHOS::Media::Knowledge
#endif
