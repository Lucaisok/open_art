"""
OpenArt — where a call takes place: country_canonical corrected from the call's city.

The extraction prompt asked for "the country the opportunity is based in OR restricted
to" (src/collectors/extraction.py), so for some calls `country` holds who may apply,
not where the call happens: Gasworks' residency in London for artists based in Brazil
got "Brazil", a Paris residency for Moroccan artists got "Morocco". The product's
country filter and every result card mean the place, and who may apply is the
eligibility engine's job (it reads the call's own sentences), so country_canonical is
corrected here to mean the place. The raw `country` and its literal translation
`country_en` stay as extracted.

Two deterministic sources, both checked by hand:
1. The city. Where a call names one city (or region, or venue) listed in CITY_COUNTRY,
   that city's country is the place. Lists of several cities keep the extracted value.
2. PLACE_CORRECTIONS: the few calls with no city whose extracted country was read
   wrong, one reviewed line each with its reason.

Runs at the end of canonicalize_all() (it needs city_en and country_canonical), so a
pipeline re-run keeps it. Workflow.MD step 5c has the review.
"""

from src.models.processed_opportunity import ProcessedOpportunity

# city_en -> the country it is in (a CANONICAL_COUNTRIES name). Every single-place
# value in the corpus as of 2026-10-09; a new city falls back to the extracted country.
CITY_COUNTRY = {
    # Belgium
    "Antwerp": "Belgium", "Berchem": "Belgium", "Bruges": "Belgium", "Brugge": "Belgium",
    "Brussels": "Belgium", "Gent": "Belgium", "Ghent": "Belgium", "Kortrijk": "Belgium",
    "Leuven": "Belgium", "Liège": "Belgium", "Malines": "Belgium", "Mechelen": "Belgium",
    "Sint-Agatha-Berchem": "Belgium",
    # Netherlands
    "Amsterdam": "Netherlands", "Rotterdam": "Netherlands", "Tilburg": "Netherlands",
    "Utrecht": "Netherlands", "Vijfhuizen": "Netherlands", "Wijlre": "Netherlands",
    # Germany
    "BBA Gallery": "Germany", "Berlin": "Germany", "Cologne": "Germany", "Münster": "Germany",
    "North Rhine-Westphalia": "Germany", "Ringenberg Castle": "Germany", "Saarland": "Germany",
    "Straelen": "Germany", "Stuttgart": "Germany", "Weimar": "Germany",
    # France
    "Arles": "France", "Issy-les-Moulineaux": "France", "Liancourt": "France", "Marseille": "France",
    "Nice": "France", "Paris": "France", "Poitiers": "France", "Ramatuelle": "France",
    "Villa Arson": "France",
    # Spain
    "Almeria": "Spain", "Barcelona and Madrid": "Spain", "Corteconcepción (Huelva)": "Spain",
    "El Bruc": "Spain", "El Bruc - Barcelona": "Spain", "Galicia": "Spain", "Madrid": "Spain",
    # Italy
    "Florence": "Italy", "Milan": "Italy", "Naples": "Italy", "Terni": "Italy", "Venice": "Italy",
    "Zafferana Etnea, Sicily": "Italy",
    # elsewhere in Europe
    "Alentejo": "Portugal", "Lisbon": "Portugal",
    "Edinburgh": "United Kingdom", "London": "United Kingdom",
    "Vienna": "Austria", "Luxembourg": "Luxembourg",
    "Copenhagen": "Denmark", "Gothenburg": "Sweden", "Göteborg": "Sweden",
    "Oslo": "Norway", "Ålvik": "Norway", "Helsinki": "Finland", "Reykjavík": "Iceland",
    "Narva": "Estonia", "Riga": "Latvia", "Vilnius": "Lithuania",
    "Katowice": "Poland", "Warsaw": "Poland", "Warsaw or Orońsko": "Poland",
    "Pragovka complex": "Czech Republic", "Bratislava": "Slovakia", "Budapest": "Hungary",
    "Bucharest": "Romania", "Zagreb": "Croatia", "Novi Sad": "Serbia", "Tirana": "Albania",
    "Porta": "Greece",   # Porta, Corfu
    "Kyiv": "Ukraine", "Istanbul": "Turkey", "Yerevan": "Armenia",
    # outside Europe
    "Tel Aviv": "Israel", "Andore Village": "India", "Chengdu": "China",
    "Seoul or Gyeonggi": "South Korea", "Mexico City": "Mexico", "Monterrey": "Mexico",
    "São Paulo": "Brazil",
}  # fmt: skip

# opportunity id -> (place countries, why). Calls with no city whose extracted country is
# who may apply, or was lost; each read by hand (2026-10-09).
PLACE_CORRECTIONS = {
    "kunstlerhaus_bethanien_ad1d16a215d9": (
        ["Germany"], "IASPIS residency at Künstlerhaus Bethanien, Berlin; 'Sweden' is who may apply"),
    "kunsten_be_flanders_45954c0f1127": (
        ["Spain"], "SCAN Tarragona's Full Contact; 'any EU country or the UK' is who may apply"),
}


def place_countries(opp: ProcessedOpportunity) -> list[str]:
    """The countries the call takes place in: a reviewed correction, else its city's country,
    else the extracted country_canonical."""
    if opp.id in PLACE_CORRECTIONS:
        return PLACE_CORRECTIONS[opp.id][0]
    if opp.city_en in CITY_COUNTRY:
        return [CITY_COUNTRY[opp.city_en]]
    return opp.country_canonical


def correct_places(records: list[ProcessedOpportunity]) -> int:
    """Sets every record's country_canonical to where the call takes place. Returns how many changed."""
    changed = 0
    for record in records:
        place = place_countries(record)
        if place != record.country_canonical:
            record.country_canonical = place
            changed += 1
    return changed
