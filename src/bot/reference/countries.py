"""ISO country code → Damodaran country name.

Two country vocabularies meet in the database:

- **ISO 3166 alpha-2** (``"US"``, ``"JP"``) — what ``companies.country`` holds,
  as emitted by the providers (EDGAR, FMP).
- **Damodaran names** (``"United States"``, ``"Japan"``) — what
  ``damodaran_country.country`` holds, copied from the ``ERPs by country`` sheet.

Joining one to the other with ``WHERE country = ?`` never matched, so every
non-default country lookup silently fell back to defaults. This module is the
single translation point: every reader of ``damodaran_country`` and the
dataset-region overrides runs the company country through
:func:`damodaran_country_name` first.
"""

from __future__ import annotations

from bot.utils.logging import get_logger

log = get_logger(__name__)

#: ISO 3166 alpha-2 code to the country name Damodaran's ``ERPs by country`` sheet uses.
ISO_TO_DAMODARAN_COUNTRY: dict[str, str] = {
    "AD": "Andorra (Principality of)",
    "AE": "United Arab Emirates",
    "AL": "Albania",
    "AM": "Armenia",
    "AO": "Angola",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "AW": "Aruba",
    "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BF": "Burkina Faso",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BN": "Brunei",
    "BO": "Bolivia",
    "BR": "Brazil",
    "BS": "Bahamas",
    "BW": "Botswana",
    "BY": "Belarus",
    "BZ": "Belize",
    "CA": "Canada",
    "CD": "Congo (Democratic Republic of)",
    "CG": "Congo (Republic of)",
    "CH": "Switzerland",
    "CI": "Côte d'Ivoire",
    "CK": "Cook Islands",
    "CL": "Chile",
    "CM": "Cameroon",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cape Verde",
    "CW": "Curacao",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EE": "Estonia",
    "EG": "Egypt",
    "ES": "Spain",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FR": "France",
    "GA": "Gabon",
    "GB": "United Kingdom",
    "GE": "Georgia",
    "GG": "Guernsey (States of)",
    "GH": "Ghana",
    "GM": "Gambia",
    "GN": "Guinea",
    "GR": "Greece",
    "GT": "Guatemala",
    "GW": "Guinea-Bissau",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IM": "Isle of Man",
    "IN": "India",
    "IQ": "Iraq",
    "IR": "Iran",
    "IS": "Iceland",
    "IT": "Italy",
    "JE": "Jersey (States of)",
    "JM": "Jamaica",
    "JO": "Jordan",
    "JP": "Japan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KP": "Korea, D.P.R.",
    "KR": "Korea",
    "KW": "Kuwait",
    "KY": "Cayman Islands",
    "KZ": "Kazakhstan",
    "LA": "Laos",
    "LB": "Lebanon",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LR": "Liberia",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "LY": "Libya",
    "MA": "Morocco",
    "MD": "Moldova",
    "ME": "Montenegro",
    "MG": "Madagascar",
    "MK": "Macedonia",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongolia",
    "MO": "Macao",
    "MS": "Montserrat",
    "MT": "Malta",
    "MU": "Mauritius",
    "MV": "Maldives",
    "MW": "Malawi",
    "MX": "Mexico",
    "MY": "Malaysia",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NE": "Niger",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PA": "Panama",
    "PE": "Peru",
    "PG": "Papua New Guinea",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PT": "Portugal",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SB": "Solomon Islands",
    "SD": "Sudan",
    "SE": "Sweden",
    "SG": "Singapore",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "SL": "Sierra Leone",
    "SN": "Senegal",
    "SO": "Somalia",
    "SR": "Suriname",
    "SV": "El Salvador",
    "SX": "St. Maarten",
    "SY": "Syria",
    "SZ": "Swaziland",
    "TC": "Turks and Caicos Islands",
    "TG": "Togo",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TT": "Trinidad and Tobago",
    "TW": "Taiwan",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "UG": "Uganda",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VC": "St. Vincent & the Grenadines",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "YE": "Yemen, Republic",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

#: Sheet rows with no ISO alpha-2 code (UAE emirates). They pass through unchanged.
SUBNATIONAL_SHEET_ROWS: frozenset[str] = frozenset(
    {"Abu Dhabi", "Ras Al Khaimah (Emirate of)", "Sharjah"}
)

#: Keys already warned about, so each unmapped value logs once per process.
_warned: set[str] = set()

_KNOWN_NAMES: frozenset[str] = frozenset(ISO_TO_DAMODARAN_COUNTRY.values()) | SUBNATIONAL_SHEET_ROWS


def damodaran_country_name(country: str | None) -> str | None:
    """Translate a company country to the name ``damodaran_country`` stores.

    Input is stripped. A two-letter input is upper-cased and looked up. A known
    Damodaran name passes through silently. Anything else is returned unchanged
    (so the SQL lookup misses as before) and logged once per distinct key.
    ``None`` and blank input give ``None``.
    """
    if country is None:
        return None
    stripped = country.strip()
    if not stripped:
        return None
    key = stripped.upper() if len(stripped) == 2 else stripped
    name = ISO_TO_DAMODARAN_COUNTRY.get(key)
    if name is not None:
        return name
    if stripped in _KNOWN_NAMES:
        return stripped
    if key not in _warned:
        _warned.add(key)
        log.warning("reference.country_unmapped", country=key)
    return stripped
