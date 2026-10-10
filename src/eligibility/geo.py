"""
OpenArt — geography tables for the NATIONALITY / RESIDENCE value parser
(src/eligibility/values.py). Plain Python data, no external service, so every
mapping is visible and auditable.

  COUNTRIES      ISO 3166-1 alpha-2 code -> names and demonyms that refer to it
                 (every UN member state, plus a few territories)
  REGIONS        well-defined groupings -> their member countries
  SUBNATIONAL    regions / cities inside one country -> that country
  VAGUE_REGION_RE  regions with no agreed member list ("Europe", "Africa",
                 "the Caribbean"): a sentence naming one gets no value, so the
                 engine shows a CHECK instead of guessing a country list
"""

import re

# Names are matched case-insensitively as whole words, longest first, so
# "Papua New Guinea" wins over "Guinea". Demonyms are included where they're
# unambiguous ("Dutch", "Belgian"); ones that double as a language for
# several countries ("Spanish" is fine, "Arabic" is not) are left out.
COUNTRIES = {
    # Europe
    "AD": ["Andorra", "Andorran"],
    "AL": ["Albania", "Albanian"],
    "AM": ["Armenia", "Armenian"],
    "AT": ["Austria", "Austrian"],
    "AX": ["Åland", "Åland Islands", "Aland Islands"],
    "AZ": ["Azerbaijan", "Azerbaijani"],
    "BA": ["Bosnia and Herzegovina", "Bosnia", "Bosnian"],
    "BE": ["Belgium", "Belgian"],
    "BG": ["Bulgaria", "Bulgarian"],
    "BY": ["Belarus", "Republic of Belarus", "Belarusian"],
    "CH": ["Switzerland", "Swiss"],
    "CY": ["Cyprus", "Cypriot"],
    "CZ": ["Czech Republic", "Czechia", "Czech"],
    "DE": ["Germany", "German"],
    "DK": ["Denmark", "Danish"],
    "EE": ["Estonia", "Estonian"],
    "ES": ["Spain", "Spanish"],
    "FI": ["Finland", "Finnish"],
    "FO": ["Faroe Islands", "the Faroe Islands", "Faroese"],
    "FR": ["France", "French"],
    "GB": ["United Kingdom", "the UK", "UK", "Great Britain", "Britain", "British"],
    "GE": ["Georgia", "Georgian"],
    "GL": ["Greenland", "Greenlandic"],
    "GR": ["Greece", "Greek"],
    "HR": ["Croatia", "Croatian"],
    "HU": ["Hungary", "Hungarian"],
    "IE": ["Ireland", "Irish"],
    "IS": ["Iceland", "Icelandic"],
    "IT": ["Italy", "Italian"],
    "LI": ["Liechtenstein"],
    "LT": ["Lithuania", "Lithuanian"],
    "LU": ["Luxembourg", "Luxembourgish", "Luxembourger"],
    "LV": ["Latvia", "Latvian"],
    "MC": ["Monaco", "Monegasque"],
    "MD": ["Moldova", "Moldovan"],
    "ME": ["Montenegro", "Montenegrin"],
    "MK": ["North Macedonia", "Macedonia", "Macedonian"],
    "MT": ["Malta", "Maltese"],
    "NL": ["Netherlands", "the Netherlands", "Holland", "Dutch"],
    "NO": ["Norway", "Norwegian"],
    "PL": ["Poland", "Polish"],
    "PT": ["Portugal", "Portuguese"],
    "RO": ["Romania", "Romanian"],
    "RS": ["Serbia", "Serbian"],
    "RU": ["Russia", "Russian Federation", "Russian"],
    "SE": ["Sweden", "Swedish"],
    "SI": ["Slovenia", "Slovenian", "Slovene"],
    "SK": ["Slovakia", "Slovak Republic", "Slovak"],
    "SM": ["San Marino"],
    "TR": ["Turkey", "Türkiye", "Turkish"],
    "UA": ["Ukraine", "Ukrainian"],
    "XK": ["Kosovo", "Kosovar"],
    # Kingdom of the Netherlands, Caribbean part
    "AW": ["Aruba", "Aruban"],
    "BQ": ["Bonaire", "Sint Eustatius", "Saba"],
    "CW": ["Curaçao", "Curacao"],
    "SX": ["Sint Maarten"],
    # Americas
    "AR": ["Argentina", "Argentinian", "Argentine"],
    "BO": ["Bolivia", "Bolivian"],
    "BR": ["Brazil", "Brazilian"],
    "BZ": ["Belize", "Belizean"],
    "CA": ["Canada", "Canadian"],
    "CL": ["Chile", "Chilean"],
    "CO": ["Colombia", "Colombian"],
    "CR": ["Costa Rica", "Costa Rican"],
    "CU": ["Cuba", "Cuban"],
    "DO": ["Dominican Republic", "Dominican"],
    "EC": ["Ecuador", "Ecuadorian"],
    "GT": ["Guatemala", "Guatemalan"],
    "HN": ["Honduras", "Honduran"],
    "HT": ["Haiti", "Haitian"],
    "JM": ["Jamaica", "Jamaican"],
    "MX": ["Mexico", "Mexican"],
    "NI": ["Nicaragua", "Nicaraguan"],
    "PA": ["Panama", "Panamanian"],
    "PE": ["Peru", "Peruvian"],
    "PY": ["Paraguay", "Paraguayan"],
    "SR": ["Suriname", "Surinamese"],
    "SV": ["El Salvador", "Salvadoran"],
    "US": ["United States", "the USA", "USA", "the US", "American"],
    "UY": ["Uruguay", "Uruguayan"],
    "VE": ["Venezuela", "Venezuelan"],
    # Africa
    "DZ": ["Algeria", "Algerian"],
    "EG": ["Egypt", "Egyptian"],
    "ET": ["Ethiopia", "Ethiopian"],
    "GH": ["Ghana", "Ghanaian"],
    "KE": ["Kenya", "Kenyan"],
    "MA": ["Morocco", "Moroccan"],
    "NG": ["Nigeria", "Nigerian"],
    "SN": ["Senegal", "Senegalese"],
    "TN": ["Tunisia", "Tunisian"],
    "ZA": ["South Africa", "South African"],
    # Asia, Middle East, Oceania
    "AU": ["Australia", "Australian"],
    "CN": ["China", "Chinese"],
    "IL": ["Israel", "Israeli"],
    "IN": ["India", "Indian"],
    "IR": ["Iran", "Islamic Republic of Iran", "Iranian"],
    "JP": ["Japan", "Japanese"],
    "KR": ["South Korea", "Republic of Korea", "Korea", "Korean"],
    "LB": ["Lebanon", "Lebanese"],
    "NZ": ["New Zealand"],
    "PS": ["Palestine", "Palestinian"],
    "SY": ["Syria", "Syrian"],
    "TW": ["Taiwan", "Taiwanese"],
    # every other UN member state (plus Hong Kong), so a country named in a list
    # is never silently dropped: a missing "Yemen" in "Lebanon, Syria, Palestine,
    # Yemen and Sudan" would have rejected Yemeni artists (step 4, v3)
    "AE": ["United Arab Emirates", "UAE", "Emirati"], "AF": ["Afghanistan", "Afghan"],
    "AG": ["Antigua and Barbuda"], "AO": ["Angola", "Angolan"], "BB": ["Barbados", "Barbadian"],
    "BD": ["Bangladesh", "Bangladeshi"], "BF": ["Burkina Faso", "Burkinabe"], "BH": ["Bahrain", "Bahraini"],
    "BI": ["Burundi", "Burundian"], "BJ": ["Benin", "Beninese"], "BN": ["Brunei"], "BS": ["Bahamas"],
    "BT": ["Bhutan", "Bhutanese"], "BW": ["Botswana"], "CD": ["Democratic Republic of the Congo", "DR Congo", "DRC"],
    "CF": ["Central African Republic"], "CG": ["Republic of the Congo", "Congo"], "CI": ["Côte d'Ivoire", "Ivory Coast", "Ivorian"],
    "CM": ["Cameroon", "Cameroonian"], "CV": ["Cape Verde", "Cabo Verde"], "DJ": ["Djibouti"], "DM": ["Dominica"],
    "ER": ["Eritrea", "Eritrean"], "FJ": ["Fiji", "Fijian"], "FM": ["Micronesia"], "GA": ["Gabon", "Gabonese"],
    "GD": ["Grenada"], "GM": ["Gambia", "Gambian"], "GN": ["Guinea"], "GQ": ["Equatorial Guinea"],
    "GW": ["Guinea-Bissau"], "GY": ["Guyana", "Guyanese"], "HK": ["Hong Kong"], "ID": ["Indonesia", "Indonesian"],
    "IQ": ["Iraq", "Iraqi"], "JO": ["Jordan", "Jordanian"], "KG": ["Kyrgyzstan"], "KH": ["Cambodia", "Cambodian"],
    "KI": ["Kiribati"], "KM": ["Comoros"], "KN": ["Saint Kitts and Nevis"], "KP": ["North Korea"],
    "KW": ["Kuwait", "Kuwaiti"], "KZ": ["Kazakhstan", "Kazakh"], "LA": ["Laos", "Lao"], "LC": ["Saint Lucia"],
    "LK": ["Sri Lanka", "Sri Lankan"], "LR": ["Liberia", "Liberian"], "LS": ["Lesotho"], "LY": ["Libya", "Libyan"],
    "MG": ["Madagascar", "Malagasy"], "MH": ["Marshall Islands"], "ML": ["Mali", "Malian"], "MM": ["Myanmar", "Burma"],
    "MN": ["Mongolia", "Mongolian"], "MR": ["Mauritania", "Mauritanian"], "MU": ["Mauritius", "Mauritian"],
    "MV": ["Maldives"], "MW": ["Malawi", "Malawian"], "MY": ["Malaysia", "Malaysian"], "MZ": ["Mozambique"],
    "NA": ["Namibia", "Namibian"], "NE": ["Niger"], "NP": ["Nepal", "Nepali", "Nepalese"], "NR": ["Nauru"],
    "OM": ["Oman", "Omani"], "PG": ["Papua New Guinea"], "PH": ["Philippines", "Filipino"], "PK": ["Pakistan", "Pakistani"],
    "PW": ["Palau"], "QA": ["Qatar", "Qatari"], "RW": ["Rwanda", "Rwandan"], "SA": ["Saudi Arabia", "Saudi"],
    "SB": ["Solomon Islands"], "SC": ["Seychelles"], "SD": ["Sudan", "Sudanese"], "SG": ["Singapore", "Singaporean"],
    "SL": ["Sierra Leone"], "SO": ["Somalia", "Somali"], "SS": ["South Sudan"], "ST": ["São Tomé and Príncipe", "Sao Tome and Principe"],
    "SZ": ["Eswatini", "Swaziland"], "TD": ["Chad", "Chadian"], "TG": ["Togo", "Togolese"], "TH": ["Thailand", "Thai"],
    "TJ": ["Tajikistan"], "TL": ["Timor-Leste", "East Timor"], "TM": ["Turkmenistan"], "TO": ["Tonga"],
    "TT": ["Trinidad and Tobago"], "TV": ["Tuvalu"], "TZ": ["Tanzania", "Tanzanian"], "UG": ["Uganda", "Ugandan"],
    "UZ": ["Uzbekistan", "Uzbek"], "VA": ["Vatican", "Holy See"], "VC": ["Saint Vincent and the Grenadines"],
    "VN": ["Vietnam", "Viet Nam", "Vietnamese"], "VU": ["Vanuatu"], "WS": ["Samoa"], "YE": ["Yemen", "Yemeni"],
    "ZM": ["Zambia", "Zambian"], "ZW": ["Zimbabwe", "Zimbabwean"],
}

