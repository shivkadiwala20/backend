"""
Mandatory exam questions — /api/questions/*

Q1  GET /earliest-year               — earliest accident year in dataset
Q2  GET /accidents-by-state-year     — accident count for a state + year
Q3  GET /earliest-year-by-state      — earliest data year for NRW
Q4  GET /earliest-year-by-state      — earliest data year for Mecklenburg-WP
Q5  GET /participant-accidents        — pedestrian accidents Berlin 2023
Q6  GET /rate-per-100k               — cross-source: accidents / population (Unfallatlas + Destatis)
Q7  GET /trend-by-state              — year-over-year trend for a state
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import DBConnection, get_db
from ..models.schemas import (
    AccidentsByStateYearResponse,
    EarliestYearByStateResponse,
    EarliestYearResponse,
    ParticipantAccidentsResponse,
    RatePer100kResponse,
    RankingRow,
)
from ..utils.ags import STATE_NAMES, resolve_state_ags

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Q1  Earliest accident year in the entire dataset
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/earliest-year",
    response_model=EarliestYearResponse,
    summary="Q1: Earliest accident year in the complete dataset",
)
def earliest_year(db: DBConnection = Depends(get_db)):
    row = db.execute("SELECT MIN(year) AS y FROM accident_events").fetchone()
    if not row or row["y"] is None:
        raise HTTPException(404, detail="No accident data found. Run ETL first.")
    return {"earliest_year": row["y"], "source": "Unfallatlas (imported)", "license": "dl-de/by-2-0"}


# ─────────────────────────────────────────────────────────────────────────────
# Q2  Accident count in a state for a given year
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/accidents-by-state-year",
    response_model=AccidentsByStateYearResponse,
    summary="Q2: Total accidents with personal injury in a state for a given year",
)
def accidents_by_state_year(
    state: str = Query(..., description="State name (e.g. Sachsen) or 2-digit AGS code"),
    year:  int = Query(..., ge=2016, le=2025),
    db: DBConnection = Depends(get_db),
):
    ags = resolve_state_ags(state)
    row = db.execute(
        "SELECT COUNT(*) AS c FROM accident_events WHERE ags LIKE %s AND year=%s",
        [f"{ags}%", year],
    ).fetchone()
    return {
        "state": STATE_NAMES.get(ags, state),
        "ags": ags,
        "year": year,
        "accident_count": row["c"],
        "source_license": "dl-de/by-2-0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Q3 + Q4  Earliest year available for a given state
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/earliest-year-by-state",
    response_model=EarliestYearByStateResponse,
    summary="Q3/Q4: Earliest accident year available for a given state",
    description="Q3: state=Nordrhein-Westfalen  |  Q4: state=Mecklenburg-Vorpommern",
)
def earliest_year_by_state(
    state: str = Query(..., description="State name or 2-digit AGS code"),
    db: DBConnection = Depends(get_db),
):
    ags = resolve_state_ags(state)
    row = db.execute(
        "SELECT MIN(year) AS y FROM accident_events WHERE ags LIKE %s",
        [f"{ags}%"],
    ).fetchone()
    if not row or row["y"] is None:
        raise HTTPException(404, detail=f"No data found for state '{state}'. Check ETL imports.")
    return {
        "state": STATE_NAMES.get(ags, state),
        "ags": ags,
        "earliest_year": row["y"],
        "license": "dl-de/by-2-0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Q5  Accidents by participant type in a state + year
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/participant-accidents",
    response_model=ParticipantAccidentsResponse,
    summary="Q5: Accidents by participant type in a state and year",
    description="Uses the normalised accident_participants table. Example: state=Berlin&year=2023&participant_type=pedestrian",
)
def participant_accidents(
    state: str = Query(...),
    year:  int = Query(..., ge=2016, le=2025),
    participant_type: str = Query(
        "pedestrian",
        enum=["bicycle", "car", "pedestrian", "motorcycle", "truck", "other"],
    ),
    db: DBConnection = Depends(get_db),
):
    ags = resolve_state_ags(state)
    row = db.execute(
        """
        SELECT COUNT(DISTINCT ae.event_id) AS c
        FROM accident_events ae
        JOIN accident_participants ap ON ap.event_id = ae.event_id
        WHERE ae.ags LIKE %s AND ae.year = %s AND ap.participant_type = %s
        """,
        [f"{ags}%", year, participant_type],
    ).fetchone()
    return {
        "state": STATE_NAMES.get(ags, state),
        "ags": ags,
        "year": year,
        "participant_type": participant_type,
        "accident_count": row["c"],
        "license": "dl-de/by-2-0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Q6  Accident rate per 100,000 inhabitants (mandatory cross-source join)
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/rate-per-100k",
    response_model=RatePer100kResponse,
    summary="Q6: Accident rate per 100,000 inhabitants (cross-source: Unfallatlas + Destatis)",
    description=(
        "Joins accident_events (Unfallatlas) with statistical_values (Destatis population). "
        "This is the mandatory cross-source question."
    ),
)
def rate_per_100k(
    year:  int = Query(2023, ge=2016, le=2025),
    level: str = Query("state", enum=["state", "district"]),
    limit: int = Query(16, ge=1, le=50),
    order: str = Query("desc", enum=["asc", "desc"]),
    db: DBConnection = Depends(get_db),
):
    direction = "DESC" if order == "desc" else "ASC"
    rows = db.execute(
        f"""
        SELECT
            l.ags,
            l.name,
            COUNT(ae.event_id)                                          AS accident_count,
            sv.value                                                     AS population,
            CASE WHEN sv.value > 0
                 THEN ROUND(CAST(COUNT(ae.event_id) AS NUMERIC) / sv.value * 100000, 2)
                 ELSE NULL END                                           AS rate_per_100k
        FROM accident_events ae
        JOIN locations l ON ae.location_id = l.location_id
        LEFT JOIN statistical_values sv
               ON sv.location_id = l.location_id
              AND sv.year = ae.year
              AND sv.indicator_id = (
                  SELECT indicator_id FROM statistical_indicators WHERE code = 'population' LIMIT 1
              )
        WHERE l.location_type = %s AND ae.year = %s
        GROUP BY l.ags, l.name, sv.value
        ORDER BY rate_per_100k {direction} NULLS LAST
        LIMIT %s
        """,
        [level, year, limit],
    ).fetchall()

    return {
        "year": year,
        "level": level,
        "license": "dl-de/by-2-0",
        "ranking": [
            RankingRow(
                rank=i + 1,
                ags=r["ags"],
                name=r["name"],
                accident_count=r["accident_count"],
                population=r["population"],
                rate_per_100k=r["rate_per_100k"],
            )
            for i, r in enumerate(rows)
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Q7  Year-over-year accident trend for a state
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/trend-by-state",
    summary="Q7: Year-over-year accident trend for a state",
)
def trend_by_state(
    state:      str = Query(...),
    start_year: int = Query(2016, ge=2016, le=2025),
    end_year:   int = Query(2025, ge=2016, le=2025),
    db: DBConnection = Depends(get_db),
):
    ags = resolve_state_ags(state)
    rows = db.execute(
        """
        SELECT year, COUNT(*) AS accident_count
        FROM accident_events
        WHERE ags LIKE %s AND year BETWEEN %s AND %s
        GROUP BY year
        ORDER BY year
        """,
        [f"{ags}%", start_year, end_year],
    ).fetchall()
    return {
        "state": STATE_NAMES.get(ags, state),
        "ags": ags,
        "license": "dl-de/by-2-0",
        "trend": [{"year": r["year"], "accident_count": r["accident_count"]} for r in rows],
    }
