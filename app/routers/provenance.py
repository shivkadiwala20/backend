"""
Provenance endpoints — /api/data-sources, /api/indicators

These expose the lineage and license metadata stored alongside every import.
"""

import sqlite3
from typing import List

from fastapi import APIRouter, Depends

from ..database import get_db
from ..models.schemas import DataSourceResponse, IndicatorResponse

router = APIRouter()


@router.get(
    "/data-sources",
    response_model=List[DataSourceResponse],
    summary="List all data source imports with provenance and license info",
    tags=["Provenance"],
)
def list_data_sources(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM data_sources ORDER BY retrieved_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get(
    "/indicators",
    response_model=List[IndicatorResponse],
    summary="List all statistical indicators loaded into the database",
    tags=["Provenance"],
)
def list_indicators(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM statistical_indicators ORDER BY code"
    ).fetchall()
    return [dict(r) for r in rows]