NORDIC = ["AX", "DK", "FI", "FO", "GL", "IS", "NO", "SE"]
BALTIC = ["EE", "LT", "LV"]
EU = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT",
      "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]

REGIONS = {
    "European Union": EU,
    "EU": EU,
    "European Economic Area": EU + ["IS", "LI", "NO"],
    "EEA": EU + ["IS", "LI", "NO"],
    "Nordic Region": NORDIC,
    "Nordic countries": NORDIC,
    "Nordic": NORDIC,
    "Baltic countries": BALTIC,
    "Baltic states": BALTIC,
    "Baltic": BALTIC,
    "Benelux": ["BE", "LU", "NL"],
    "Central America": ["BZ", "CR", "GT", "HN", "NI", "PA", "SV"],
    "Caribbean part of the Kingdom": ["AW", "BQ", "CW", "SX"],
    "Dutch Caribbean": ["AW", "BQ", "CW", "SX"],
}

# inside one country: the parser returns the country plus also_requires=<name>,
# so the engine can still reject an artist from another country, but only
# CHECKs one from the right country (their region isn't in the profile)
SUBNATIONAL = {
    "England": "GB", "Scotland": "GB", "Wales": "GB", "Northern Ireland": "GB", "London": "GB",
    "Flanders": "BE", "Wallonia": "BE", "Brussels": "BE",
    "North Rhine-Westphalia": "DE", "Bavaria": "DE", "Berlin": "DE",
    "Catalonia": "ES", "Basque Country": "ES", "Madrid": "ES",
    "Rotterdam": "NL", "Amsterdam": "NL",
    "Paris": "FR", "Vienna": "AT", "Oslo": "NO",
}

