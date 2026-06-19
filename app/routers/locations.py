import sqlite3
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..models.schemas import LocationResponse

router = APIRouter()


@router.get(
    "",
    response_model=List[LocationResponse],
    summary="List locations (states, districts, municipalities)",
    description="Filter by location_type and/or name (partial match).",
)
def list_locations(
    location_type: Optional[str] = Query(
        None, enum=["state", "district", "municipality"],
        description="Filter by type"
    ),
    name: Optional[str] = Query(None, description="Partial name match (case-insensitive)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    sql    = "SELECT * FROM locations WHERE 1=1"
    params = []

    if location_type:
        sql += " AND location_type = ?"
        params.append(location_type)

    if name:
        sql += " AND LOWER(name) LIKE ?"
        params.append(f"%{name.lower()}%")

    sql += " ORDER BY ags LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@router.get(
    "/{ags}",
    response_model=LocationResponse,
    summary="Get a single location by AGS code",
)
def get_location(
    ags: str,
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute("SELECT * FROM locations WHERE ags = ?", [ags]).fetchone()
    if not row:
        raise HTTPException(404, detail=f"Location with AGS '{ags}' not found.")
    return dict(row)
