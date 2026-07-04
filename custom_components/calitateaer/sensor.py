"""Sensor platform for RNMCA Air Quality."""
import datetime
import logging
import math
import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
    EntityCategory,
    PERCENTAGE,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LANGUAGE, CONF_LATITUDE, CONF_LONGITUDE, DEFAULT_LANGUAGE, DOMAIN

_LOGGER = logging.getLogger(__name__)

POLLUTANT_MAP = {
    1: {"name": "SO2", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    2: {"name": "NO2", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    3: {"name": "O3", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    4: {"name": "PM10", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:blur", "class": SensorDeviceClass.PM10},
    5: {"name": "PM2.5", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:blur", "class": SensorDeviceClass.PM25},
    6: {"name": "CO", "unit": CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": SensorDeviceClass.CO},
    7: {"name": "Benzene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    8: {"name": "Nitrogen Monoxide", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    9: {"name": "NOx", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    10: {"name": "Air Temperature", "unit": UnitOfTemperature.CELSIUS, "icon": "mdi:thermometer", "class": SensorDeviceClass.TEMPERATURE},
    11: {"name": "Relative Humidity", "unit": PERCENTAGE, "icon": "mdi:water-percent", "class": SensorDeviceClass.HUMIDITY},
    12: {"name": "Air Pressure", "unit": UnitOfPressure.HPA, "icon": "mdi:gauge", "class": SensorDeviceClass.PRESSURE},
    13: {"name": "Wind Speed", "unit": UnitOfSpeed.METERS_PER_SECOND, "icon": "mdi:wind-power", "class": SensorDeviceClass.WIND_SPEED},
    14: {"name": "Wind Direction", "unit": "deg", "icon": "mdi:compass-outline", "class": None},
    15: {"name": "Solar Radiation", "unit": "W/m2", "icon": "mdi:sun-wireless", "class": SensorDeviceClass.IRRADIANCE},
    16: {"name": "Precipitation", "unit": "mm", "icon": "mdi:weather-pouring", "class": SensorDeviceClass.PRECIPITATION},
    17: {"name": "H2S (Hydrogen Sulfide)", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:skull-scan", "class": None},
    18: {"name": "NH3 (Ammonia)", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:molecule", "class": None},
    19: {"name": "Toluene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:flask", "class": None},
    20: {"name": "o-Xylene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:flask", "class": None},
    21: {"name": "m-Xylene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:flask", "class": None},
    22: {"name": "p-Xylene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:flask", "class": None},
    23: {"name": "Ethylbenzene", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, "icon": "mdi:flask", "class": None},
}

SENSOR_LABELS = {
    "general_index": {
        "ro": "Indice general",
        "en": "General Index",
        "fr": "Indice general",
        "es": "Indice general",
        "it": "Indice generale",
        "de": "Gesamtindex",
    },
    "configured_location": {
        "ro": "Locatie configurata",
        "en": "Configured location",
        "fr": "Emplacement configure",
        "es": "Ubicacion configurada",
        "it": "Posizione configurata",
        "de": "Konfigurierter Standort",
    },
    "attribution": {
        "ro": "Date informative si gratuite furnizate de RNMCA (calitateaer.ro)",
        "en": "Informational free data provided by RNMCA (calitateaer.ro)",
        "fr": "Donnees informatives gratuites fournies par RNMCA (calitateaer.ro)",
        "es": "Datos informativos gratuitos proporcionados por RNMCA (calitateaer.ro)",
        "it": "Dati informativi gratuiti forniti da RNMCA (calitateaer.ro)",
        "de": "Kostenlose Informationsdaten von RNMCA (calitateaer.ro)",
    },
    "early_warning": {
        "ro": "Avertizare timpurie",
        "en": "Early Warning",
        "fr": "Alerte precoce",
        "es": "Alerta temprana",
        "it": "Allerta precoce",
        "de": "Fruhwarnung",
    },
    "national_stations": {
        "ro": "Statii nationale",
        "en": "National Stations",
        "fr": "Stations nationales",
        "es": "Estaciones nacionales",
        "it": "Stazioni nazionali",
        "de": "Nationale Stationen",
    },
    "weather_summary": {
        "ro": "Sumar meteo",
        "en": "Weather Summary",
        "fr": "Resume meteo",
        "es": "Resumen meteo",
        "it": "Riepilogo meteo",
        "de": "Wetteruebersicht",
    },
    "area_weather": {
        "ro": "Meteo estimat in zona",
        "en": "Estimated Area Weather",
        "fr": "Meteo estimee de la zone",
        "es": "Meteo estimada del area",
        "it": "Meteo stimato area",
        "de": "Geschaetztes Gebietswetter",
    },
    "area_estimate": {
        "ro": "Estimare zona",
        "en": "Area Estimate",
        "fr": "Estimation de zone",
        "es": "Estimacion de area",
        "it": "Stima area",
        "de": "Gebietsschaetzung",
    },
    "clear": {
        "ro": "clar",
        "en": "clear",
        "fr": "clair",
        "es": "despejado",
        "it": "chiaro",
        "de": "klar",
    },
    "watch": {
        "ro": "monitorizare",
        "en": "watch",
        "fr": "surveillance",
        "es": "vigilancia",
        "it": "monitoraggio",
        "de": "beobachtung",
    },
    "warning": {
        "ro": "avertizare",
        "en": "warning",
        "fr": "alerte",
        "es": "alerta",
        "it": "allerta",
        "de": "warnung",
    },
}

CARDINAL_DIRECTIONS = {
    "N": {"ro": "Nord", "en": "North", "fr": "Nord", "es": "Norte", "it": "Nord", "de": "Nord"},
    "NE": {"ro": "Nord-Est", "en": "North-East", "fr": "Nord-Est", "es": "Noreste", "it": "Nord-Est", "de": "Nordost"},
    "E": {"ro": "Est", "en": "East", "fr": "Est", "es": "Este", "it": "Est", "de": "Ost"},
    "SE": {"ro": "Sud-Est", "en": "South-East", "fr": "Sud-Est", "es": "Sureste", "it": "Sud-Est", "de": "Suedost"},
    "S": {"ro": "Sud", "en": "South", "fr": "Sud", "es": "Sur", "it": "Sud", "de": "Sued"},
    "SW": {"ro": "Sud-Vest", "en": "South-West", "fr": "Sud-Ouest", "es": "Suroeste", "it": "Sud-Ovest", "de": "Suedwest"},
    "W": {"ro": "Vest", "en": "West", "fr": "Ouest", "es": "Oeste", "it": "Ovest", "de": "West"},
    "NW": {"ro": "Nord-Vest", "en": "North-West", "fr": "Nord-Ouest", "es": "Noroeste", "it": "Nord-Ovest", "de": "Nordwest"},
}

WARNING_THRESHOLDS = {
    "pm10": {"watch": 35.0, "warning": 50.0},
    "pm2.5": {"watch": 15.0, "warning": 25.0},
    "pm25": {"watch": 15.0, "warning": 25.0},
    "no2": {"watch": 100.0, "warning": 200.0},
    "so2": {"watch": 125.0, "warning": 350.0},
    "o3": {"watch": 120.0, "warning": 180.0},
    "co": {"watch": 5.0, "warning": 10.0},
    "benzene": {"watch": 2.0, "warning": 5.0},
    "benzen": {"watch": 2.0, "warning": 5.0},
    "h2s": {"watch": 7.0, "warning": 15.0},
    "nh3": {"watch": 500.0, "warning": 1000.0},
    "wind_speed": {"watch": 10.8, "warning": 15.0},
    "solar_radiation": {"watch": 800.0, "warning": 1000.0},
    "air_temperature": {"watch": 35.0, "warning": 40.0},
}

MEASUREMENT_DISPLAY_PRECISION = 2

POLLUTANT_NAMES = {
    1: {"ro": "SO2", "en": "SO2", "fr": "SO2", "es": "SO2", "it": "SO2", "de": "SO2"},
    2: {"ro": "NO2", "en": "NO2", "fr": "NO2", "es": "NO2", "it": "NO2", "de": "NO2"},
    3: {"ro": "O3", "en": "O3", "fr": "O3", "es": "O3", "it": "O3", "de": "O3"},
    4: {"ro": "PM10", "en": "PM10", "fr": "PM10", "es": "PM10", "it": "PM10", "de": "PM10"},
    5: {"ro": "PM2.5", "en": "PM2.5", "fr": "PM2.5", "es": "PM2.5", "it": "PM2.5", "de": "PM2.5"},
    6: {"ro": "CO", "en": "CO", "fr": "CO", "es": "CO", "it": "CO", "de": "CO"},
    7: {"ro": "Benzen", "en": "Benzene", "fr": "Benzene", "es": "Benceno", "it": "Benzene", "de": "Benzol"},
    8: {
        "ro": "Monoxid de azot",
        "en": "Nitrogen Monoxide",
        "fr": "Monoxyde d'azote",
        "es": "Monoxido de nitrogeno",
        "it": "Monossido di azoto",
        "de": "Stickstoffmonoxid",
    },
    9: {"ro": "NOx", "en": "NOx", "fr": "NOx", "es": "NOx", "it": "NOx", "de": "NOx"},
    10: {
        "ro": "Temperatura aerului",
        "en": "Air Temperature",
        "fr": "Temperature de l'air",
        "es": "Temperatura del aire",
        "it": "Temperatura dell'aria",
        "de": "Lufttemperatur",
    },
    11: {
        "ro": "Umiditate relativa",
        "en": "Relative Humidity",
        "fr": "Humidite relative",
        "es": "Humedad relativa",
        "it": "Umidita relativa",
        "de": "Relative Luftfeuchtigkeit",
    },
    12: {
        "ro": "Presiune atmosferica",
        "en": "Air Pressure",
        "fr": "Pression atmospherique",
        "es": "Presion atmosferica",
        "it": "Pressione atmosferica",
        "de": "Luftdruck",
    },
    13: {
        "ro": "Viteza vantului",
        "en": "Wind Speed",
        "fr": "Vitesse du vent",
        "es": "Velocidad del viento",
        "it": "Velocita del vento",
        "de": "Windgeschwindigkeit",
    },
    14: {
        "ro": "Directia vantului",
        "en": "Wind Direction",
        "fr": "Direction du vent",
        "es": "Direccion del viento",
        "it": "Direzione del vento",
        "de": "Windrichtung",
    },
    15: {
        "ro": "Radiatie solara",
        "en": "Solar Radiation",
        "fr": "Rayonnement solaire",
        "es": "Radiacion solar",
        "it": "Radiazione solare",
        "de": "Sonnenstrahlung",
    },
    16: {
        "ro": "Precipitatii",
        "en": "Precipitation",
        "fr": "Precipitations",
        "es": "Precipitacion",
        "it": "Precipitazioni",
        "de": "Niederschlag",
    },
    17: {"ro": "H2S (Hidrogen sulfurat)", "en": "H2S (Hydrogen Sulfide)", "fr": "H2S (Sulfure d'hydrogene)", "es": "H2S (Sulfuro de hidrogeno)", "it": "H2S (Solfuro di idrogeno)", "de": "H2S (Schwefelwasserstoff)"},
    18: {"ro": "NH3 (Amoniac)", "en": "NH3 (Ammonia)", "fr": "NH3 (Ammoniac)", "es": "NH3 (Amoniaco)", "it": "NH3 (Ammoniaca)", "de": "NH3 (Ammoniak)"},
    19: {"ro": "Toluen", "en": "Toluene", "fr": "Toluene", "es": "Tolueno", "it": "Toluene", "de": "Toluol"},
    20: {"ro": "o-Xilen", "en": "o-Xylene", "fr": "o-Xylene", "es": "o-Xileno", "it": "o-Xilene", "de": "o-Xylol"},
    21: {"ro": "m-Xilen", "en": "m-Xylene", "fr": "m-Xylene", "es": "m-Xileno", "it": "m-Xilene", "de": "m-Xylol"},
    22: {"ro": "p-Xilen", "en": "p-Xylene", "fr": "p-Xylene", "es": "p-Xileno", "it": "p-Xilene", "de": "p-Xylol"},
    23: {"ro": "Etilbenzen", "en": "Ethylbenzene", "fr": "Ethylbenzene", "es": "Etilbenceno", "it": "Etilbenzene", "de": "Ethylbenzol"},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_entities = set()

    def discover_entities():
        """Add sensors for stations and newly discovered measurement wrappers."""
        sensors = []

        # One always-on sensor carrying every RNMCA station nationwide for the
        # CalitateAer Map Card (only when national map mode is enabled).
        if getattr(coordinator, "national_map", False) and ("national",) not in known_entities:
            known_entities.add(("national",))
            sensors.append(CalitateAerNationalStationsSensor(coordinator))

        for index, poi in enumerate(getattr(coordinator, "pois", []) or []):
            area_weather_key = ("area_weather", poi.get("id") or poi.get("name") or index)
            if area_weather_key not in known_entities:
                known_entities.add(area_weather_key)
                sensors.append(CalitateAerAreaWeatherSensor(coordinator, poi, index))

            warning_key = ("early_warning", poi.get("id") or poi.get("name") or index)
            if warning_key not in known_entities:
                known_entities.add(warning_key)
                sensors.append(CalitateAerEarlyWarningSensor(coordinator, poi, index))

            for parameter in _area_measurement_keys(coordinator.data or {}, poi):
                area_key = ("area_measurement", poi.get("id") or poi.get("name") or index, parameter["key"])
                if area_key not in known_entities:
                    known_entities.add(area_key)
                    sensors.append(
                        CalitateAerAreaMeasurementSensor(
                            coordinator,
                            poi,
                            index,
                            parameter["key"],
                            parameter["label"],
                            parameter.get("unit"),
                        )
                    )

        for location_id, location_data in (coordinator.data or {}).items():
            live_data = location_data.get("live_data", {})
            config_data = location_data.get("config", {})

            general_key = (location_id, "general")
            if general_key not in known_entities:
                known_entities.add(general_key)
                sensors.append(CalitateAerGeneralIndexSensor(coordinator, location_id, config_data))

            weather_key = (location_id, "weather_summary")
            if weather_key not in known_entities and _has_weather_measurement(config_data):
                known_entities.add(weather_key)
                sensors.append(CalitateAerWeatherSummarySensor(coordinator, location_id, config_data))

            for measurement in _measurement_configs(config_data):
                measurement_id = measurement.get("id")
                sensor_key = (location_id, "measurement", measurement_id)
                if measurement_id is not None and sensor_key not in known_entities:
                    known_entities.add(sensor_key)
                    sensors.append(
                        CalitateAerMeasurementSensor(
                            coordinator,
                            location_id,
                            measurement,
                            config_data,
                        )
                    )

            if not _measurement_configs(config_data):
                for wrapper in _specific_wrappers(live_data):
                    specific_id = _specific_id(wrapper)
                    sensor_key = (location_id, specific_id)
                    if specific_id is not None and sensor_key not in known_entities:
                        known_entities.add(sensor_key)
                        sensors.append(
                            CalitateAerPollutantSensor(coordinator, location_id, specific_id, config_data)
                        )

        if sensors:
            async_add_entities(sensors, True)

    discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(discover_entities))


class CalitateAerGeneralIndexSensor(CoordinatorEntity, SensorEntity):
    """Representation of a station's general air quality index."""

    def __init__(self, coordinator, location_id, config_data):
        """Initialize the general index sensor."""
        super().__init__(coordinator)
        self.location_id = location_id
        self.config_data = config_data
        self.language = _language(coordinator)

        station_name = _station_name(self.config_data, location_id)
        poi_name = _poi_name(self.config_data, self.language)
        general_index = _label("general_index", self.language)
        unique_location_id = _unique_location_id(location_id)

        self._attr_name = f"RNMCA {poi_name} {station_name} {general_index}"
        self._attr_unique_id = f"rnmca_{unique_location_id}_general_index"
        self._attr_icon = "mdi:air-filter"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self):
        """Return station device information."""
        return _station_device_info(self.config_data, self.location_id, self.language)

    @property
    def native_value(self):
        """Extract the general index code."""
        try:
            location_data = self.coordinator.data.get(self.location_id, {}).get("live_data", {})
            latest_group = _latest_timestamp_group(location_data)
            if latest_group:
                return (latest_group.get("hourlyGeneralIndex") or {}).get("code")
            general_values = location_data.get("generalIndexHourlyValues", [])
            if general_values:
                return _index_code(general_values[0])
        except (KeyError, IndexError):
            pass
        return None

    @property
    def extra_state_attributes(self):
        """Return coordinates, metadata, and measurement time."""
        attributes = _base_attributes(self.config_data, self.language)

        try:
            location_data = self.coordinator.data.get(self.location_id, {}).get("live_data", {})
            latest_group = _latest_timestamp_group(location_data)
            if latest_group:
                attributes["measurement_time"] = latest_group.get("dateTime")
                general_index = latest_group.get("hourlyGeneralIndex") or {}
                if general_index:
                    attributes["quality_index_name"] = general_index.get("codeName")
                    attributes["quality_index_valid"] = general_index.get("valid")
                    attributes["specific_index_name"] = general_index.get("specificIndexName")
                    attributes["specific_index_used_value"] = general_index.get("specificIndexUsedValue")
            general_values = location_data.get("generalIndexHourlyValues", [])
            if general_values:
                _add_measurement_time(attributes, general_values[0])
        except (KeyError, IndexError):
            pass

        return attributes


class CalitateAerPollutantSensor(CoordinatorEntity, SensorEntity):
    """Representation of a specific pollutant or weather sensor."""

    def __init__(self, coordinator, location_id, specific_id, config_data):
        """Initialize the specific sensor."""
        super().__init__(coordinator)
        self.location_id = location_id
        self.specific_id = specific_id
        self.config_data = config_data
        self.language = _language(coordinator)

        meta = POLLUTANT_MAP.get(specific_id, {
            "name": f"Sensor {specific_id}",
            "unit": None,
            "icon": "mdi:chart-bell-curve",
            "class": None,
        })

        station_name = _station_name(self.config_data, location_id)
        poi_name = _poi_name(self.config_data, self.language)
        sensor_name = _pollutant_name(specific_id, self.language, meta["name"])
        unique_location_id = _unique_location_id(location_id)

        self._attr_name = f"RNMCA {poi_name} {station_name} {sensor_name}"
        self._attr_unique_id = f"rnmca_{unique_location_id}_sensor_{specific_id}"
        self._attr_icon = meta["icon"]
        self._attr_native_unit_of_measurement = meta["unit"]
        self._attr_device_class = meta["class"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = MEASUREMENT_DISPLAY_PRECISION
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self):
        """Return station device information."""
        return _station_device_info(self.config_data, self.location_id, self.language)

    @property
    def native_value(self):
        """Return the measurement value."""
        try:
            for wrapper in self._wrappers():
                if _specific_id(wrapper) == self.specific_id:
                    values = _hourly_values(wrapper)
                    if values:
                        return _display_value(_measurement_value(values[0]))
        except (KeyError, IndexError):
            pass
        return None

    @property
    def extra_state_attributes(self):
        """Return map attributes, index codes, and measurement time."""
        attributes = _base_attributes(self.config_data, self.language)
        attributes["station_type"] = self.config_data.get("info", {}).get("areaType")

        try:
            for wrapper in self._wrappers():
                if _specific_id(wrapper) == self.specific_id:
                    values = _hourly_values(wrapper)
                    if values:
                        code = _index_code(values[0])
                        if code is not None:
                            attributes["quality_index_code"] = code
                        _add_measurement_time(attributes, values[0])
        except (KeyError, IndexError):
            pass

        return attributes

    def _wrappers(self):
        """Return specific wrappers for this station."""
        location_data = self.coordinator.data.get(self.location_id, {}).get("live_data", {})
        return _specific_wrappers(location_data)


class CalitateAerMeasurementSensor(CoordinatorEntity, SensorEntity):
    """Representation of a simplified API measurement value sensor."""

    def __init__(self, coordinator, location_id, measurement, config_data):
        """Initialize the measurement sensor."""
        super().__init__(coordinator)
        self.location_id = location_id
        self.measurement = measurement
        self.measurement_id = measurement.get("id")
        self.config_data = config_data
        self.language = _language(coordinator)
        self._cached_value = None
        self._cached_value_time = None

        station_name = _station_name(config_data, location_id)
        poi_name = _poi_name(config_data, self.language)
        parameter_name = _measurement_label(measurement)
        unique_location_id = _unique_location_id(location_id)

        self._attr_name = f"RNMCA {poi_name} {station_name} {parameter_name}"
        self._attr_unique_id = f"rnmca_{unique_location_id}_measurement_{self.measurement_id}"
        self._attr_icon = _measurement_icon(parameter_name)
        self._attr_native_unit_of_measurement = _measurement_unit(measurement)
        self._attr_device_class = _measurement_device_class(parameter_name)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = MEASUREMENT_DISPLAY_PRECISION
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self):
        """Return station device information."""
        return _station_device_info(self.config_data, self.location_id, self.language)

    @property
    def native_value(self):
        """Return the latest simplified measurement value, or the last valid reading."""
        latest_value = self._latest_value()
        if latest_value is not None:
            if not latest_value.get("valid", True):
                return None
            fresh = _display_value(latest_value.get("usedValue"))
            if fresh is not None:
                self._cached_value = fresh
                latest_group = _latest_timestamp_group(
                    self.coordinator.data.get(self.location_id, {}).get("live_data", {})
                )
                self._cached_value_time = (latest_group or {}).get("dateTime")
            return fresh
        return self._cached_value

    @property
    def extra_state_attributes(self):
        """Return metadata and quality index information."""
        attributes = _base_attributes(self.config_data, self.language)
        attributes.update({
            "measurement_id": self.measurement_id,
            "measurement_name": self.measurement.get("name"),
            "measurement_description": self.measurement.get("description"),
            "measurement_value_type": self.measurement.get("measurementValueType"),
            "measurement_value_subtype": self.measurement.get("measurementValueSubtype"),
            "interval_between_values": self.measurement.get("intervalBetweenValues"),
            "measurement": self.measurement.get("measurementName"),
            "parameter": self.measurement.get("parameter"),
            "measurement_unit": self.measurement.get("measurementUnit"),
            "specific_quality_index_id": self.measurement.get("qualityIndexSpecificId"),
        })

        latest_group = _latest_timestamp_group(self.coordinator.data.get(self.location_id, {}).get("live_data", {}))
        latest_value = self._latest_value()
        if latest_group:
            attributes["measurement_time"] = latest_group.get("dateTime")
        if latest_value:
            attributes["valid"] = latest_value.get("valid")
            attributes["qaqc_state"] = latest_value.get("qaqcState")
            attributes["qaqc_status"] = latest_value.get("qaqcStatus")
            specific_index = latest_value.get("hourlySpecificIndex") or {}
            if specific_index:
                attributes["quality_index_code"] = specific_index.get("code")
                attributes["quality_index_name"] = specific_index.get("codeName")
                attributes["quality_index_valid"] = specific_index.get("valid")
        if self._cached_value is not None and latest_value is None:
            attributes["last_valid_reading_time"] = self._cached_value_time
            attributes["value_source"] = "cached_last_valid"
        else:
            attributes["value_source"] = "live"

        return attributes

    def _latest_value(self):
        """Return the latest matching measurement value data element."""
        live_data = self.coordinator.data.get(self.location_id, {}).get("live_data", {})
        latest_group = _latest_timestamp_group(live_data)
        if not latest_group:
            return None

        expected_name = self.measurement.get("name")
        expected_parameter = self.measurement.get("parameter")
        expected_unit = self.measurement.get("measurementUnit")
        for value_data in latest_group.get("measurementValuesData", []) or []:
            if _matches_measurement(value_data, expected_name, expected_parameter, expected_unit):
                return value_data
        return None


class CalitateAerWeatherSummarySensor(CoordinatorEntity, SensorEntity):
    """Representation of combined station weather data for automations."""

    def __init__(self, coordinator, location_id, config_data):
        """Initialize the weather summary sensor."""
        super().__init__(coordinator)
        self.location_id = location_id
        self.config_data = config_data
        self.language = _language(coordinator)

        station_name = _station_name(config_data, location_id)
        poi_name = _poi_name(config_data, self.language)
        weather_summary = _label("weather_summary", self.language)
        unique_location_id = _unique_location_id(location_id)

        self._attr_name = f"RNMCA {poi_name} {station_name} {weather_summary}"
        self._attr_unique_id = f"rnmca_{unique_location_id}_weather_summary"
        self._attr_icon = "mdi:weather-windy"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self):
        """Return station device information."""
        return _station_device_info(self.config_data, self.location_id, self.language)

    @property
    def native_value(self):
        """Return the current wind sector as a compact state."""
        weather = _station_weather_values(self.coordinator.data.get(self.location_id, {}).get("live_data", {}))
        direction = weather.get("wind_direction_degrees")
        if direction is not None:
            return _compass16(direction)
        if weather.get("wind_speed_mps") is not None or weather.get("air_pressure_hpa") is not None:
            return "available"
        return None

    @property
    def extra_state_attributes(self):
        """Return combined wind and pressure details."""
        attributes = _base_attributes(self.config_data, self.language)
        live_data = self.coordinator.data.get(self.location_id, {}).get("live_data", {})
        latest_group = _latest_timestamp_group(live_data)
        weather = _station_weather_values(live_data)

        direction_degrees = weather.get("wind_direction_degrees")
        speed_mps = weather.get("wind_speed_mps")
        pressure_hpa = weather.get("air_pressure_hpa")

        attributes.update({
            "measurement_time": latest_group.get("dateTime") if latest_group else None,
            "wind_speed_mps": speed_mps,
            "wind_speed_kmh": _rounded(speed_mps * 3.6, 2) if speed_mps is not None else None,
            "wind_speed_band": _wind_speed_band(speed_mps),
            "wind_direction_degrees": direction_degrees,
            "wind_direction_cardinal": _compass16(direction_degrees) if direction_degrees is not None else None,
            "wind_direction_name": _cardinal(direction_degrees, self.language) if direction_degrees is not None else None,
            "air_pressure_hpa": pressure_hpa,
            "pressure_change_hint": "Use Home Assistant statistics/trend helpers for pressure tendency automations.",
            "automation_examples": [
                "numeric_state on attribute wind_speed_mps above 10.8 for strong wind watch",
                "template condition on wind_direction_cardinal for incoming direction",
                "template condition on air_pressure_hpa or a HA trend helper for pressure drops",
            ],
        })
        return attributes


class CalitateAerAreaWeatherSensor(CoordinatorEntity, SensorEntity):
    """Representation of estimated weather for a monitored point."""

    def __init__(self, coordinator, poi, index):
        """Initialize the estimated area weather sensor."""
        super().__init__(coordinator)
        self.poi = poi
        self.index = index
        self.language = _language(coordinator)

        poi_name = poi.get("name") or _label("configured_location", self.language)
        unique_poi_id = _unique_location_id(poi.get("id") or poi_name or index)
        self._attr_name = f"RNMCA {poi_name} {_label('area_weather', self.language)}"
        self._attr_unique_id = f"rnmca_{unique_poi_id}_area_weather"
        self._attr_icon = "mdi:weather-windy"

    @property
    def device_info(self):
        """Return monitored point device information."""
        return _poi_device_info(self.poi, self.index, self.language)

    @property
    def native_value(self):
        """Return the estimated wind sector."""
        report = _area_weather_report(self.coordinator.data or {}, self.poi, self.language)
        if report.get("wind_direction_cardinal"):
            return report.get("wind_direction_cardinal")
        if report.get("wind_speed_mps") is not None or report.get("air_pressure_hpa") is not None:
            return "available"
        return None

    @property
    def extra_state_attributes(self):
        """Return estimated wind and pressure attributes."""
        report = _area_weather_report(self.coordinator.data or {}, self.poi, self.language)
        return {
            "monitored_point": self.poi.get("name"),
            "monitored_point_latitude": self.poi.get(CONF_LATITUDE),
            "monitored_point_longitude": self.poi.get(CONF_LONGITUDE),
            "estimated_wind_speed_mps": report.get("wind_speed_mps"),
            "estimated_wind_speed_kmh": report.get("wind_speed_kmh"),
            "estimated_wind_speed_band": report.get("wind_speed_band"),
            "estimated_wind_direction_degrees": report.get("wind_direction_degrees"),
            "estimated_wind_direction_cardinal": report.get("wind_direction_cardinal"),
            "estimated_wind_direction_name": report.get("wind_direction_name"),
            "estimated_air_pressure_hpa": report.get("air_pressure_hpa"),
            "wind_station_count": report.get("wind_station_count"),
            "pressure_station_count": report.get("pressure_station_count"),
            "nearest_station_distance_km": report.get("nearest_station_distance_km"),
            "farthest_station_distance_km": report.get("farthest_station_distance_km"),
            "latest_measurement_time": report.get("latest_measurement_time"),
            "contributing_stations": report.get("contributing_stations"),
            "method": report.get("method"),
            "attribution": _label("attribution", self.language),
        }


class CalitateAerAreaMeasurementSensor(CoordinatorEntity, SensorEntity):
    """Representation of an estimated area value for one parameter."""

    def __init__(self, coordinator, poi, index, parameter_key, parameter_label, unit):
        """Initialize the estimated area measurement sensor."""
        super().__init__(coordinator)
        self.poi = poi
        self.index = index
        self.parameter_key = parameter_key
        self.parameter_label = parameter_label
        self.language = _language(coordinator)
        self._cached_value = None
        self._cached_report = {}

        poi_name = poi.get("name") or _label("configured_location", self.language)
        unique_poi_id = _unique_location_id(poi.get("id") or poi_name or index)
        unique_parameter = _unique_location_id(parameter_key)
        area_estimate = _label("area_estimate", self.language)

        self._attr_name = f"RNMCA {poi_name} {area_estimate} {parameter_label}"
        self._attr_unique_id = f"rnmca_{unique_poi_id}_area_{unique_parameter}"
        self._attr_icon = _measurement_icon(parameter_label)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = _measurement_device_class(parameter_label)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = MEASUREMENT_DISPLAY_PRECISION

    @property
    def device_info(self):
        """Return monitored point device information."""
        return _poi_device_info(self.poi, self.index, self.language)

    @property
    def native_value(self):
        """Return the estimated area value, or the last valid estimate."""
        report = _area_measurement_report(self.coordinator.data or {}, self.poi, self.parameter_key)
        value = report.get("value")
        if value is not None:
            self._cached_value = value
            self._cached_report = report
        return value if value is not None else self._cached_value

    @property
    def extra_state_attributes(self):
        """Return aggregate details and source stations."""
        report = _area_measurement_report(self.coordinator.data or {}, self.poi, self.parameter_key)
        active = report if report.get("value") is not None else self._cached_report
        return {
            "parameter": self.parameter_label,
            "monitored_point": self.poi.get("name"),
            "monitored_point_latitude": self.poi.get(CONF_LATITUDE),
            "monitored_point_longitude": self.poi.get(CONF_LONGITUDE),
            "station_count": active.get("station_count"),
            "nearest_station_distance_km": active.get("nearest_station_distance_km"),
            "farthest_station_distance_km": active.get("farthest_station_distance_km"),
            "minimum_value": active.get("minimum_value"),
            "maximum_value": active.get("maximum_value"),
            "latest_measurement_time": active.get("latest_measurement_time"),
            "contributing_stations": active.get("contributing_stations"),
            "method": active.get("method"),
            "value_source": "live" if report.get("value") is not None else "cached_last_valid",
            "attribution": _label("attribution", self.language),
        }


class CalitateAerEarlyWarningSensor(CoordinatorEntity, SensorEntity):
    """Representation of a monitored point early-warning summary."""

    def __init__(self, coordinator, poi, index):
        """Initialize the early-warning sensor."""
        super().__init__(coordinator)
        self.poi = poi
        self.index = index
        self.language = _language(coordinator)

        poi_name = poi.get("name") or _label("configured_location", self.language)
        unique_poi_id = _unique_location_id(poi.get("id") or poi_name or index)
        self._attr_name = f"RNMCA {poi_name} {_label('early_warning', self.language)}"
        self._attr_unique_id = f"rnmca_{unique_poi_id}_early_warning"
        self._attr_icon = "mdi:alert-decagram"

    @property
    def device_info(self):
        """Return monitored point device information."""
        return _poi_device_info(self.poi, self.index, self.language)

    @property
    def native_value(self):
        """Return the overall warning state for this monitored point."""
        return _build_warning_report(self.coordinator.data or {}, self.poi, self.language)["state"]

    @property
    def extra_state_attributes(self):
        """Return warning details suitable for notifications and dashboards."""
        report = _build_warning_report(self.coordinator.data or {}, self.poi, self.language)
        return {
            "state_key": report["state"],
            "state_label": _label(report["state"], self.language),
            "monitored_point": self.poi.get("name"),
            "monitored_point_latitude": self.poi.get(CONF_LATITUDE),
            "monitored_point_longitude": self.poi.get(CONF_LONGITUDE),
            "event_count": len(report["events"]),
            "warning_count": report["warning_count"],
            "watch_count": report["watch_count"],
            "nearest_event_distance_km": report["nearest_event_distance_km"],
            "primary_direction_from_poi": report["primary_direction_from_poi"],
            "primary_eta_minutes": report["primary_eta_minutes"],
            "top_event_summary": report["top_event_summary"],
            "events": report["events"],
            "automation_hint": (
                "Trigger when state_key is warning or watch. Use top_event_summary, "
                "primary_direction_from_poi, and primary_eta_minutes in notifications."
            ),
            "attribution": _label("attribution", self.language),
        }


class CalitateAerNationalStationsSensor(CoordinatorEntity, SensorEntity):
    """All RNMCA stations nationwide, exposed for the CalitateAer Map Card.

    This single always-on entity carries a compact per-station array in its
    attributes (coordinates, AQI, and curated readings) built once per poll
    from a single root-network API call. It is the data source the map card
    reads to plot every station across the country.

    Note: the ``stations`` attribute can be sizeable (~40 KB for ~186
    stations). Excluding this entity from the recorder is recommended; see the
    map card README.
    """

    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator):
        """Initialize the national stations sensor."""
        super().__init__(coordinator)
        self.language = _language(coordinator)
        self._attr_name = f"RNMCA {_label('national_stations', self.language)}"
        self._attr_unique_id = "rnmca_national_stations"
        self._attr_icon = "mdi:map-marker-multiple"

    @property
    def device_info(self):
        """Group the national sensor under its own device."""
        return {
            "identifiers": {(DOMAIN, "national")},
            "name": "RNMCA National",
            "manufacturer": "RNMCA",
            "model": "CalitateAer national map",
        }

    @property
    def native_value(self):
        """Return the number of stations that currently have data."""
        payload = getattr(self.coordinator, "national_payload", {}) or {}
        return payload.get("with_data_count")

    @property
    def extra_state_attributes(self):
        """Return the compact national-stations payload for the map card."""
        payload = getattr(self.coordinator, "national_payload", {}) or {}
        return {
            "station_count": payload.get("station_count", 0),
            "with_data_count": payload.get("with_data_count", 0),
            "updated": payload.get("updated"),
            "units": payload.get("units", {}),
            "stations": payload.get("stations", []),
            "attribution": _label("attribution", self.language),
        }


def _specific_wrappers(live_data):
    """Return specific pollutant wrappers from known API response shapes."""
    return (
        live_data.get("specificIndexHourlyValuesWrappers")
        or live_data.get("specificIndexHourlyValueWrappers")
        or live_data.get("specificIndexes")
        or []
    )


def _measurement_configs(config_data):
    """Return simplified measurement value definitions from station config."""
    return config_data.get("info", {}).get("measurementValues") or []


def _has_weather_measurement(config_data):
    """Return true when a station exposes wind or pressure data."""
    for measurement in _measurement_configs(config_data):
        kind = _parameter_kind(_measurement_label(measurement))
        if kind in ("wind_speed", "wind_direction", "air_pressure"):
            return True
    return False


def _area_measurement_keys(data, poi):
    """Return unique measurement parameters available for a monitored point."""
    parameters = {}
    for location_data in data.values():
        config_data = location_data.get("config", {})
        if not _poi_matches(config_data.get("poi", {}), poi):
            continue

        for measurement in _measurement_configs(config_data):
            _add_area_measurement_key(parameters, measurement)

        latest_group = _latest_timestamp_group(location_data.get("live_data", {}))
        for measurement in (latest_group or {}).get("measurementValuesData", []) or []:
            _add_area_measurement_key(parameters, measurement)

    return sorted(parameters.values(), key=lambda item: item["label"])


def _add_area_measurement_key(parameters, measurement):
    """Add one area parameter key from either config or live measurement data."""
    label = _measurement_label(measurement)
    key = _parameter_key(label)
    if key not in parameters:
        parameters[key] = {
            "key": key,
            "label": label,
            "unit": _measurement_unit(measurement),
        }


def _latest_timestamp_group(live_data):
    """Return the most recent simplified timestamp group."""
    timestamp_groups = live_data.get("locationDataForTimestamps") or []
    if not timestamp_groups:
        return None
    return timestamp_groups[0]


def _matches_measurement(value_data, expected_name, expected_parameter, expected_unit):
    """Match simplified data values to their config definition."""
    if expected_name and value_data.get("measurementValueName") == expected_name:
        return True
    return (
        expected_parameter
        and value_data.get("parameter") == expected_parameter
        and (not expected_unit or value_data.get("measurementUnit") == expected_unit)
    )


def _measurement_label(measurement):
    """Return the friendly measurement label from simplified config."""
    return (
        measurement.get("parameter")
        or measurement.get("name")
        or measurement.get("measurementValueName")
        or f"Measurement {measurement.get('id')}"
    )


def _measurement_unit(measurement):
    """Return the measurement unit from simplified config."""
    unit = measurement.get("measurementUnit")
    unit_text = str(unit or "")
    unit_ascii = (
        unit_text.replace("³", "3")
        .replace("²", "2")
        .replace("Â³", "3")
        .replace("Â²", "2")
        .lower()
    )
    if unit_text.endswith("°") or unit_text.endswith("Â°"):
        return "deg"
    if unit_ascii in ("µg/m3", "ug/m3", "Âµg/m3"):
        return CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    if unit_ascii == "mg/m3":
        return CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
    if unit_ascii == "w/m2":
        return "W/m2"
    if unit == "°":
        return "deg"
    if unit == "m3":
        return "m3"
    return unit


def _measurement_icon(parameter_name):
    """Return an icon based on the measured parameter."""
    normalized = parameter_name.lower()
    if "temperature" in normalized or "temperatura" in normalized:
        return "mdi:thermometer"
    if "humidity" in normalized or "umiditate" in normalized:
        return "mdi:water-percent"
    if "pressure" in normalized or "presiune" in normalized:
        return "mdi:gauge"
    if "wind" in normalized or "vant" in normalized:
        return "mdi:weather-windy"
    if "precip" in normalized:
        return "mdi:weather-pouring"
    if "solar" in normalized or "radiatie" in normalized:
        return "mdi:white-balance-sunny"
    if "pm" in normalized:
        return "mdi:blur"
    return "mdi:molecule"


def _measurement_device_class(parameter_name):
    """Return a Home Assistant device class for known simplified parameters."""
    normalized = _normalized_parameter(parameter_name)
    if "temperature" in normalized or "temperatura" in normalized:
        return SensorDeviceClass.TEMPERATURE
    if "humidity" in normalized or "umiditate" in normalized:
        return SensorDeviceClass.HUMIDITY
    if "pressure" in normalized or "presiune" in normalized:
        return SensorDeviceClass.PRESSURE
    if _parameter_kind(normalized) == "wind_speed":
        return SensorDeviceClass.WIND_SPEED
    if "precip" in normalized:
        return SensorDeviceClass.PRECIPITATION
    if "solar" in normalized or "radiatie" in normalized:
        return SensorDeviceClass.IRRADIANCE
    if normalized in ("pm10", "pm 10"):
        return SensorDeviceClass.PM10
    if normalized in ("pm2.5", "pm25", "pm 2.5"):
        return SensorDeviceClass.PM25
    if normalized == "co":
        return SensorDeviceClass.CO
    return None


def _station_weather_values(live_data):
    """Return wind and pressure values from the latest station timestamp."""
    latest_group = _latest_timestamp_group(live_data)
    values = latest_group.get("measurementValuesData", []) if latest_group else []
    weather = {
        "wind_speed_mps": None,
        "wind_direction_degrees": None,
        "air_pressure_hpa": None,
    }
    for value_data in values or []:
        if not value_data.get("valid", True):
            continue
        value = _float_or_none(value_data.get("usedValue", value_data.get("value")))
        if value is None:
            continue
        kind = _parameter_kind(value_data.get("parameter") or value_data.get("measurementValueName"))
        if kind == "wind_speed":
            weather["wind_speed_mps"] = value
        elif kind == "wind_direction":
            weather["wind_direction_degrees"] = value % 360
        elif kind == "air_pressure":
            weather["air_pressure_hpa"] = value
    return weather


def _area_weather_report(data, poi, language):
    """Estimate wind vector and pressure around a monitored point."""
    wind_components = []
    pressure_values = []
    stations = []
    latest_time = None

    for location_id, location_data in data.items():
        config_data = location_data.get("config", {})
        if not _poi_matches(config_data.get("poi", {}), poi):
            continue

        live_data = location_data.get("live_data", {})
        latest_group = _latest_timestamp_group(live_data)
        weather = _station_weather_values(live_data)
        distance = _float_or_none(config_data.get("distance"))
        station_name = _station_name(config_data, location_id)
        weight = _distance_weight(distance)
        latest_time = _latest_time(latest_time, latest_group.get("dateTime") if latest_group else None)

        speed = weather.get("wind_speed_mps")
        direction = weather.get("wind_direction_degrees")
        pressure = weather.get("air_pressure_hpa")

        station_entry = {
            "station": station_name,
            "distance_km": _rounded(distance, 2),
            "wind_speed_mps": _rounded(speed, 2),
            "wind_direction_degrees": _rounded(direction, 1),
            "air_pressure_hpa": _rounded(pressure, 2),
        }

        if speed is not None and direction is not None:
            travel_direction = (direction + 180.0) % 360.0
            radians = math.radians(travel_direction)
            wind_components.append({
                "x": math.sin(radians) * speed,
                "y": math.cos(radians) * speed,
                "weight": weight,
            })
            stations.append(station_entry)

        if pressure is not None:
            pressure_values.append({"value": pressure, "weight": weight, "distance": distance})
            if station_entry not in stations:
                stations.append(station_entry)

    wind_speed = None
    wind_from_direction = None
    if wind_components:
        weight_sum = sum(item["weight"] for item in wind_components)
        x = sum(item["x"] * item["weight"] for item in wind_components) / weight_sum
        y = sum(item["y"] * item["weight"] for item in wind_components) / weight_sum
        wind_speed = math.sqrt(x * x + y * y)
        travel_direction = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
        wind_from_direction = (travel_direction + 180.0) % 360.0

    pressure = _weighted_average(pressure_values)
    distances = [
        item.get("distance_km")
        for item in stations
        if item.get("distance_km") is not None
    ]
    return {
        "wind_speed_mps": _rounded(wind_speed, 2),
        "wind_speed_kmh": _rounded(wind_speed * 3.6, 2) if wind_speed is not None else None,
        "wind_speed_band": _wind_speed_band(wind_speed),
        "wind_direction_degrees": _rounded(wind_from_direction, 1),
        "wind_direction_cardinal": _compass16(wind_from_direction) if wind_from_direction is not None else None,
        "wind_direction_name": _cardinal(wind_from_direction, language) if wind_from_direction is not None else None,
        "air_pressure_hpa": _rounded(pressure, 2),
        "wind_station_count": len(wind_components),
        "pressure_station_count": len(pressure_values),
        "nearest_station_distance_km": min(distances) if distances else None,
        "farthest_station_distance_km": max(distances) if distances else None,
        "latest_measurement_time": latest_time,
        "contributing_stations": stations[:15],
        "method": "inverse_distance_weighted_area_estimate",
    }


def _area_measurement_report(data, poi, parameter_key):
    """Estimate one parameter around a monitored point."""
    values = []
    latest_time = None

    for location_id, location_data in data.items():
        config_data = location_data.get("config", {})
        if not _poi_matches(config_data.get("poi", {}), poi):
            continue

        latest_group = _latest_timestamp_group(location_data.get("live_data", {}))
        if not latest_group:
            continue

        distance = _float_or_none(config_data.get("distance"))
        weight = _distance_weight(distance)
        latest_time = _latest_time(latest_time, latest_group.get("dateTime"))
        for value_data in latest_group.get("measurementValuesData", []) or []:
            if not value_data.get("valid", True):
                continue
            if _parameter_key(value_data.get("parameter") or value_data.get("measurementValueName")) != parameter_key:
                continue
            value = _float_or_none(value_data.get("usedValue", value_data.get("value")))
            if value is None:
                continue
            values.append({
                "value": value,
                "weight": weight,
                "distance": distance,
                "station": _station_name(config_data, location_id),
                "measurement_time": latest_group.get("dateTime"),
            })

    estimate = _weighted_average(values)
    distances = [
        _rounded(item["distance"], 2)
        for item in values
        if item.get("distance") is not None
    ]
    raw_values = [item["value"] for item in values]
    return {
        "value": _rounded(estimate, 3),
        "station_count": len(values),
        "nearest_station_distance_km": min(distances) if distances else None,
        "farthest_station_distance_km": max(distances) if distances else None,
        "minimum_value": _rounded(min(raw_values), 3) if raw_values else None,
        "maximum_value": _rounded(max(raw_values), 3) if raw_values else None,
        "latest_measurement_time": latest_time,
        "contributing_stations": [
            {
                "station": item["station"],
                "value": _rounded(item["value"], 3),
                "distance_km": _rounded(item["distance"], 2),
                "measurement_time": item["measurement_time"],
            }
            for item in sorted(values, key=lambda item: item["distance"] if item["distance"] is not None else 999999)[:15]
        ],
        "method": "inverse_distance_weighted_area_estimate",
    }


def _build_warning_report(data, poi, language):
    """Build a compact early-warning report for one monitored point."""
    events = []
    station_ids = {"warning": set(), "watch": set()}

    for location_id, location_data in data.items():
        config_data = location_data.get("config", {})
        if not _poi_matches(config_data.get("poi", {}), poi):
            continue

        live_data = location_data.get("live_data", {})
        latest_group = _latest_timestamp_group(live_data)
        if not latest_group:
            continue

        station_info = config_data.get("info", {})
        station_lat = _float_or_none(station_info.get("latitude"))
        station_lon = _float_or_none(station_info.get("longitude"))
        poi_lat = _float_or_none(poi.get(CONF_LATITUDE))
        poi_lon = _float_or_none(poi.get(CONF_LONGITUDE))
        distance_km = _float_or_none(config_data.get("distance"))
        if distance_km is None and None not in (poi_lat, poi_lon, station_lat, station_lon):
            distance_km = _distance_km(poi_lat, poi_lon, station_lat, station_lon)

        wind = _find_station_wind(latest_group.get("measurementValuesData", []) or [])
        direction_from_poi = None
        bearing_to_station = None
        if None not in (poi_lat, poi_lon, station_lat, station_lon):
            bearing_to_station = _bearing(poi_lat, poi_lon, station_lat, station_lon)
            direction_from_poi = _cardinal(bearing_to_station, language)

        for value_data in latest_group.get("measurementValuesData", []) or []:
            event = _classify_event(value_data)
            if not event:
                continue

            event.update({
                "station": _station_name(config_data, location_id),
                "station_id": config_data.get("station_id"),
                "network_id": config_data.get("network_id"),
                "distance_km": _rounded(distance_km, 2),
                "direction_from_monitored_point": direction_from_poi,
                "bearing_from_monitored_point": _rounded(bearing_to_station, 1),
                "measurement_time": latest_group.get("dateTime"),
                "wind_speed_mps": _rounded(wind.get("speed_mps"), 2),
                "wind_direction_degrees": _rounded(wind.get("direction_degrees"), 1),
                "moving_toward_monitored_point": False,
                "eta_minutes": None,
            })

            eta = _eta_minutes(
                station_lat,
                station_lon,
                poi_lat,
                poi_lon,
                distance_km,
                wind.get("speed_mps"),
                wind.get("direction_degrees"),
            )
            if eta is not None:
                event["moving_toward_monitored_point"] = True
                event["eta_minutes"] = eta

            events.append(event)
            station_id = config_data.get("station_id") or location_id
            station_ids[event["severity"]].add(station_id)

    events.sort(key=lambda event: (
        0 if event["severity"] == "warning" else 1,
        event.get("distance_km") if event.get("distance_km") is not None else 999999,
    ))

    warning_count = sum(1 for event in events if event["severity"] == "warning")
    watch_count = sum(1 for event in events if event["severity"] == "watch")
    if warning_count or len(station_ids["watch"]) >= 2:
        state = "warning"
    elif watch_count:
        state = "watch"
    else:
        state = "clear"

    top_event = events[0] if events else None
    return {
        "state": state,
        "events": events[:15],
        "warning_count": warning_count,
        "watch_count": watch_count,
        "nearest_event_distance_km": top_event.get("distance_km") if top_event else None,
        "primary_direction_from_poi": top_event.get("direction_from_monitored_point") if top_event else None,
        "primary_eta_minutes": top_event.get("eta_minutes") if top_event else None,
        "top_event_summary": _event_summary(top_event) if top_event else None,
    }


def _classify_event(value_data):
    """Classify a simplified measurement as clear, watch, or warning."""
    if not value_data.get("valid", True):
        return None

    parameter = value_data.get("parameter") or value_data.get("measurementValueName")
    normalized = _normalized_parameter(parameter)
    value = _float_or_none(value_data.get("usedValue", value_data.get("value")))
    unit = value_data.get("measurementUnit")
    specific_index = value_data.get("hourlySpecificIndex") or {}
    code = _float_or_none(specific_index.get("code"))

    severity = None
    reason = None
    if code is not None:
        if code >= 4:
            severity = "warning"
            reason = "air_quality_index"
        elif code >= 3:
            severity = "watch"
            reason = "air_quality_index"

    threshold_key = _threshold_key(normalized)
    thresholds = WARNING_THRESHOLDS.get(threshold_key)
    if value is not None and thresholds:
        if value >= thresholds["warning"]:
            severity = "warning"
            reason = "threshold"
        elif value >= thresholds["watch"] and severity != "warning":
            severity = "watch"
            reason = "threshold"

    if not severity:
        return None

    return {
        "severity": severity,
        "reason": reason,
        "parameter": parameter,
        "value": _rounded(value, 3),
        "unit": _measurement_unit({"measurementUnit": unit}),
        "quality_index_code": int(code) if code is not None else None,
        "quality_index_name": specific_index.get("codeName"),
        "quality_index_valid": specific_index.get("valid"),
    }


def _find_station_wind(values):
    """Return wind speed and meteorological direction from the latest station group."""
    wind = {"speed_mps": None, "direction_degrees": None}
    for value_data in values:
        value = _float_or_none(value_data.get("usedValue", value_data.get("value")))
        if value is None:
            continue
        kind = _parameter_kind(value_data.get("parameter") or value_data.get("measurementValueName"))
        if kind == "wind_speed":
            wind["speed_mps"] = value
        elif kind == "wind_direction":
            wind["direction_degrees"] = value
    return wind


def _parameter_kind(parameter_name):
    """Map API parameter labels to stable weather/pollutant keys."""
    normalized = _normalized_parameter(parameter_name)
    if ("viteza" in normalized and "vant" in normalized) or "wind speed" in normalized:
        return "wind_speed"
    if (
        ("directia" in normalized and "vant" in normalized)
        or ("directie" in normalized and "vant" in normalized)
        or "wind direction" in normalized
    ):
        return "wind_direction"
    if "presiune" in normalized or "pressure" in normalized:
        return "air_pressure"
    return _threshold_key(normalized)


def _threshold_key(normalized_parameter):
    """Map API parameter names to warning threshold keys."""
    if "pm2" in normalized_parameter or "pm 2" in normalized_parameter:
        return "pm2.5"
    if "pm10" in normalized_parameter or "pm 10" in normalized_parameter:
        return "pm10"
    if normalized_parameter in WARNING_THRESHOLDS:
        return normalized_parameter
    if "viteza" in normalized_parameter and "vant" in normalized_parameter:
        return "wind_speed"
    if "wind speed" in normalized_parameter:
        return "wind_speed"
    if "radiatie" in normalized_parameter or "radiation" in normalized_parameter:
        return "solar_radiation"
    if "temperatura" in normalized_parameter or "temperature" in normalized_parameter:
        return "air_temperature"
    if "benzen" in normalized_parameter or "benzene" in normalized_parameter:
        return "benzene"
    for key in ("so2", "no2", "o3", "co", "h2s", "nh3"):
        if normalized_parameter == key or key in normalized_parameter:
            return key
    return normalized_parameter


def _parameter_key(parameter_name):
    """Return a stable key for grouping measurements across stations."""
    return _unique_location_id(_parameter_kind(parameter_name))


def _distance_weight(distance_km):
    """Return an inverse-distance weight that handles nearby stations safely."""
    if distance_km is None:
        return 1.0
    return 1.0 / max(distance_km, 1.0)


def _weighted_average(values):
    """Return a weighted average from value/weight dictionaries."""
    if not values:
        return None
    weight_sum = sum(item["weight"] for item in values)
    if weight_sum <= 0:
        return None
    return sum(item["value"] * item["weight"] for item in values) / weight_sum


def _latest_time(current, candidate):
    """Return the lexicographically latest ISO timestamp-like value."""
    if not candidate:
        return current
    if not current or candidate > current:
        return candidate
    return current


def _wind_speed_band(speed_mps):
    """Return a wind speed band matching the RNMCA website legend."""
    if speed_mps is None:
        return None
    if speed_mps < 0.5:
        return "< 0.50 m/s"
    if speed_mps < 2:
        return "0.50 - 2.00 m/s"
    if speed_mps < 6:
        return "2.00 - 6.00 m/s"
    if speed_mps < 8:
        return "6.00 - 8.00 m/s"
    if speed_mps < 10:
        return "8.00 - 10.00 m/s"
    if speed_mps < 12:
        return "10.00 - 12.00 m/s"
    return "> 12.00 m/s"


def _normalized_parameter(value):
    """Normalize API parameter names for matching."""
    value = str(value or "").lower()
    replacements = {
        "ă": "a",
        "â": "a",
        "î": "i",
        "ș": "s",
        "ş": "s",
        "ț": "t",
        "ţ": "t",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _poi_matches(station_poi, poi):
    """Return true when a station record belongs to the monitored point."""
    station_id = station_poi.get("id")
    poi_id = poi.get("id")
    if station_id is not None and poi_id is not None:
        return station_id == poi_id
    return station_poi.get("name") == poi.get("name")


def _eta_minutes(station_lat, station_lon, poi_lat, poi_lon, distance_km, wind_speed_mps, wind_direction_degrees):
    """Estimate arrival time if the station wind vector points toward the monitored point."""
    if None in (station_lat, station_lon, poi_lat, poi_lon, distance_km, wind_speed_mps, wind_direction_degrees):
        return None
    if wind_speed_mps <= 0:
        return None

    bearing_station_to_poi = _bearing(station_lat, station_lon, poi_lat, poi_lon)
    wind_travel_direction = (wind_direction_degrees + 180.0) % 360.0
    if _angular_difference(wind_travel_direction, bearing_station_to_poi) > 67.5:
        return None

    eta_hours = distance_km / (wind_speed_mps * 3.6)
    return int(round(eta_hours * 60))


def _bearing(lat1, lon1, lat2, lon2):
    """Return the initial bearing in degrees from point one to point two."""
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _cardinal(bearing, language):
    """Return a localized cardinal direction label."""
    keys = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    key = keys[int((bearing + 22.5) / 45.0) % 8]
    labels = CARDINAL_DIRECTIONS[key]
    return labels.get(language, labels[DEFAULT_LANGUAGE])


def _compass16(bearing):
    """Return a 16-point compass sector abbreviation."""
    keys = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return keys[int((bearing + 11.25) / 22.5) % 16]


def _angular_difference(first, second):
    """Return the smallest difference between two bearings."""
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _distance_km(lat1, lon1, lat2, lon2):
    """Calculate a haversine distance in kilometers."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _event_summary(event):
    """Return a short notification-friendly event summary."""
    if not event:
        return None
    value = event.get("value")
    unit = event.get("unit") or ""
    station = event.get("station")
    direction = event.get("direction_from_monitored_point")
    distance = event.get("distance_km")
    eta = event.get("eta_minutes")
    summary = f"{event.get('severity')} {event.get('parameter')} at {station}: {value} {unit}"
    if direction and distance is not None:
        summary = f"{summary}, {distance} km toward {direction}"
    if eta is not None:
        summary = f"{summary}, estimated arrival in {eta} minutes"
    return summary


def _float_or_none(value):
    """Convert a value to float, or return None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_value(value):
    """Return a numeric API value rounded for Home Assistant display."""
    numeric = _float_or_none(value)
    if numeric is None:
        return value
    return _rounded(numeric, MEASUREMENT_DISPLAY_PRECISION)


def _rounded(value, digits):
    """Round numeric values while preserving None."""
    if value is None:
        return None
    return round(value, digits)


def _specific_id(wrapper):
    """Extract the RNMCA measurement id from known wrapper shapes."""
    specific_id = wrapper.get("qualityIndexSpecificId")
    if specific_id is None:
        specific_id = wrapper.get("specificId")
    if specific_id is None:
        specific_id = wrapper.get("qualityIndexSpecific", {}).get("id")
    try:
        return int(specific_id)
    except (TypeError, ValueError):
        return specific_id


def _hourly_values(wrapper):
    """Return hourly values from known specific wrapper shapes."""
    return (
        wrapper.get("specificIndexHourlyValues")
        or wrapper.get("hourlyValues")
        or wrapper.get("values")
        or []
    )


def _measurement_value(hourly_value):
    """Extract the numeric measurement value from a wrapper."""
    if "usedValue" in hourly_value:
        return hourly_value.get("usedValue")
    if "value" in hourly_value:
        return hourly_value.get("value")
    nested = hourly_value.get("specificIndexHourlyValue", {})
    return nested.get("usedValue", nested.get("value"))


def _index_code(hourly_value):
    """Extract the air quality index code from a wrapper."""
    if "code" in hourly_value:
        return hourly_value.get("code")
    nested = hourly_value.get("specificIndexHourlyValue", {})
    return nested.get("code")


def _add_measurement_time(attributes, hourly_value):
    """Add a human-readable measurement time when the API provides one."""
    timestamp_ms = hourly_value.get("timestamp")
    if timestamp_ms is None:
        timestamp_ms = hourly_value.get("specificIndexHourlyValue", {}).get("timestamp")
    if timestamp_ms:
        dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0)
        attributes["measurement_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")


def _base_attributes(config_data, language):
    """Return common entity attributes."""
    info = config_data.get("info", {})
    poi = config_data.get("poi", {})
    return {
        "latitude": info.get("latitude"),
        "longitude": info.get("longitude"),
        "distance_km": config_data.get("distance"),
        "station_id": config_data.get("station_id"),
        "network_id": config_data.get("network_id"),
        "station_code": info.get("code"),
        "station_area_type": info.get("areaType"),
        "station_emission_source_type": info.get("emissionSourceType"),
        "general_quality_index_id": info.get("qualityIndexGeneralId"),
        "monitored_point": _poi_name(config_data, language),
        "monitored_point_latitude": poi.get(CONF_LATITUDE),
        "monitored_point_longitude": poi.get(CONF_LONGITUDE),
        "attribution": _label("attribution", language),
    }


def _poi_device_info(poi, index, language):
    """Return device info for a monitored point."""
    poi_name = poi.get("name") or _label("configured_location", language)
    unique_poi_id = _unique_location_id(poi.get("id") or poi_name or index)
    return {
        "identifiers": {(DOMAIN, f"poi_{unique_poi_id}")},
        "name": f"RNMCA {poi_name}",
        "manufacturer": "RNMCA",
        "model": "CalitateAer monitored area",
    }


def _station_device_info(config_data, location_id, language):
    """Return device info for one RNMCA station."""
    station_name = _station_name(config_data, location_id)
    poi = config_data.get("poi", {})
    poi_name = _poi_name(config_data, language)
    unique_station_id = _unique_location_id(location_id)
    unique_poi_id = _unique_location_id(poi.get("id") or poi_name)
    return {
        "identifiers": {(DOMAIN, f"station_{unique_station_id}")},
        "name": f"RNMCA {station_name}",
        "manufacturer": "RNMCA",
        "model": "RNMCA monitoring station",
        "via_device": (DOMAIN, f"poi_{unique_poi_id}"),
    }


def _station_name(config_data, location_id):
    """Return a friendly station name."""
    return (
        config_data.get("info", {}).get("name")
        or config_data.get("info", {}).get("label")
        or f"Station {location_id}"
    )


def _poi_name(config_data, language=DEFAULT_LANGUAGE):
    """Return a friendly monitored point name."""
    return config_data.get("poi", {}).get("name") or _label("configured_location", language)


def _unique_location_id(location_id):
    """Normalize location ids for entity unique IDs."""
    value = str(location_id).lower()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    return value.strip("_") or "station"


def _language(coordinator):
    """Return the configured UI/data language."""
    entry = getattr(coordinator, "entry", None)
    if entry is None:
        return DEFAULT_LANGUAGE
    language = entry.options.get(CONF_LANGUAGE, entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))
    return language if language in SENSOR_LABELS["general_index"] else DEFAULT_LANGUAGE


def _label(label_key, language):
    """Return a localized label."""
    labels = SENSOR_LABELS[label_key]
    return labels.get(language, labels[DEFAULT_LANGUAGE])


def _pollutant_name(specific_id, language, fallback):
    """Return a localized pollutant or meteorological sensor name."""
    labels = POLLUTANT_NAMES.get(specific_id)
    if not labels:
        return fallback
    return labels.get(language, labels[DEFAULT_LANGUAGE])