VAGUE_REGION_RE = re.compile(
    r"\b(Europe|European(?! (Union|Economic Area))|Africa|African|Asia|Asian|Caribbean(?! part of the Kingdom)"
    r"|Latin America|South America|North America|Middle East|Balkans?|Scandinavia|Sápmi"
    r"|Global South|abroad|international|worldwide|foreign)\b",
    re.IGNORECASE,
)


def _names_pattern(names: list[str]) -> re.Pattern:
    """One regex matching any of `names` as a whole word, longest first."""
    ordered = sorted(names, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in ordered) + r")\b", re.IGNORECASE)


# demonyms that are also language names: "write in French" or "German-language"
# is about a language, not a country (checked in values.parse_countries)
LANGUAGES = {
    "albanian", "bulgarian", "chinese", "croatian", "czech", "danish", "dutch", "estonian", "finnish",
    "french", "german", "greek", "hungarian", "icelandic", "italian", "japanese", "korean", "latvian",
    "lithuanian", "norwegian", "polish", "portuguese", "romanian", "russian", "serbian", "slovak",
    "slovene", "slovenian", "spanish", "swedish", "turkish", "ukrainian",
}

# lookup tables built once from the data above
NAME_TO_COUNTRY = {name.lower(): code for code, names in COUNTRIES.items() for name in names}
COUNTRY_RE = _names_pattern(list(NAME_TO_COUNTRY))
REGION_RE = _names_pattern(list(REGIONS))
REGION_LOOKUP = {name.lower(): members for name, members in REGIONS.items()}
SUBNATIONAL_RE = _names_pattern(list(SUBNATIONAL))
SUBNATIONAL_LOOKUP = {name.lower(): code for name, code in SUBNATIONAL.items()}


