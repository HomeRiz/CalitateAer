# API Documentation — CalitateAer Integration

This document explains in detail how the CalitateAer Home Assistant integration communicates with the RNMCA (`calitateaer.ro`) API servers, what data it requests, how it processes responses, and how it combines values from multiple stations to produce the area estimates and early-warning sensors exposed in Home Assistant.

For legal terms governing the use of this API, see [TERMS_AND_CONDITIONS.md](TERMS_AND_CONDITIONS.md) and [PRIVACY_POLICY.md](PRIVACY_POLICY.md).

---

## Table of Contents

1. [API Overview](#1-api-overview)
2. [Authentication](#2-authentication)
3. [Base Server and Transport](#3-base-server-and-transport)
4. [Rate Limits and Error Handling](#4-rate-limits-and-error-handling)
5. [API Modules](#5-api-modules)
   - [Simplified Data API](#51-simplified-data-api-used-by-this-integration)
   - [Main Measurement Data API](#52-main-measurement-data-api-not-currently-used)
   - [Air Quality Index API](#53-air-quality-index-api-not-currently-used)
6. [How This Integration Uses the API](#6-how-this-integration-uses-the-api)
7. [Area Estimate Calculation](#7-area-estimate-calculation)
8. [Weather Summary Sensor](#8-weather-summary-sensor)
9. [Early-Warning Logic](#9-early-warning-logic)
10. [Data Freshness and Polling Cadence](#10-data-freshness-and-polling-cadence)
11. [Historical and Database-Level Access](#11-historical-and-database-level-access)
12. [Interactive API Explorer](#12-interactive-api-explorer)

---

## 1. API Overview

The Romanian National Air Quality Monitoring Network (RNMCA) exposes a public REST API at:

```
https://calitateaer.ro:8443
```

The API is documented using OpenAPI 3 (Swagger). It is divided into three modules:

| Module | Purpose | Used by integration |
|---|---|---|
| **Simplified Data API** | Recent measurements and AQI in a human-readable, merged format — up to the last 7 days | **Yes — primary data source** |
| **Main Measurement Data API** | Complete measurement data, historical records, versioned incremental updates, threshold metadata | No — potential future use |
| **Air Quality Index API** | AQI data computed according to Romanian legislation, historical and recent | No — potential future use |

All three modules share the same authentication scheme, base URL, rate-limiting rules, and error codes.

---

## 2. Authentication

All requests require **HTTP Basic Authentication** as specified in RFC 7617.

The username and password are issued by MMAP (Ministerul Mediului, Apelor și Pădurilor) on request via:

> [https://www.calitateaer.ro/public/webservice-page/](https://www.calitateaer.ro/public/webservice-page/)

The integration sends the credentials as a Base64-encoded `Authorization: Basic <token>` header on every request. Credentials are stored in the Home Assistant config entry and never written to disk outside of the standard Home Assistant secrets/storage mechanism.

**Important:** Credentials are personal and per-account. Sharing credentials violates the Terms of Use and may result in account suspension.

---

## 3. Base Server and Transport

- **Base URL:** `https://calitateaer.ro:8443`
- **Protocol:** HTTPS (TLS) on port 8443
- **Compression:** The API documentation recommends sending `Accept-Encoding: gzip` on all requests to reduce response payload size. The integration sets this header.
- **Null handling:** The API typically omits null fields from JSON responses rather than serializing them as `null`.
- **Timestamps:** All timestamps are UTC, represented as Unix milliseconds (int64) in most places or ISO 8601 strings where noted. Station measurement timestamps represent the **end** of the measurement interval.
- **Language:** API responses can be returned in Romanian or English depending on the account settings registered with MMAP.

---

## 4. Rate Limits and Error Handling

The RNMCA API enforces per-user rate limits across multiple time windows:

| Window | Limit type |
|---|---|
| Per 10 seconds | Global user limit |
| Per minute | Global user limit + module-specific limit |
| Per hour | Global user limit + module-specific limit |
| Per day | Global user limit + module-specific limit |

Concurrent request limits also apply.

### HTTP Error Codes

| Code | Meaning | Integration behavior |
|---|---|---|
| `400` | Invalid request parameter | Logged; setup flow reports configuration error |
| `401` | Missing or invalid credentials | Logged; setup flow reports authentication failure |
| `429` | Rate limit exceeded | Respect `Retry-After` response header and back off |
| `503` | Data temporarily unavailable or server overloaded | Retry later; treated as transient |

**Guidance for users:** Do not build automations that call `homeassistant.update_entity` repeatedly for RNMCA sensor entities. The API caches recent data and updates it only a few times per hour. Repeated forced pulls do not produce new data and risk hitting rate limits.

---

## 5. API Modules

### 5.1 Simplified Data API — *Used by this integration*

**Swagger UI:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Simplified%20Data%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Simplified%20Data%20API)

The Simplified Data API is designed for users who want current or recent data in a human-readable, combined format without needing to reconstruct the full RNMCA database model. It merges several layers of the data model — location, parameter, measurement, measurement value, and quality index — into a single, compact response per location.

#### Why this module was chosen

The Main Measurement Data API returns data optimized for database replication: IDs must be resolved against base configuration catalogues, nested objects are serialized by reference, and data is structured for bulk transfers rather than convenience. The Simplified API returns the same fundamental values but pre-joined into a flat, immediately usable shape — making it the right fit for a Home Assistant integration that needs friendly display names, units, and values without maintaining a local RNMCA database.

#### Endpoints used by the integration

---

##### `GET /airquality/simplified/config/all`

**Purpose:** Retrieve the full Simplified API configuration — networks, locations, measurement definitions, and quality index definitions.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lastReceivedVersion` | int64 | Yes | The version of the last received configuration. Use `-1` or leave empty for the first request. On subsequent calls, provide the previously returned version so the API can skip serializing unchanged config. |

**What it returns (`Websaqsd_UserConfigurationWrapper`):**

- A version number for the returned configuration
- Language (ISO3 code)
- `generalQualityIndexDefinitions` — the 1–6 AQI scale with `minIndicesCount` rules
- `specificQualityIndexDefinitions` — per-parameter index definitions with intervals, index codes, and associated parameters
- `networks` and `subnetworks` — hierarchical tree of RNMCA networks (typically organized by county)
- `locations` — each with:
  - `locationId`, `locationCode`
  - WGS84 latitude and longitude
  - Altitude
  - Area type (urban, suburban, rural, etc.)
  - Emission source type (traffic, industrial, background, etc.)
  - Associated `generalQualityIndexId`
  - `measurementValueDefinitions` — the list of parameter/measurement combinations available at that station
- Cached recent measurement values per location (each with type, subtype, interval, measurement name, parameter, unit, and specific quality index ID)

The integration uses this endpoint at startup to:
1. Discover all available RNMCA network IDs (needed for subsequent data requests)
2. Identify which stations fall within the configured radius of each point of interest
3. Learn what parameters each station measures, for creating Home Assistant entities
4. Obtain station coordinates (latitude, longitude) for map display

---

##### `GET /airquality/simplified/data/recent/availableIntervals`

**Purpose:** Query the API for which cache interval codes are currently accepted.

**Parameters:** None

**Returns:** A map of `{ intervalCode: description }` pairs.

During live testing (2026-05-27), the following intervals were confirmed:

```
3h, 12h, 24h, 3d, 7d
```

The interval `1h` is **not** supported by the Simplified Data API. The integration uses `3h` as the shortest available interval.

---

##### `GET /airquality/simplified/data/recent/network`

**Purpose:** Retrieve all recent cached measurement values for a network (and all its subnetworks and locations) for the specified interval.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `networkId` | int64 | Yes | RNMCA network identifier (e.g., `25001`, `25022`). These are discovered from the configuration. Do NOT use `networkId=1` — it returns the entire national dataset for all locations. |
| `intervalCode` | string | Yes | One of the supported interval codes (the integration uses `3h`). |

**Returns (`Websaqsd_Response`):**

```
{
  language: "ENG",
  locationsData: [
    {
      locationId: 12345,
      locationCode: "AB001",
      locationDataForTimestamps: [
        {
          dateTime: "2026-05-27T14:00:00Z",
          measurementValuesData: [
            {
              parameter: "PM 10",
              measurementName: "PM10 gravimetric",
              measurementValueName: "PM10",
              measurementUnit: "μg/m³",
              valid: true,
              usedValue: 18.4,
              qaqcState: "Validated",
              qaqcStatus: "Good",
              hourlySpecificIndex: { indexCode: 1, indexName: "Good", valid: true }
            },
            ...
          ],
          hourlyGeneralIndex: { indexCode: 1, indexName: "Good", valid: true }
        }
      ]
    }
  ]
}
```

**Key field semantics:**

| Field | Meaning |
|---|---|
| `valid` | If `false`, this value is flagged by QA/QC and **must not be used in computations** |
| `usedValue` | The numeric measurement value. If `null`, the value is missing or affected by a range/data issue |
| `qaqcState` | Validation state (e.g., Raw, Validated, Certified) |
| `qaqcStatus` | Validation quality (e.g., Good, Bad, Uncertain) |
| `hourlySpecificIndex` | Present only when this measurement has an associated specific AQI. Contains `indexCode` (1–6) and `indexName` |
| `hourlyGeneralIndex` | The overall AQI for the location at this timestamp — the worst valid specific index among all configured parameters |

---

##### `GET /airquality/simplified/data/recent/location`

**Purpose:** Same as the network endpoint but scoped to a single location ID. Useful for targeted refreshes.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `locationId` | int64 | Yes | RNMCA location identifier |
| `intervalCode` | string | Yes | Cache interval code |

---

### 5.2 Main Measurement Data API — *Not currently used*

**Swagger UI:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Main%20Measurement%20Data%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Main%20Measurement%20Data%20API)

This module is designed for users who need the complete RNMCA dataset — full measurement history, threshold exceedance data, range flags, versioned incremental updates, and the ability to build a local replica of the database.

It is more complete but more complex: nested objects are returned by ID reference and must be inflated using the base configuration catalogue. Processing requires resolving parameters, units, statuses, and measurement ranges from separate lookup tables.

#### All endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/main/config/all?lastReceivedVersion=<n>` | Full RNMCA main configuration (base + network). Returns a new config only if a newer version exists. Pass `-1` for first call. |
| `GET` | `/main/measurements/recent/config/all` | Configuration of which measurement values are cached for recent-data requests |
| `GET` | `/main/measurements/recent/data/availableIntervals` | Available cache interval codes |
| `GET` | `/main/measurements/recent/data/network?networkId=<n>&intervalCode=<c>` | Cached recent data for a network and all subnetworks/locations |
| `GET` | `/main/measurements/recent/data/location?locationId=<n>&intervalCode=<c>` | Cached recent data for a specific location |
| `GET` | `/main/measurements/recent/data/measurementValue?measurementValueId=<n>&intervalCode=<c>` | Cached recent data for a specific measurement value ID |
| `POST` | `/main/measurements/arbitrary/data/measurementValues` | Historical data for arbitrary time intervals (max 1-year span per request, max 100 measurement value IDs per request) |
| `POST` | `/main/measurements/versioned/data/measurementValues` | Incremental data updates since a specified version — used for database replication |

#### Configuration model

The Main configuration is split into two parts:

**Base configuration** (reusable shared entities):
- Measurement units
- Parameters (e.g., PM10, NO2, SO2)
- Statuses and status groups (bit-encoded flags)
- Value types and value subtypes
- Value computation types
- Simple thresholds
- QA/QC states and statuses

**Network configuration** (the measurement tree):
- Networks → Subnetworks → Locations → Measurements → Measurement values
- Most nested objects are serialized as IDs and must be resolved against the base catalogue
- Not all measurement values are available for recent-data caching; only those listed in the recent-data configuration

#### Versioned data (database replication)

The versioned endpoint is designed for replicating the RNMCA database incrementally:
1. First synchronization: use the arbitrary data endpoint for the full initial history
2. Subsequent updates: use the versioned endpoint with the version number of the last received record — only records with newer versions are returned
3. Only measurement values marked `versioned=true` in the configuration can use the versioned endpoint

> **Note:** Building a full local replica of RNMCA historical data is a heavier integration that may require a dedicated data pipeline. If you need historical access at database scale, contact MMAP through the API request form (see *Getting API Credentials* in [README.md](README.md)).

---

### 5.3 Air Quality Index API — *Not currently used*

**Swagger UI:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Air%20Quality%20Index%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Air%20Quality%20Index%20API)

This module focuses specifically on air quality index data computed according to Romanian legislation. Rather than exposing raw measurement values, it exposes only the derived index values (codes 1–6) at the location and measurement-value level.

#### All endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/airquality/index/config/all?lastReceivedVersion=<n>` | AQI configuration: base definitions (index codes, general and specific quality indexes) and network tree linking locations to index definitions |
| `GET` | `/airquality/index/data/recent/availableIntervals` | Available cache interval codes |
| `GET` | `/airquality/index/data/recent/location?locationId=<n>&intervalCode=<c>` | Cached recent AQI data for a location |
| `GET` | `/airquality/index/data/recent/network?networkId=<n>&intervalCode=<c>` | Cached recent AQI data for a network (recursive) |
| `POST` | `/airquality/index/data/arbitrary/locations` | Historical AQI data for a list of location IDs and a custom time range (max 100 location IDs, max 1-year span) |

#### Data model

- **Specific index:** tied to a measurement value — represents the AQI for one pollutant parameter at one location and hour. For example, SO2, O3, and NO2 indexes are computed from hourly averages; PM10 and PM2.5 indexes use a 24-hour moving average.
- **General index:** tied to a location — represents the worst valid specific index across all configured parameters for the same hourly interval.

AQI entity IDs in this module match the corresponding IDs in the Main Measurement Data API, so they can be cross-referenced if needed.

The Simplified Data API already embeds both specific and general index values in its measurement response, making a separate call to the AQI API redundant for current-value use cases. The AQI API becomes useful for historical AQI trend analysis or for building dedicated index dashboards.

---

## 6. How This Integration Uses the API

At startup and at each polling cycle the integration performs the following steps:

### Step 1 — Configuration fetch

```
GET /airquality/simplified/config/all?lastReceivedVersion=-1
```

This returns the full Simplified configuration including all 50 RNMCA networks, 186 locations (as of 2026-05), station coordinates, and measurement value definitions for each station.

The integration:
1. Iterates over all locations in the configuration
2. Calculates the great-circle (haversine) distance from each station to each configured point of interest
3. Keeps all stations within the configured monitoring radius
4. Stores station metadata: ID, network ID, name, coordinates, distance, and source point of interest

### Step 2 — Data fetch per network

For each unique network ID that contains at least one station within range:

```
GET /airquality/simplified/data/recent/network?networkId=<id>&intervalCode=3h
```

The response is a list of location data objects. Each location contains one or more timestamp groups, and each timestamp group contains a list of measurement values.

The integration processes the most recent timestamp group for each station and updates the corresponding Home Assistant sensor entities.

### Step 3 — Entity creation and update

For each station–parameter combination:
1. A Home Assistant sensor entity is created (if it does not already exist)
2. The entity state is set to the `usedValue` from the most recent valid measurement
3. If `valid` is `false` or `usedValue` is `null`, the entity is set to `unavailable`
4. Attributes are populated: station name, coordinates, distance from monitored point, RNMCA station/network IDs, measurement timestamp, QA/QC state/status, AQI code and name where available

Station sensors are marked as **diagnostic** and **disabled by default** on new installs — they serve as raw reference data. The area estimate sensors and early-warning sensor remain enabled by default.

---

## 7. Area Estimate Calculation

For each point of interest and each detected parameter, the integration creates an **area estimate sensor** — a single combined value representing what the air quality near your monitored location likely is, based on readings from surrounding stations.

### Method: Inverse Distance Weighted (IDW) average

The formula used is:

```
estimated_value = Σ (value_i / distance_i²) / Σ (1 / distance_i²)
```

where `value_i` is the reading at station `i` and `distance_i` is the distance in kilometres from that station to the monitored point.

Stations closer to the monitored point receive significantly more weight than distant stations. A station 5 km away gets 4× the weight of one 10 km away.

**Important caveats:**

- This is **not an official RNMCA interpolation model**. It is a practical estimate for Home Assistant dashboards and automations.
- Only stations with `valid=true` and non-null `usedValue` are included in the calculation.
- The calculation assumes flat space (short distances). For very large radii this becomes less accurate.
- Different stations update at different times; the latest measurement time per station is exposed in the sensor attributes.

### Area estimate sensor attributes

| Attribute | Description |
|---|---|
| `station_count` | Number of stations contributing to the estimate |
| `nearest_station_distance_km` | Distance to the closest contributing station |
| `farthest_station_distance_km` | Distance to the farthest contributing station |
| `minimum_value` | Lowest raw value among contributing stations |
| `maximum_value` | Highest raw value among contributing stations |
| `latest_measurement_time` | Most recent measurement timestamp among contributing stations |
| `contributing_stations` | List of station names, values, distances, and individual measurement times |
| `method` | Always `inverse_distance_weighted_area_estimate` |

---

## 8. Weather Summary Sensor

For each monitored point, the integration creates a **weather summary sensor** that combines wind and pressure readings from all nearby stations using the same IDW formula.

### State

The sensor state is the estimated 16-point compass sector when wind direction data is available:

```
N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW
```

### Attributes

| Attribute | Description |
|---|---|
| `estimated_wind_speed_mps` | IDW-weighted wind speed in metres per second |
| `estimated_wind_speed_kmh` | Same in km/h |
| `estimated_wind_speed_band` | Speed band label (following RNMCA website convention) |
| `estimated_wind_direction_degrees` | IDW-weighted wind direction in degrees (0–360) |
| `estimated_wind_direction_cardinal` | 16-point compass abbreviation |
| `estimated_wind_direction_name` | Full name (e.g., "South-Southwest") |
| `estimated_air_pressure_hpa` | IDW-weighted air pressure in hPa |
| `wind_station_count` | Number of stations contributing wind data |
| `pressure_station_count` | Number of stations contributing pressure data |
| `contributing_stations` | Per-station detail |

### Wind speed bands

| Band |
|---|
| `< 0.50 m/s` |
| `0.50 – 2.00 m/s` |
| `2.00 – 6.00 m/s` |
| `6.00 – 8.00 m/s` |
| `8.00 – 10.00 m/s` |
| `10.00 – 12.00 m/s` |
| `> 12.00 m/s` |

---

## 9. Early-Warning Logic

For each monitored point the integration creates an **early-warning summary sensor** with three possible states:

| State | Meaning |
|---|---|
| `clear` | No elevated readings detected among nearby stations |
| `watch` | One station reporting a moderate-level event, or integration-side threshold exceeded |
| `warning` | One station reporting a high-level event, or two or more separate stations at watch level |

### Classification sources

**Primary: RNMCA air quality index codes**

| Index code | Integration state |
|---|---|
| 1–2 | `clear` |
| 3 | `watch` |
| 4–6 | `warning` |

**Fallback: integration-side thresholds (when no AQI index is available)**

Applied for: PM10, PM2.5, NO2, SO2, O3, CO, benzene, H2S, NH3, wind speed, solar radiation, air temperature.

These are conservative reference thresholds. They are **not** replacements for the official RNMCA threshold exceedance data available through the Main Measurement Data API.

### Multi-station escalation

If two or more separate stations independently report watch-level events for the same monitored point, the overall state escalates to `warning` — because corroborating readings from multiple independent stations are treated as stronger evidence of a real event.

### Direction and ETA

When a station reports an event and also provides wind speed and wind direction:
1. The bearing from the event station to the monitored point is calculated using WGS84 coordinates
2. The wind vector at the station is compared to that bearing
3. If the wind is generally blowing toward the monitored point, an ETA is estimated as:
   ```
   ETA (minutes) = (distance_km / wind_speed_mps) × (1000 / 60)
   ```
4. The ETA is intentionally approximate — it assumes straight-line movement at constant speed, with no modelling of terrain, atmospheric dispersion, changing wind direction, or pressure systems

### Early-warning sensor attributes

| Attribute | Description |
|---|---|
| `state_label` | Human-readable state name |
| `event_count` | Total number of events (watch + warning) detected |
| `warning_count` | Number of warning-level events |
| `watch_count` | Number of watch-level events |
| `nearest_event_distance_km` | Distance to the nearest triggering station |
| `primary_direction_from_poi` | Compass direction toward the primary event station |
| `primary_eta_minutes` | Estimated minutes until the primary event reaches the monitored point (null if no wind data) |
| `top_event_summary` | Human-readable string describing the most significant event |
| `events` | Full list of events with station name, parameter, value, unit, distance, direction, QA/QC, AQI details, and ETA |

---

## 10. Data Freshness and Polling Cadence

| Behaviour | Detail |
|---|---|
| **Polling interval** | The integration polls the API at the `3h` cadence matching the shortest available cache interval |
| **Actual data freshness** | The RNMCA API documentation states that recent cached data normally changes **about once per hour** |
| **`1h` interval** | Not supported by the Simplified Data API — requesting it returns an error |
| **Root network requests** | Requesting `networkId` of the root RNMCA network returns all locations across all subnetworks for the selected interval — avoid this unless every station nationwide is needed |
| **Configuration versioning** | The current integration always passes `lastReceivedVersion=-1` and fetches the full configuration on each cycle. A future optimisation should store the returned version and send it back to avoid redundant configuration serialization |
| **Forcing updates** | Do not use `homeassistant.update_entity` in automations targeting RNMCA sensors — the underlying cached data does not change on demand |

---

## 11. Historical and Database-Level Access

The current integration only uses the **recent cached data** (up to 7 days) available through the Simplified Data API. For deeper historical access:

- The **Main Measurement Data API** provides arbitrary time-range queries (`POST /main/measurements/arbitrary/data/measurementValues`) for up to a 1-year span per request, for up to 100 measurement value IDs per request.
- The **versioned endpoint** (`POST /main/measurements/versioned/data/measurementValues`) supports incremental database replication — ideal for building a long-term local RNMCA archive.
- The **Air Quality Index API** also supports arbitrary historical AQI data via `POST /airquality/index/data/arbitrary/locations`.

Building a full historical integration requires significant additional work: loading and caching the Main Measurement base configuration, resolving all ID references, managing large response payloads, and scheduling incremental syncs.

**If you need database-level historical access for research or analytics purposes**, contact MMAP directly through the API request form at [https://www.calitateaer.ro/public/webservice-page/](https://www.calitateaer.ro/public/webservice-page/) and indicate in your request that you need access to the Main Measurement Data API and/or versioned replication endpoints. The API access level granted may vary depending on your stated use case.

---

## 12. Interactive API Explorer

All three API modules are browsable through the RNMCA Swagger UI:

- **All modules:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=/api-docs/swagger-config](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=/api-docs/swagger-config)
- **Simplified Data API:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Simplified%20Data%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Simplified%20Data%20API)
- **Main Measurement Data API:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Main%20Measurement%20Data%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Main%20Measurement%20Data%20API)
- **Air Quality Index API:** [https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Air%20Quality%20Index%20API](https://calitateaer.ro:8443/swagger-ui/index.html?configUrl=%2Fapi-docs%2Fswagger-config&urls.primaryName=Air%20Quality%20Index%20API)

You can use the Swagger UI to explore the full request/response schemas, try live calls with your credentials, and browse all available parameters and models in detail.

---

*This document reflects the API state as of May 2026, based on live API testing and the published OpenAPI 3 specifications. API structure may change; consult the Swagger UI for the authoritative current specification.*
