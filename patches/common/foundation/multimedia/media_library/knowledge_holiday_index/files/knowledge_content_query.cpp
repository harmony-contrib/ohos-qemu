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
#include "knowledge_content_query.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
namespace OHOS::Media::Knowledge {
namespace {
// A single statement sees one real database snapshot. Every entity/map/alias
// remains joined to a currently visible Photos row; stale analysis entries
// cannot survive a photo delete/trash/hide or appear through stored album counts.
// Risk photos stay excluded: READ_IMAGEVIDEO does not grant MANAGE_RISK_PHOTOS.
const std::string ROWS = R"SQL(WITH eligible AS (
 SELECT file_id,date_year,date_month,date_day,media_type FROM Photos
 WHERE sync_status=0 AND clean_flag=0 AND hidden=0 AND date_trashed=0
 AND time_pending=0 AND is_temp=0 AND is_critical=0 AND burst_cover_level=1
 AND media_type IN (1,2)
), entity_rows(asset_id,field,entity_id,name,alias) AS (
 SELECT p.file_id,CASE a.album_subtype WHEN 4102 THEN 1 WHEN 4097 THEN 2 WHEN 4100 THEN 3 END,
 CAST(a.album_id AS TEXT),a.album_name,COALESCE(n.nick_name,'')
 FROM eligible p JOIN AnalysisPhotoMap m ON m.map_asset=p.file_id
 JOIN AnalysisAlbum a ON a.album_id=m.map_album
 LEFT JOIN tab_analysis_nick_name n ON n.album_id=a.album_id AND a.album_subtype=4102
 WHERE a.album_subtype IN (4102,4097,4100) AND a.album_name IS NOT NULL AND a.album_name<>''
 UNION ALL SELECT file_id,4,date_year,date_year,'' FROM eligible WHERE date_year<>''
 UNION ALL SELECT file_id,5,date_month,date_month,'' FROM eligible WHERE date_month<>''
 UNION ALL SELECT file_id,6,date_day,date_day,'' FROM eligible WHERE date_day<>''
 UNION ALL SELECT p.file_id,7,h.entity_id,h.name,''
 FROM eligible p JOIN KnowledgeHoliday h ON h.civil_date=p.date_day
 UNION ALL SELECT file_id,8,CAST(media_type AS TEXT),
 CASE media_type WHEN 1 THEN 'IMAGE' ELSE 'VIDEO' END,'' FROM eligible
))SQL";
std::string Placeholders(const std::vector<int32_t> &values, std::vector<Argument> &args)
{
    std::string result;
    std::set<int32_t> distinct(values.begin(), values.end());
    for (int32_t value : distinct) {
        if (!result.empty()) {
            result += ',';
        }
        result += '?';
        args.emplace_back(static_cast<int64_t>(value));
    }
    return result;
}
} // namespace
bool IsField(int32_t field)
{
    return field >= 0 && field <= 8;
}
bool HasProducer(int32_t field)
{
    return field >= 1 && field <= 8;
}
Query Related(const std::string &topic, const std::vector<int32_t> &topicFields,
    const std::vector<int32_t> &suggestionFields)
{
    Query query;
    query.sql = ROWS + ", topic_entities AS (SELECT DISTINCT field,entity_id,asset_id FROM entity_rows WHERE field IN (";
    query.sql += Placeholders(topicFields, query.args);
    query.sql += ") AND (instr(lower(name),lower(?))>0 OR instr(lower(alias),lower(?))>0)),";
    query.args.emplace_back(topic);
    query.args.emplace_back(topic);
    query.sql += " votes AS (SELECT e.field,e.entity_id,e.name,COUNT(DISTINCT e.asset_id) AS votes"
        " FROM entity_rows e JOIN (SELECT DISTINCT asset_id FROM topic_entities) t ON t.asset_id=e.asset_id"
        " WHERE e.field IN (";
    query.sql += Placeholders(suggestionFields, query.args);
    query.sql += ") AND NOT EXISTS (SELECT 1 FROM topic_entities x WHERE x.field=e.field AND x.entity_id=e.entity_id)"
        " GROUP BY e.field,e.entity_id,e.name)"
        " SELECT DISTINCT v.field,v.entity_id,v.name,e.alias,v.votes FROM votes v"
        " JOIN entity_rows e ON e.field=v.field AND e.entity_id=v.entity_id AND e.name=v.name"
        " ORDER BY v.field,v.entity_id,v.name,e.alias";
    return query;
}
Query Suggestions(const std::vector<int32_t> &types)
{
    Query query;
    query.sql = ROWS;
    // Actual source fields per SDK SearchSuggestionType; a scenario exists only
    // when all its named time/people/geography/label components share an asset.
    const std::vector<std::vector<int32_t>> fields = {
        {6,3,2}, {6,3}, {6,2}, {6,1,3,2}, {6,1,3}, {6,1,2}, {6,1}
    };
    std::set<int32_t> distinct(types.begin(), types.end());
    bool first = true;
    for (int32_t type : distinct) {
        if (type < 0 || type >= static_cast<int32_t>(fields.size())) {
            return {};
        }
        query.sql += first ? " SELECT * FROM (" : " UNION ALL SELECT * FROM (";
        first = false;
        query.sql += "SELECT ? AS type,";
        query.args.emplace_back(static_cast<int64_t>(type));
        const auto &components = fields[type];
        for (size_t i = 0; i < components.size(); ++i) {
            if (i != 0) {
                query.sql += " || ' ' || ";
            }
            query.sql += "e" + std::to_string(i) + ".name";
        }
        query.sql += " AS value,COUNT(DISTINCT e0.asset_id) AS count FROM entity_rows e0";
        for (size_t i = 1; i < components.size(); ++i) {
            const std::string name = "e" + std::to_string(i);
            query.sql += " JOIN entity_rows " + name + " ON " + name + ".asset_id=e0.asset_id";
        }
        query.sql += " WHERE ";
        for (size_t i = 0; i < components.size(); ++i) {
            if (i != 0) {
                query.sql += " AND ";
            }
            query.sql += "e" + std::to_string(i) + ".field=?";
            query.args.emplace_back(static_cast<int64_t>(components[i]));
        }
        query.sql += " GROUP BY value ORDER BY count DESC,value)";
    }
    return query;
}
namespace {
constexpr const char *SERVICE_WIRE = "KnowledgeContent.service.v1";
void WriteFields(std::vector<std::string> &wire, const std::vector<int32_t> &fields)
{
    wire.push_back(std::to_string(fields.size()));
    for (int32_t field : fields) wire.push_back(std::to_string(field));
}
bool ReadFields(const std::vector<std::string> &wire, size_t &position,
    std::vector<int32_t> &fields, int32_t minimum, int32_t maximum)
{
    // Counts and enums have single canonical decimal digits (at most 8 fields).
    if (position >= wire.size() || wire[position].size() != 1 ||
        wire[position][0] < '1' || wire[position][0] > '8') return false;
    const size_t count = static_cast<size_t>(wire[position++][0] - '0');
    if (count > static_cast<size_t>(maximum - minimum + 1) || count > wire.size() - position) return false;
    for (size_t n = 0; n < count; ++n) {
        const auto &token = wire[position++];
        if (token.size() != 1 || token[0] < '0' + minimum || token[0] > '0' + maximum) return false;
        const int32_t field = token[0] - '0';
        if (std::find(fields.begin(), fields.end(), field) != fields.end()) return false;
        fields.push_back(field);
    }
    return true;
}
} // namespace
std::vector<std::string> RelatedWire(const std::string &topic, const std::vector<int32_t> &topicFields,
    const std::vector<int32_t> &suggestionFields)
{
    std::vector<std::string> wire = {SERVICE_WIRE, "related", topic};
    WriteFields(wire, topicFields); WriteFields(wire, suggestionFields);
    return wire;
}
std::vector<std::string> SuggestionsWire(const std::vector<int32_t> &types)
{
    std::vector<std::string> wire = {SERVICE_WIRE, "suggestions"};
    WriteFields(wire, types); return wire;
}
bool DecodeServiceWire(const std::vector<std::string> &wire, Query &query)
{
    if (wire.size() < 4 || wire.size() > 21 || wire[0] != SERVICE_WIRE) return false;
    std::vector<int32_t> fields, suggestions;
    size_t position = 0;
    if (wire[1] == "related") {
        if (wire[2].size() > 64 * 1024) return false;
        position = 3;
        if (!ReadFields(wire, position, fields, 1, 8) ||
            !ReadFields(wire, position, suggestions, 1, 8) || position != wire.size()) return false;
        query = Related(wire[2], fields, suggestions);
    } else if (wire[1] == "suggestions") {
        position = 2;
        if (!ReadFields(wire, position, fields, 0, 6) || position != wire.size()) return false;
        query = Suggestions(fields);
    } else return false;
    return !query.sql.empty();
}

std::vector<Entity> RandomVote(std::vector<Entity> candidates, size_t count, std::mt19937_64 &random)
{
    // Exponential-race weighted sampling without replacement. With no explicit
    // count this is an O(n log n) weighted permutation, not an O(n^2) redraw loop.
    struct Choice {double key; size_t index;};
    std::vector<Entity> selected;
    if (count == 0) return selected;
    std::vector<Choice> choices;
    choices.reserve(candidates.size());
    for (size_t index = 0; index < candidates.size(); ++index) {
        if (candidates[index].votes <= 0) continue;
        const double uniform = std::max(std::numeric_limits<double>::min(),
            1.0 - std::generate_canonical<double,53>(random));
        choices.push_back({-std::log(uniform)/static_cast<double>(candidates[index].votes),index});
    }
    count = std::min(count,choices.size());
    auto compare = [](const Choice &left,const Choice &right) {
        return left.key == right.key ? left.index < right.index : left.key < right.key;
    };
    std::partial_sort(choices.begin(),choices.begin()+count,choices.end(),compare);
    selected.reserve(count);
    for (size_t i = 0; i < count; ++i) selected.push_back(std::move(candidates[choices[i].index]));
    return selected;
}
} // namespace OHOS::Media::Knowledge
