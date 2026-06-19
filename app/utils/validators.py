"""Plausibility check functions for accident data."""


# Germany bounding box (WGS84)
LON_MIN, LON_MAX = 5.8, 15.1
LAT_MIN, LAT_MAX = 47.2, 55.1

YEAR_MIN, YEAR_MAX = 2016, 2025


def is_valid_year(year) -> bool:
    try:
        return YEAR_MIN <= int(year) <= YEAR_MAX
    except (TypeError, ValueError):
        return False


def is_valid_coordinates(lon, lat) -> bool:
    try:
        return LON_MIN <= float(lon) <= LON_MAX and LAT_MIN <= float(lat) <= LAT_MAX
    except (TypeError, ValueError):
        return False


def is_valid_severity(severity) -> bool:
    try:
        return int(severity) in (1, 2, 3)
    except (TypeError, ValueError):
        return False


def is_valid_light_condition(light) -> bool:
    try:
        return int(light) in (0, 1, 2)
    except (TypeError, ValueError):
        return False


def is_valid_ags(ags: str) -> bool:
    return isinstance(ags, str) and ags.isdigit() and len(ags) in (2, 5, 8)


def plausibility_report(df) -> dict:
    """
    Run all plausibility checks on a DataFrame and return a summary.
    Used after CSV load to quantify data quality before filtering.
    """
    total = len(df)
    issues = {}

    if "UJAHR" in df.columns:
        bad_year = (~df["UJAHR"].between(YEAR_MIN, YEAR_MAX)).sum()
        issues["invalid_year"] = int(bad_year)

    if "XGCSWGS84" in df.columns and "YGCSWGS84" in df.columns:
        bad_coord = (
            ~(df["XGCSWGS84"].between(LON_MIN, LON_MAX) & df["YGCSWGS84"].between(LAT_MIN, LAT_MAX))
        ).sum()
        issues["invalid_coordinates"] = int(bad_coord)

    if "UKATEGORIE" in df.columns:
        bad_sev = (~df["UKATEGORIE"].isin([1, 2, 3])).sum()
        issues["invalid_severity"] = int(bad_sev)

    return {"total_rows": total, "issues": issues}
