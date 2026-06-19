"""
AGS (Amtlicher Gemeindeschlüssel) utilities.
The AGS is the official German region key: 2 digits = state, 5 = district, 8 = municipality.
"""

STATE_NAMES: dict[str, str] = {
    "01": "Schleswig-Holstein",
    "02": "Hamburg",
    "03": "Niedersachsen",
    "04": "Bremen",
    "05": "Nordrhein-Westfalen",
    "06": "Hessen",
    "07": "Rheinland-Pfalz",
    "08": "Baden-Württemberg",
    "09": "Bayern",
    "10": "Saarland",
    "11": "Berlin",
    "12": "Brandenburg",
    "13": "Mecklenburg-Vorpommern",
    "14": "Sachsen",
    "15": "Sachsen-Anhalt",
    "16": "Thüringen",
}

# Population estimates 2023 (Destatis / Regionalstatistik)
STATE_POPULATION_2023: dict[str, int] = {
    "01": 2_953_243,
    "02": 1_892_122,
    "03": 8_140_243,
    "04":   685_456,
    "05": 17_926_753,
    "06": 6_391_619,
    "07": 4_159_150,
    "08": 11_280_257,
    "09": 13_369_393,
    "10":   980_348,
    "11": 3_782_992,
    "12": 2_573_403,
    "13": 1_632_002,
    "14": 4_086_152,
    "15": 2_165_460,
    "16": 2_112_427,
}

# Reverse map — accepts German/English names and numeric codes
STATE_AGS_BY_NAME: dict[str, str] = {v.lower(): k for k, v in STATE_NAMES.items()}
STATE_AGS_BY_NAME.update(
    {
        "saxony": "14",
        "bavaria": "09",
        "berlin": "11",
        "hamburg": "02",
        "bremen": "04",
        "north rhine-westphalia": "05",
        "nrw": "05",
        "mecklenburg-western pomerania": "13",
        "mecklenburg-vorpommern": "13",
        "mecklenburg": "13",
        "thuringia": "16",
        "saxony-anhalt": "15",
        "lower saxony": "03",
        "hesse": "06",
        "saarland": "10",
        "rhineland-palatinate": "07",
        "rhineland palatinate": "07",
        "baden-württemberg": "08",
        "brandon": "12",
        "brandenburg": "12",
        "sh": "01",
        "schleswig holstein": "01",
        "nordrhein westfalen": "05",
        "sachsen": "14",
        "sachsen-anhalt": "15",
        "thüringen": "16",
        "niedersachsen": "03",
        "hessen": "06",
        "rheinland-pfalz": "07",
    }
)

# CSV column → participant_type mapping (Unfallatlas column names)
PARTICIPANT_COLUMNS: dict[str, str] = {
    "IstRad": "bicycle",
    "IstPKW": "car",
    "IstFuss": "pedestrian",
    "IstKrad": "motorcycle",
    "IstGkfz": "truck",
    "IstSonstige": "other",
}


def build_ags(uland, uregbez, ukreis, ugemeinde) -> str:
    """Build a full 8-digit AGS from Unfallatlas CSV columns."""
    try:
        land = str(int(float(uland))).zfill(2)    if uland    and str(uland).strip()    else "00"
        reg  = str(int(float(uregbez))).zfill(1)  if uregbez  and str(uregbez).strip()  else "0"
        krs  = str(int(float(ukreis))).zfill(2)   if ukreis   and str(ukreis).strip()   else "00"
        gem  = str(int(float(ugemeinde))).zfill(3) if ugemeinde and str(ugemeinde).strip() else "000"
        return land + reg + krs + gem
    except (ValueError, TypeError):
        return "00000000"


def build_district_ags(uland, uregbez, ukreis) -> str:
    """Build a 5-digit district AGS."""
    try:
        land = str(int(float(uland))).zfill(2)   if uland   and str(uland).strip()   else "00"
        reg  = str(int(float(uregbez))).zfill(1) if uregbez and str(uregbez).strip() else "0"
        krs  = str(int(float(ukreis))).zfill(2)  if ukreis  and str(ukreis).strip()  else "00"
        return land + reg + krs
    except (ValueError, TypeError):
        return "00000"


def resolve_state_ags(state_param: str) -> str:
    """
    Resolve a state parameter (name or code) to a 2-digit AGS string.
    Accepts: '14', 'Sachsen', 'Saxony', 'SN', etc.
    """
    if not state_param:
        raise ValueError("state parameter is required")
    s = state_param.strip().rstrip("%")
    # Numeric code (01-16)
    if s.isdigit() and len(s) <= 2:
        ags = s.zfill(2)
        if ags in STATE_NAMES:
            return ags
        raise ValueError(f"Unknown state code: '{state_param}'")
    found = STATE_AGS_BY_NAME.get(s.lower())
    if found:
        return found
    raise ValueError(
        f"Unknown state: '{state_param}'. "
        f"Try a 2-digit code ('14'), German name ('Sachsen') or English name ('Saxony')."
    )
