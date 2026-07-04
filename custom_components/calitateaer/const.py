"""Constants for the RNMCA Air Quality integration."""
DOMAIN = "calitateaer"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_RADIUS = "radius"
CONF_LANGUAGE = "language"

# Location Constants
CONF_LOCATION_METHOD = "location_method"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_ADDRESS = "address"
CONF_POIS = "points_of_interest"
CONF_POI_NAME = "poi_name"
CONF_POI_COUNTY = "poi_county"
CONF_POI_LOCALITY = "poi_locality"
CONF_POI_LOCATION = "poi_location"
CONF_ADD_MORE = "add_more"

METHOD_HA = "home_assistant"
METHOD_ADDRESS = "address"
METHOD_MANUAL = "manual"

DEFAULT_RADIUS = 100  # Default to 100km for better coverage
MAX_RADIUS = 250      # Allow the user to go up to 250km
API_BASE_URL = "https://calitateaer.ro:8443/airquality"
DEFAULT_RECENT_INTERVAL_CODE = "3h"
DEFAULT_RECENT_POLL_HOURS = 3

# National map data (for the CalitateAer Map Card).
# When enabled, the coordinator makes ONE root-network request
# (networkId=ROOT_NETWORK_ID) per update so it can expose every RNMCA station
# nationwide via the always-on sensor.rnmca_national_stations entity. The root
# call returns the entire national dataset in a single response, so it is the
# rate-limit-friendly way to cover all stations (one call per poll interval).
CONF_NATIONAL_MAP = "national_map"
DEFAULT_NATIONAL_MAP = True
ROOT_NETWORK_ID = 1

DEFAULT_LANGUAGE = "en"
LANGUAGES = {
    "ro": "Romanian",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "de": "German",
}

POI_DONE = "__done__"

ROMANIA_COUNTIES = {
    POI_DONE: "Done adding monitored points",
    "AB": "Alba",
    "AR": "Arad",
    "AG": "Arges",
    "BC": "Bacau",
    "BH": "Bihor",
    "BN": "Bistrita-Nasaud",
    "BT": "Botosani",
    "BR": "Braila",
    "BV": "Brasov",
    "B": "Bucuresti",
    "BZ": "Buzau",
    "CL": "Calarasi",
    "CS": "Caras-Severin",
    "CJ": "Cluj",
    "CT": "Constanta",
    "CV": "Covasna",
    "DB": "Dambovita",
    "DJ": "Dolj",
    "GL": "Galati",
    "GR": "Giurgiu",
    "GJ": "Gorj",
    "HR": "Harghita",
    "HD": "Hunedoara",
    "IL": "Ialomita",
    "IS": "Iasi",
    "IF": "Ilfov",
    "MM": "Maramures",
    "MH": "Mehedinti",
    "MS": "Mures",
    "NT": "Neamt",
    "OT": "Olt",
    "PH": "Prahova",
    "SJ": "Salaj",
    "SM": "Satu Mare",
    "SB": "Sibiu",
    "SV": "Suceava",
    "TR": "Teleorman",
    "TM": "Timis",
    "TL": "Tulcea",
    "VL": "Valcea",
    "VS": "Vaslui",
    "VN": "Vrancea",
}
