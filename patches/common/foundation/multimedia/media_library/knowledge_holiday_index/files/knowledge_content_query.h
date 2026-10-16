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
std::vector<Entity> RandomVote(std::vector<Entity> candidates, size_t count, std::mt19937_64 &random);
} // namespace OHOS::Media::Knowledge
#endif
