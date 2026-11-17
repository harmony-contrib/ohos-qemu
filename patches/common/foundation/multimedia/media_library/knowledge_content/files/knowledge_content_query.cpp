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
    return field >= 1 && field <= 8 && field != 7;
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
std::vector<Entity> RandomVote(std::vector<Entity> candidates, size_t count, std::mt19937_64 &random)
{
    std::vector<Entity> selected;
    count = std::min(count, candidates.size());
    selected.reserve(count);
    while (selected.size() < count) {
        std::vector<double> weights;
        weights.reserve(candidates.size());
        for (const auto &candidate : candidates) {
            weights.push_back(static_cast<double>(std::max<int64_t>(candidate.votes, 0)));
        }
        if (std::all_of(weights.begin(), weights.end(), [](double value) { return value <= 0; })) {
            break;
        }
        const size_t index = std::discrete_distribution<size_t>(weights.begin(), weights.end())(random);
        selected.push_back(std::move(candidates[index]));
        candidates.erase(candidates.begin() + index);
    }
    return selected;
}
} // namespace OHOS::Media::Knowledge
