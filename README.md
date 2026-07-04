# CalitateAer — RNMCA Air Quality for Home Assistant

<img width="100" alt="CalitateAer Logo" src="https://raw.githubusercontent.com/HomeRiz/CalitateAer/refs/heads/main/custom_components/calitateaer/brand/icon.png" />

Home Assistant custom integration for the Romanian National Air Quality Monitoring Network (RNMCA), using the public [calitateaer.ro](https://www.calitateaer.ro) API.

> **Note:** This integration was developed with the assistance of AI tools — primarily **Claude Code** and **ChatGPT / Codex**. The code is functional and actively used, but it is not perfect. Use it as a helpful monitoring tool, not as a safety-critical or official alert system. Feedback and contributions are welcome.

---

## What It Does

CalitateAer connects Home Assistant to the RNMCA station network. It discovers monitoring stations around one or more configured locations, creates sensor entities for every measured parameter, and provides an early-warning summary sensor that can alert you before elevated pollution or adverse weather reaches your area.

**Key capabilities:**

- Monitors official RNMCA air quality stations within a configurable radius of your chosen locations
- Tracks pollutants (PM10, PM2.5, NO2, SO2, O3, CO, benzene, H2S, NH3, and more) and meteorological values (wind speed and direction, temperature, humidity, pressure, solar radiation, precipitation)
- Exposes station coordinates for use in Home Assistant map cards
- Provides an **early-warning sensor** per monitored location with direction and estimated time of arrival when wind data is available
- Estimates a combined **area value** for each parameter using nearby stations weighted by distance
- Supports **multiple points of interest** — home, workplace, family locations, or any custom coordinates

---

## Getting API Credentials

The RNMCA API requires credentials (username and password) issued by the Ministry of Environment, Waters and Forests of Romania (MMAP).

**To request access:**

1. Visit the official page: [https://www.calitateaer.ro/public/webservice-page/](https://www.calitateaer.ro/public/webservice-page/)
2. Follow the instructions on that page to submit a request — you will need to provide your name (or company name), personal/company ID, email address, reason for requesting access, which API module(s) you want to use, preferred data language (Romanian or English), and acceptance of the Terms and Conditions
3. Submit the form and **be patient** — the MMAP team reviews requests manually and may take up to 10 business days to respond. Your credentials will be sent to your email once approved

Credentials are **personal and non-transferable**. Do not share them. See the [Terms and Conditions](TERMS_AND_CONDITIONS.md) for full details.

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the three-dot menu → **Custom repositories**
4. Add the repository URL:
   ```
   https://github.com/HomeRiz/CalitateAer
   ```
   and select category **Integration**
5. Search for **RNMCA Air Quality** and install it
6. **Restart Home Assistant**

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/calitateaer` folder to your Home Assistant `config/custom_components/` directory:
   ```
   config/
   └── custom_components/
       └── calitateaer/
   ```
3. **Restart Home Assistant**

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **RNMCA Air Quality**
3. Enter your RNMCA API **username** and **password**
4. Select the **language** for integration labels
5. Choose your location method: Home Assistant map, address lookup, or manual coordinates
6. Add one or more **points of interest** and set a monitoring **radius**

You can adjust the radius and add more points of interest later through the integration options.

---

## Data Update Intervals

The RNMCA API caches recent data and refreshes it a limited number of times per hour. The integration uses the shortest available interval supported by the Simplified Data API, which is **3 hours**.

Available cached data intervals: `3h`, `12h`, `24h`, `3d`, `7d`

**Important:** Not all sensors will update simultaneously — different parameters and stations update according to their own measurement cycles. Avoid creating automations that force frequent manual refreshes of RNMCA entities; the underlying data from the API is not truly real-time and forcing extra calls will not produce new values.

See [API.md](API.md) for full details on how data is fetched and combined.

---

## Sensors and Entities

For each configured point of interest, the integration creates:

| Entity type | Description |
|---|---|
| **Early-warning sensor** | Summary state: `clear`, `watch`, or `warning`, with direction and ETA attributes |
| **Area estimate sensors** | One per detected parameter — an estimated local value from nearby stations using inverse-distance weighting |
| **Weather summary sensor** | Combined wind speed, direction, compass sector, and pressure estimate |
| **Station sensors** | Individual measurements per RNMCA station (diagnostic, disabled by default on new installs) |

### Air Quality Index Scale

RNMCA uses a 1–6 index scale:

| Code | Meaning |
|---|---|
| 1 | Good |
| 2 | Acceptable |
| 3 | Moderate |
| 4 | Bad |
| 5 | Very bad |
| 6 | Extremely bad |

The integration triggers **watch** at index code 3 and **warning** at index code 4 or higher. Conservative fallback thresholds are also applied for parameters without index codes (PM10, PM2.5, NO2, SO2, O3, CO, benzene, H2S, NH3, wind speed, solar radiation, air temperature).

---

## Automation Examples

### 1. Early Warning Notification

Send a mobile notification whenever the warning sensor changes to `watch` or `warning`.

```yaml
alias: Air Quality Early Warning
mode: queued
trigger:
  - platform: state
    entity_id: sensor.rnmca_home_early_warning
    to:
      - "watch"
      - "warning"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "⚠️ Air Quality {{ trigger.to_state.state | title }}"
      message: >-
        {{ trigger.to_state.attributes.top_event_summary }}
        Direction: {{ trigger.to_state.attributes.primary_direction_from_poi }}.
        {% if trigger.to_state.attributes.primary_eta_minutes %}
        ETA: ~{{ trigger.to_state.attributes.primary_eta_minutes }} min.
        {% endif %}
```

---

### 2. Close Windows on Pollution Warning

Automatically close smart windows or pause mechanical ventilation when elevated pollution is heading toward your home.

```yaml
alias: Close Windows on Pollution Warning
mode: single
trigger:
  - platform: state
    entity_id: sensor.rnmca_home_early_warning
    to: "warning"
condition:
  - condition: state
    entity_id: binary_sensor.windows_open
    state: "on"
action:
  - service: cover.close_cover
    target:
      area_id: living_room
  - service: notify.mobile_app_your_phone
    data:
      title: "Windows closed automatically"
      message: >-
        Pollution warning detected.
        {{ trigger.to_state.attributes.top_event_summary }}
```

---

### 3. Repeated Alert While Warning Is Active

Send a reminder notification every 45 minutes for as long as a warning remains active.

```yaml
alias: Repeat Air Quality Warning
mode: single
trigger:
  - platform: state
    entity_id: sensor.rnmca_home_early_warning
    to: "warning"
action:
  - repeat:
      while:
        - condition: state
          entity_id: sensor.rnmca_home_early_warning
          state: "warning"
      sequence:
        - service: notify.mobile_app_your_phone
          data:
            title: "⛔ Air Quality Warning Still Active"
            message: >-
              Events: {{ state_attr('sensor.rnmca_home_early_warning', 'warning_count') }} warning,
              {{ state_attr('sensor.rnmca_home_early_warning', 'watch_count') }} watch.
              {{ state_attr('sensor.rnmca_home_early_warning', 'top_event_summary') }}
        - delay:
            minutes: 45
```

---

### 4. Strong Wind from Unfavourable Direction

Alert when a strong southwesterly wind is detected — useful for knowing when pollution from industrial areas may be carried toward your location.

```yaml
alias: Strong SW Wind Alert
mode: single
trigger:
  - platform: numeric_state
    entity_id: sensor.rnmca_home_area_weather
    attribute: estimated_wind_speed_mps
    above: 8
condition:
  - condition: template
    value_template: >-
      {{ state_attr('sensor.rnmca_home_area_weather', 'estimated_wind_direction_cardinal')
         in ['SW', 'WSW', 'SSW', 'S'] }}
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "💨 Strong SW Wind"
      message: >-
        Wind: {{ state_attr('sensor.rnmca_home_area_weather', 'estimated_wind_speed_kmh') | round(1) }} km/h
        from {{ state_attr('sensor.rnmca_home_area_weather', 'estimated_wind_direction_name') }}.
        Pressure: {{ state_attr('sensor.rnmca_home_area_weather', 'estimated_air_pressure_hpa') }} hPa.
```

---

### 5. Urgent Alert When Event Is Close and Approaching

Send a high-priority notification when the estimated arrival time of a detected event is under 30 minutes.

```yaml
alias: Imminent Air Quality Event
mode: single
trigger:
  - platform: template
    value_template: >-
      {{ states('sensor.rnmca_home_early_warning') in ['watch', 'warning']
         and state_attr('sensor.rnmca_home_early_warning', 'primary_eta_minutes') | int(999) < 30 }}
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🚨 Imminent Air Quality Event"
      message: >-
        ETA: {{ state_attr('sensor.rnmca_home_early_warning', 'primary_eta_minutes') }} minutes.
        {{ state_attr('sensor.rnmca_home_early_warning', 'top_event_summary') }}
        Direction: {{ state_attr('sensor.rnmca_home_early_warning', 'primary_direction_from_poi') }}.
      data:
        push:
          interruption-level: critical
```

---

## Automation Blueprint

An automation blueprint is available for quick setup of early-warning notifications without writing YAML manually.

**Import URL:**
```
https://raw.githubusercontent.com/HomeRiz/CalitateAer/refs/heads/main/blueprints/automation/calitateaer/early_warning_notification.yaml
```

The blueprint lets you select an early-warning sensor and a notification service. It sends a notification when the sensor transitions to `watch` or `warning`, including the top event summary, direction, and ETA where available.

> **Note:** This blueprint is a starting point and subject to change as the integration evolves. New options and more detailed customisation may be added or restructured in future versions. It is not guaranteed to remain in its current form.

---

## Documentation

| Document | Description |
|---|---|
| [API.md](API.md) | Detailed documentation on how this integration communicates with the RNMCA API servers — endpoints, data models, rate limits, and how area estimates are calculated |
| [TERMS_AND_CONDITIONS.md](TERMS_AND_CONDITIONS.md) | English summary and full reflection of the RNMCA API Terms and Conditions issued by MMAP |
| [PRIVACY_POLICY.md](PRIVACY_POLICY.md) | English summary and full reflection of the calitateaer.ro Privacy Policy issued by MMAP |

---

## Legal and Data Notes

- Data is provided by RNMCA through `calitateaer.ro` and is **informational and unofficial** in the context of this integration
- The official version of any data can only be obtained directly from the Furnizor (MMAP)
- Warning and ETA calculations are **heuristic estimates** — they are not official emergency alerts
- Keep your API credentials private and do not share them with third parties
- Respect API rate limits; exceeding them may result in temporary or permanent account suspension
- This integration is not affiliated with, endorsed by, or officially connected to MMAP or RNMCA

---

*Created by [HomeRiz](https://github.com/HomeRiz) · Built with the help of Claude Code and ChatGPT / Codex*
