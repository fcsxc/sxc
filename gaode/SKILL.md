---
name: gaode-nearby-explorer
description: Recommend nearby places with verifiable walking routes using AMap. Use when a user provides a city or starting point and asks for nearby cafes, restaurants, parks, attractions, or other places, especially when walk-time limits, travel distance, ranking, or route guidance matter.
---

# Nearby Place Recommendation with AMap

Turn one natural-language request into a small set of real, walking-distance-verified place recommendations. Use the AMap tools exposed by the runtime; do not invent POIs, addresses, coordinates, distances, durations, opening hours, or ratings.

## 1. Parse the request

Extract:

- `origin`: the user's starting point. Prefer the supplied coordinates. If only an address or landmark is given, use the available AMap geocoding tool to obtain coordinates.
- `city`: city name, when supplied.
- `category`: requested place type, such as cafe, restaurant, park, museum, or scenic spot.
- `max_results`: requested count, capped at **3**.
- `walk_limit`: maximum walking time in minutes, when supplied.
- `preferences`: for example nearest first, budget, atmosphere, or accessibility.

Do not ask follow-up questions when the request is usable. Apply these defaults only when the user is silent: `max_results = 3`, no hard walking-time limit, and nearest-first ranking.

Normalize coordinates to AMap's `longitude,latitude` string format.

## 2. Find candidate places

Use the AMap nearby-search capability (typically `maps_around_search`) with:

- `keywords`: the requested category or a close synonym
- `location`: the origin coordinate string
- `radius`: a search radius in meters

Choose a sensible initial radius:

- 10-minute limit: about 800 m
- 15-minute limit: about 1500 m
- 30-minute limit: about 3000 m
- No limit: about 2000 m

If the first search returns too few usable candidates, retry once with a nearby synonym or a larger radius that still respects the user's walking limit. Do not silently change a hard constraint.

Collect each candidate's `id`, `name`, `address`, `location`, and type. Use the AMap POI-detail capability (typically `maps_search_detail`) only when a required field or coordinate is missing. Deduplicate by POI ID and discard results that clearly do not match the requested category.

## 3. Verify actual walking routes

For each viable candidate, call the AMap walking-route capability (typically `maps_walking`) with:

- `origin`: the user's starting coordinate
- `destination`: the candidate's coordinate

Read `distance` (meters) and `duration` (normally seconds) from the returned walking route. Convert duration to minutes with `ceil(duration / 60)`. A candidate qualifies only when this route-derived duration does not exceed the user's walking-time limit.

Never substitute straight-line distance, estimated distance, or an assumed walking speed for a successful walking-route result. If a route call fails, retry once; if it still fails, exclude that candidate from the matching recommendations and mention the route-data failure briefly.

## 4. Rank and select

- Apply all explicit hard constraints first: place type, walking-time limit, requested count, and any stated accessibility requirement.
- Rank qualifying places by walking time ascending for "nearest first" or by the user's stated preference.
- When times are close, prefer shorter walking distance.
- Return at most 3 places, even when more candidates qualify.
- Do not pad the list. If fewer than requested qualify, state how many were found and suggest widening the radius or walking-time limit.

Only use facts present in AMap results. Characteristics such as quietness, queue length, current opening status, or service quality are unverified unless the tool response explicitly provides current evidence; label them `未核实`.

## 5. Respond

Lead with a compact table:

| 排名 | 地点 | 地址 | 步行距离 | 预计步行时间 | 推荐理由 |
|---|---|---|---|---|---|
| 1 | AMap-returned name | AMap-returned address | AMap-returned distance | route-derived minutes | one evidence-based sentence |

After the table, add at most two short notes when needed:

- `说明：在指定步行时间/查询范围内仅找到 N 个符合条件的地点。`
- `未核实：营业状态、排队情况、安静程度等未由高德数据确认。`
- `查询异常：部分地点的步行路线暂时无法获取，已从推荐中排除。`

Use friendly, concise Chinese unless the user uses another language. Format distance as meters below 1000 m and kilometers with one decimal above 1000 m. Make clear that each recommendation is an independent option from the same origin, not a multi-stop itinerary.

## Failure handling

- Missing or ambiguous starting location: ask for a landmark, address, or coordinates when it cannot be resolved unambiguously.
- No POIs: say no matching place was found in the searched area and suggest a broader category or larger radius.
- No route data: never claim walking feasibility; omit the candidate or explicitly report that it could not be verified.
- AMap service error: state that live place or route data is temporarily unavailable and suggest retrying later.
