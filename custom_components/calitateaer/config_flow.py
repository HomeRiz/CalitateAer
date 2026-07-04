"""Config flow for RNMCA Air Quality."""
import asyncio
import logging
import urllib.parse
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv

try:
    from homeassistant.helpers.selector import LocationSelector
except ImportError:
    LocationSelector = None

from .const import (
    DOMAIN, API_BASE_URL, CONF_USERNAME, CONF_PASSWORD, CONF_RADIUS, DEFAULT_RADIUS,
    CONF_LANGUAGE, DEFAULT_LANGUAGE, LANGUAGES,
    CONF_LOCATION_METHOD, CONF_LATITUDE, CONF_LONGITUDE, CONF_ADDRESS,
    CONF_POIS, CONF_POI_NAME, CONF_POI_COUNTY, CONF_POI_LOCALITY, CONF_POI_LOCATION,
    CONF_ADD_MORE, CONF_NATIONAL_MAP, DEFAULT_NATIONAL_MAP,
    METHOD_HA, METHOD_ADDRESS, METHOD_MANUAL, MAX_RADIUS, POI_DONE, ROMANIA_COUNTIES
)

_LOGGER = logging.getLogger(__name__)

async def validate_auth(username, password):
    """Validate the user input allows us to connect."""
    url = f"{API_BASE_URL}/simplified/config/all?lastReceivedVersion=-1"
    auth = aiohttp.BasicAuth(username, password)

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, auth=auth) as response:
                if response.status in (401, 403):
                    raise InvalidAuth
                if response.status != 200:
                    _LOGGER.warning("RNMCA auth check failed with HTTP status %s", response.status)
                    raise CannotConnect
    except (InvalidAuth, CannotConnect):
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.warning("RNMCA auth check could not connect: %s", err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.warning("RNMCA auth check failed unexpectedly: %s", err)
        raise CannotConnect from err


async def geocode_romania_locality(county_code, locality):
    """Resolve a Romanian county/locality pair to coordinates."""
    county = ROMANIA_COUNTIES.get(county_code, county_code)
    query_parts = [locality]
    if county:
        query_parts.append(county)
    query_parts.append("Romania")
    query = ", ".join(query_parts)
    address = urllib.parse.quote(query)
    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1"
    headers = {"User-Agent": "HomeAssistant-RNMCA-Integration"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise CannotGeocode
            data = await resp.json()
            if not data:
                raise CannotGeocode
            return float(data[0]["lat"]), float(data[0]["lon"])

class CalitateAerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RNMCA Air Quality."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.user_data = {}
        self._poi_index = 0

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return CalitateAerOptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        """Step 1: Auth and Location Method Selection."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()

            try:
                await validate_auth(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                self.user_data = user_input
                method = user_input[CONF_LOCATION_METHOD]
                
                if method == METHOD_HA:
                    self.user_data[CONF_LATITUDE] = self.hass.config.latitude
                    self.user_data[CONF_LONGITUDE] = self.hass.config.longitude
                    self._add_primary_poi("Home Assistant location")
                    return await self.async_step_poi()
                
                elif method == METHOD_ADDRESS:
                    return await self.async_step_address()
                
                elif method == METHOD_MANUAL:
                    return await self.async_step_manual()

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS): vol.All(
                cv.positive_int, vol.Range(min=1, max=MAX_RADIUS)
            ),
            vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): vol.In(LANGUAGES),
            vol.Required(CONF_LOCATION_METHOD, default=METHOD_HA): vol.In({
                METHOD_HA: "Use Home Assistant Map",
                METHOD_ADDRESS: "Input Address",
                METHOD_MANUAL: "Input Coordinates Manually"
            })
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_address(self, user_input=None):
        """Step 2a: Geocoding via OpenStreetMap."""
        errors = {}
        
        if user_input is not None:
            address = urllib.parse.quote(user_input[CONF_ADDRESS])
            url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1"
            
            try:
                headers = {"User-Agent": "HomeAssistant-RNMCA-Integration"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                self.user_data[CONF_LATITUDE] = float(data[0]["lat"])
                                self.user_data[CONF_LONGITUDE] = float(data[0]["lon"])
                                self._add_primary_poi(user_input[CONF_ADDRESS])
                                return await self.async_step_poi()
                            errors["base"] = "geocode_failed"
                        else:
                            errors["base"] = "geocode_failed"
            except Exception:
                errors["base"] = "geocode_failed"

        return self.async_show_form(
            step_id="address", 
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}), 
            errors=errors
        )

    async def async_step_manual(self, user_input=None):
        """Step 2b: Manual coordinate entry."""
        if user_input is not None:
            self.user_data[CONF_LATITUDE] = user_input[CONF_LATITUDE]
            self.user_data[CONF_LONGITUDE] = user_input[CONF_LONGITUDE]
            self._add_primary_poi("Manual location")
            return await self.async_step_poi()

        schema = vol.Schema({
            vol.Required(CONF_LATITUDE): float,
            vol.Required(CONF_LONGITUDE): float
        })
        return self.async_show_form(step_id="manual", data_schema=schema)

    def _add_primary_poi(self, name):
        """Store the initially selected setup location as the first monitored point."""
        if CONF_POIS not in self.user_data:
            self.user_data[CONF_POIS] = []

        if self.user_data[CONF_POIS]:
            return

        self.user_data[CONF_POIS].append({
            "id": "primary",
            "name": name,
            CONF_LATITUDE: self.user_data.get(CONF_LATITUDE),
            CONF_LONGITUDE: self.user_data.get(CONF_LONGITUDE),
            "source": self.user_data.get(CONF_LOCATION_METHOD),
        })

    async def _geocode_poi(self, county_code, locality):
        """Resolve a Romanian county/locality pair to coordinates."""
        return await geocode_romania_locality(county_code, locality)

    async def async_step_poi(self, user_input=None):
        """Add optional monitored points of interest."""
        errors = {}

        if user_input is not None:
            county_code = user_input.get(CONF_POI_COUNTY)

            if county_code == POI_DONE or _empty_poi_input(user_input):
                return self.async_create_entry(title="RNMCA Dashboard", data=self.user_data)

            locality = user_input.get(CONF_POI_LOCALITY, "").strip()
            county_text = user_input.get(CONF_POI_COUNTY, "").strip()
            poi_name = user_input.get(CONF_POI_NAME, "").strip()
            map_location = user_input.get(CONF_POI_LOCATION)
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            try:
                if isinstance(map_location, dict):
                    latitude = map_location.get(CONF_LATITUDE)
                    longitude = map_location.get(CONF_LONGITUDE)
                elif latitude is None or longitude is None:
                    if not locality:
                        errors["base"] = "poi_required"
                    else:
                        latitude, longitude = await self._geocode_poi(county_text or county_code, locality)

                if not errors:
                    self._poi_index += 1
                    county = ROMANIA_COUNTIES.get(county_code, county_text or county_code)
                    display_name = poi_name or locality or "Map location"
                    self.user_data.setdefault(CONF_POIS, []).append({
                        "id": f"poi_{self._poi_index}",
                        "name": display_name,
                        "county": county,
                        "locality": locality,
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        "source": "poi",
                    })

                    if user_input.get(CONF_ADD_MORE, False):
                        return await self.async_step_poi()
                    return self.async_create_entry(title="RNMCA Dashboard", data=self.user_data)

            except CannotGeocode:
                errors["base"] = "geocode_failed"
            except Exception:
                _LOGGER.exception("Unexpected exception while adding point of interest")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="poi",
            data_schema=_poi_schema(),
            errors=errors,
        )

class CalitateAerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the integration."""

    def __init__(self):
        """Initialize options flow."""
        self._pending_options = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            self._pending_options = dict(self.config_entry.options)
            self._pending_options[CONF_RADIUS] = user_input[CONF_RADIUS]
            self._pending_options[CONF_LANGUAGE] = user_input[CONF_LANGUAGE]
            self._pending_options[CONF_NATIONAL_MAP] = user_input[CONF_NATIONAL_MAP]
            self._pending_options[CONF_POIS] = self._current_pois()

            if user_input.get(CONF_ADD_MORE):
                return await self.async_step_poi()

            return self.async_create_entry(title="", data=self._pending_options)

        current_radius = self.config_entry.options.get(
            CONF_RADIUS, 
            self.config_entry.data.get(CONF_RADIUS, DEFAULT_RADIUS)
        )
        current_language = self.config_entry.options.get(
            CONF_LANGUAGE,
            self.config_entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        )
        current_national = self.config_entry.options.get(
            CONF_NATIONAL_MAP,
            self.config_entry.data.get(CONF_NATIONAL_MAP, DEFAULT_NATIONAL_MAP)
        )

        options_schema = vol.Schema({
            vol.Optional(CONF_RADIUS, default=current_radius): vol.All(
                cv.positive_int, vol.Range(min=1, max=MAX_RADIUS)
            ),
            vol.Required(CONF_LANGUAGE, default=current_language): vol.In(LANGUAGES),
            vol.Required(CONF_NATIONAL_MAP, default=current_national): bool,
            vol.Optional(CONF_ADD_MORE, default=False): bool,
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)

    def _current_pois(self):
        """Return configured points from options or the original entry."""
        pois = self.config_entry.options.get(CONF_POIS, self.config_entry.data.get(CONF_POIS))
        if pois:
            return list(pois)

        return [{
            "id": "primary",
            "name": "Configured location",
            CONF_LATITUDE: self.config_entry.data.get(CONF_LATITUDE),
            CONF_LONGITUDE: self.config_entry.data.get(CONF_LONGITUDE),
            "source": "legacy",
        }]

    async def async_step_poi(self, user_input=None):
        """Add optional monitored points of interest from options."""
        errors = {}

        if user_input is not None:
            county_code = user_input.get(CONF_POI_COUNTY)

            if county_code == POI_DONE or _empty_poi_input(user_input):
                return self.async_create_entry(title="", data=self._pending_options)

            locality = user_input.get(CONF_POI_LOCALITY, "").strip()
            county_text = user_input.get(CONF_POI_COUNTY, "").strip()
            poi_name = user_input.get(CONF_POI_NAME, "").strip()
            map_location = user_input.get(CONF_POI_LOCATION)
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            try:
                if isinstance(map_location, dict):
                    latitude = map_location.get(CONF_LATITUDE)
                    longitude = map_location.get(CONF_LONGITUDE)
                elif latitude is None or longitude is None:
                    if not locality:
                        errors["base"] = "poi_required"
                    else:
                        latitude, longitude = await geocode_romania_locality(county_text or county_code, locality)

                if not errors:
                    pois = self._pending_options.setdefault(CONF_POIS, self._current_pois())
                    county = ROMANIA_COUNTIES.get(county_code, county_text or county_code)
                    display_name = poi_name or locality or "Map location"
                    pois.append({
                        "id": f"poi_{len(pois)}",
                        "name": display_name,
                        "county": county,
                        "locality": locality,
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        "source": "poi",
                    })

                    if user_input.get(CONF_ADD_MORE, False):
                        return await self.async_step_poi()
                    return self.async_create_entry(title="", data=self._pending_options)

            except CannotGeocode:
                errors["base"] = "geocode_failed"
            except Exception:
                _LOGGER.exception("Unexpected exception while adding point of interest")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="poi",
            data_schema=_poi_schema(),
            errors=errors,
        )

class CannotConnect(Exception): pass
class InvalidAuth(Exception): pass
class CannotGeocode(Exception): pass


def _empty_poi_input(user_input):
    """Return true when the optional POI form was submitted empty."""
    return not any(
        user_input.get(key)
        for key in (
            CONF_POI_LOCATION,
            CONF_POI_COUNTY,
            CONF_POI_LOCALITY,
            CONF_POI_NAME,
            CONF_LATITUDE,
            CONF_LONGITUDE,
        )
    )


def _poi_schema():
    """Build the optional POI schema with a safe map-selector fallback."""
    fields = {}
    location_selector = _location_selector()
    if location_selector is not None:
        fields[vol.Optional(CONF_POI_LOCATION)] = location_selector

    fields.update({
        vol.Optional(CONF_POI_COUNTY): str,
        vol.Optional(CONF_POI_LOCALITY): str,
        vol.Optional(CONF_POI_NAME): str,
        vol.Optional(CONF_LATITUDE): float,
        vol.Optional(CONF_LONGITUDE): float,
        vol.Optional(CONF_ADD_MORE, default=False): bool,
    })
    return vol.Schema(fields)


def _location_selector():
    """Return the HA location selector when available for this HA version."""
    if LocationSelector is None:
        _LOGGER.warning("Home Assistant LocationSelector is unavailable; POI map picker disabled")
        return None

    try:
        return LocationSelector()
    except Exception as err:
        _LOGGER.warning("Home Assistant LocationSelector failed to initialize: %s", err)
        return None
