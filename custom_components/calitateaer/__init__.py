"""The RNMCA Air Quality integration."""
import logging
import math
import re
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import Platform

from .const import (
    API_BASE_URL,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NATIONAL_MAP,
    CONF_PASSWORD,
    CONF_POIS,
    CONF_RADIUS,
    CONF_USERNAME,
    DEFAULT_NATIONAL_MAP,
    DEFAULT_RECENT_INTERVAL_CODE,
    DEFAULT_RECENT_POLL_HOURS,
    DOMAIN,
    ROOT_NETWORK_ID,
)
from .national import build_national_payload

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in kilometers."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except (TypeError, ValueError):
        return float('inf')
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RNMCA Air Quality from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = CalitateAerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up listener for option updates (Radius changes)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class CalitateAerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.username = entry.data[CONF_USERNAME]
        self.password = entry.data[CONF_PASSWORD]

        # Pull radius from options (Configure button) or initial data
        self.radius = entry.options.get(CONF_RADIUS, entry.data.get(CONF_RADIUS, 100))
        # National map mode: when on, one root-network call per poll exposes
        # every RNMCA station nationwide (see _update_national).
        self.national_map = entry.options.get(
            CONF_NATIONAL_MAP, entry.data.get(CONF_NATIONAL_MAP, DEFAULT_NATIONAL_MAP)
        )
        self.home_lat = entry.data.get(CONF_LATITUDE)
        self.home_lon = entry.data.get(CONF_LONGITUDE)
        self.pois = self._get_configured_pois()

        self.nearby_stations = {}
        self.all_locations = {}
        self.national_payload = {}
        self._config_loaded = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=DEFAULT_RECENT_POLL_HOURS),
        )

    def _get_configured_pois(self):
        """Return monitored points from the entry, with legacy fallback."""
        pois = self.entry.options.get(CONF_POIS, self.entry.data.get(CONF_POIS))
        if pois:
            return pois

        return [{
            "id": "primary",
            "name": "Configured location",
            CONF_LATITUDE: self.home_lat,
            CONF_LONGITUDE: self.home_lon,
            "source": "legacy",
        }]

    async def _fetch_and_parse_config(self, session, auth):
        """Fetch the full API config to find stations."""
        self.nearby_stations = {}
        self.all_locations = {}
        config_url = f"{API_BASE_URL}/simplified/config/all?lastReceivedVersion=-1"
        async with session.get(config_url, auth=auth) as response:
            response.raise_for_status()
            data = await response.json()
            networks = self._network_roots(data)
            if networks:
                self._extract_locations_recursive(networks)
            self._config_loaded = bool(self.all_locations)
            _LOGGER.info(
                "Found %s stations within %skm (%s locations nationwide)",
                len(self.nearby_stations),
                self.radius,
                len(self.all_locations),
            )

    @staticmethod
    def _network_roots(data):
        """Return network roots from known API configuration shapes."""
        if not isinstance(data, dict):
            return []

        configuration = data.get("configuration") or {}
        user_configuration = data.get("userConfiguration") or {}
        if not user_configuration:
            user_configuration = data.get("data", {}).get("userConfiguration", {})
        networks = user_configuration.get("networks")
        if networks:
            return networks

        configuration_network = configuration.get("configurationNetwork") or {}
        networks = configuration_network.get("networks") or data.get("networks")
        if networks:
            return networks

        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                candidate = item.get("networks")
                if isinstance(candidate, list):
                    return candidate
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        return []

    def _extract_locations_recursive(self, networks, parent_network_id=None):
        """Recursively search for locations."""
        for network in networks:
            network_id = network.get("id", parent_network_id)
            for loc in network.get("locations") or network.get("currentLocations") or []:
                loc_id = loc.get("id")
                if loc_id is None:
                    continue

                # Keep every location nationwide for the national map sensor.
                # The card needs coordinates for stations outside the POI radius,
                # so we retain the full catalogue here (cheap: already downloaded).
                if loc.get("networkId") is None:
                    loc["networkId"] = network_id
                self.all_locations[loc_id] = loc

                for poi in self.pois:
                    distance = haversine_distance(
                        poi.get(CONF_LATITUDE),
                        poi.get(CONF_LONGITUDE),
                        loc.get("latitude"),
                        loc.get("longitude"),
                    )
                    if distance <= self.radius:
                        poi_id = _slugify(str(poi.get("id") or poi.get("name") or "poi"))
                        key = f"{poi_id}_{loc_id}"
                        self.nearby_stations[key] = {
                            "station_id": loc_id,
                            "network_id": loc.get("networkId", network_id),
                            "info": loc,
                            "distance": round(distance, 2),
                            "poi": poi,
                        }
            subs = [sn for sn in network.get("subNetworks", []) if sn]
            if subs:
                self._extract_locations_recursive(subs, network_id)

    def _build_empty_station_data(self):
        """Create station records even before live values are available."""
        return {
            key: {
                "station_id": station["station_id"],
                "network_id": station.get("network_id"),
                "live_data": {},
                "config": station,
            }
            for key, station in self.nearby_stations.items()
        }

    async def _fetch_live_data_for_network(self, session, auth, network_id):
        """Fetch recent live data for one RNMCA network."""
        data_url = (
            f"{API_BASE_URL}/simplified/data/recent/network"
            f"?networkId={network_id}&intervalCode={DEFAULT_RECENT_INTERVAL_CODE}"
        )
        async with session.get(data_url, auth=auth) as response:
            response.raise_for_status()
            return await response.json()

    @staticmethod
    def _locations_data(raw_data):
        """Return location data wrappers from known API response shapes."""
        if not raw_data:
            return []
        if "locationsData" in raw_data:
            return raw_data["locationsData"]
        if "data" in raw_data and isinstance(raw_data["data"], dict):
            return raw_data["data"].get("locationsData", [])
        return []

    async def _async_update_data(self):
        """Fetch live air quality data."""
        auth = aiohttp.BasicAuth(self.username, self.password)
        try:
            async with async_timeout.timeout(30):
                async with aiohttp.ClientSession() as session:
                    if not self._config_loaded:
                        await self._fetch_and_parse_config(session, auth)

                    # National mode: ONE root-network request (networkId=1)
                    # returns the entire national dataset, which feeds both the
                    # nearby POI entities and the national map payload.
                    if self.national_map:
                        return await self._update_national(session, auth)

                    if not self.nearby_stations:
                        return {}

                    filtered_data = self._build_empty_station_data()
                    network_ids = {
                        station.get("network_id") or 1
                        for station in self.nearby_stations.values()
                    }

                    for network_id in network_ids:
                        try:
                            raw_data = await self._fetch_live_data_for_network(session, auth, network_id)
                        except aiohttp.ClientResponseError as err:
                            _LOGGER.warning(
                                "Failed to fetch RNMCA live data for network %s: %s",
                                network_id,
                                err,
                            )
                            continue
                        self._apply_live_data(filtered_data, raw_data)

                    self.national_payload = {}
                    return filtered_data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _update_national(self, session, auth):
        """Fetch the whole national dataset in one root-network call.

        The RNMCA Simplified API returns every location for networkId=1, so a
        single request per poll covers all ~186 stations while staying within
        rate limits. The same response also feeds the nearby POI entities, so
        national mode makes fewer calls than per-network mode.
        """
        filtered_data = self._build_empty_station_data()
        try:
            raw_data = await self._fetch_live_data_for_network(
                session, auth, ROOT_NETWORK_ID
            )
        except aiohttp.ClientResponseError as err:
            _LOGGER.warning("Failed to fetch RNMCA national data: %s", err)
            self.national_payload = build_national_payload(self.all_locations, [])
            return filtered_data

        locations_data = self._locations_data(raw_data)
        self._apply_live_data(filtered_data, raw_data)
        self.national_payload = build_national_payload(self.all_locations, locations_data)
        _LOGGER.debug(
            "National map payload: %s/%s stations have data",
            self.national_payload.get("with_data_count"),
            self.national_payload.get("station_count"),
        )
        return filtered_data

    def _apply_live_data(self, filtered_data, raw_data):
        """Match a recent-data response onto the nearby station records."""
        for loc_data in self._locations_data(raw_data):
            loc_id = loc_data.get("locationId", loc_data.get("id"))
            for key, station in self.nearby_stations.items():
                if station["station_id"] == loc_id:
                    filtered_data[key]["live_data"] = loc_data


def _slugify(value):
    """Convert values to stable entity key fragments."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    return value.strip("_") or "poi"