# -- broad regions ("Conclusive verdicts" step 5) --------------------------------------------------------
# Regions with no agreed member list ("Europe") can never reject an artist. They can only let one in,
# so each list holds just the countries clearly inside the region; borderline ones (TR, RU, GE, ...)
# are left out, which keeps them a check. "international" and "foreign" are not here: in a call they
# often mean "not from this country", the opposite of "everyone".
EUROPE = sorted(set(EU) | {"AD", "AL", "BA", "CH", "GB", "IS", "LI", "MC", "MD", "ME", "MK", "NO", "RS", "SM",
                           "UA", "VA", "XK", "AX", "FO"})
AFRICA = ["AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV", "DJ", "DZ", "EG", "ER", "ET", "GA",
          "GH", "GM", "GN", "GQ", "GW", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU", "MW", "MZ",
          "NA", "NE", "NG", "RW", "SC", "SD", "SL", "SN", "SO", "SS", "ST", "SZ", "TD", "TG", "TN", "TZ", "UG",
          "ZA", "ZM", "ZW"]
LATIN_AMERICA = ["AR", "BO", "BR", "BZ", "CL", "CO", "CR", "CU", "DO", "EC", "GT", "HN", "HT", "MX", "NI", "PA",
                 "PE", "PY", "SV", "UY", "VE"]
BROAD_REGIONS = {
    "Europe": EUROPE,
    "Africa": AFRICA,
    "Latin America": LATIN_AMERICA,
    "worldwide": sorted(COUNTRIES),
}
BROAD_REGION_RE = {
    "Europe": re.compile(r"\b(Europe|European)\b(?! (Union|Economic Area))", re.IGNORECASE),
    "Africa": re.compile(r"(?<!South )\b(Africa|African)\b", re.IGNORECASE),
    "Latin America": re.compile(r"\bLatin(o|x)? America\w*", re.IGNORECASE),
    "worldwide": re.compile(r"\b(worldwide|world-wide|from (all over|around|across) the world|from (all|any) "
                            r"countr(y|ies)|all nationalities|global(ly)?)\b", re.IGNORECASE),
}
# "non-European", "outside Europe": the region is excluded, not required
OUTSIDE_REGION_RE = re.compile(r"\b(non-|outside|excluding|except|other than|not (from|in|based))", re.IGNORECASE)


def broad_regions_named(text: str) -> list[str]:
    """The broad regions a sentence names as places applicants may come from; [] when it negates one."""
    if OUTSIDE_REGION_RE.search(text):
        return []
    return [name for name, pattern in BROAD_REGION_RE.items() if pattern.search(text)]


# -- countries in words, for the reasons shown to the artist ----------------------------------------------
# A region is named when all its members are in the list ("the EU" instead of 27 codes); largest first,
# so the EEA wins over the EU. The rest are country names.
NAMED_REGIONS = [("the EEA", REGIONS["EEA"]), ("the EU", EU), ("the Nordic countries", NORDIC),
                 ("the Baltic countries", BALTIC), ("the Benelux", REGIONS["Benelux"]),
                 ("the Dutch Caribbean", REGIONS["Dutch Caribbean"])]


def describe_countries(codes: list[str], limit: int = 8) -> str:
    """'the EU, Norway, Switzerland' for a list of ISO codes."""
    rest, parts = set(codes), []
    for name, members in NAMED_REGIONS:
        if set(members) <= rest:
            parts.append(name)
            rest -= set(members)
    names = sorted(COUNTRIES[code][0] if code in COUNTRIES else code for code in rest)
    if len(names) > limit:
        names = names[:limit] + [f"… ({len(rest)} countries)"]
    return ", ".join(parts + names)
