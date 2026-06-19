"""
FastAPI application entry point.

Run:   uvicorn app.main:app --reload --port 8000
Docs:  http://localhost:8000/api/docs
UI:    http://localhost:8000/
"""

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import accidents, aggregates, locations, provenance, questions

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="German Road Accident Data Platform",
    description="""
## Open Data Integration with Accidents in Germany

A data integration platform that harmonises official German open data from multiple sources
into a single queryable REST API.

### Data Sources
| Source | Format | License |
|--------|--------|---------|
| **Unfallatlas** (opengeodata.nrw.de) | CSV download | dl-de/by-2-0 |
| **Destatis** — Bevölkerungsstand 2023 | Hardcoded seed | dl-de/by-2-0 |
| **Unfallatlas Fallback** — rate per 10k | CSV | dl-de/by-2-0 |
| **Destatis** — Monthly statistics | CSV | dl-de/by-2-0 |

### Mandatory Questions
- **Q1** `GET /api/questions/earliest-year` — Earliest accident year
- **Q2** `GET /api/questions/accidents-by-state-year` — Saxony 2023 count
- **Q3** `GET /api/questions/earliest-year-by-state?state=Nordrhein-Westfalen`
- **Q4** `GET /api/questions/earliest-year-by-state?state=Mecklenburg-Vorpommern`
- **Q5** `GET /api/questions/participant-accidents?state=Berlin&year=2023&participant_type=pedestrian`
- **Q6** `GET /api/questions/rate-per-100k` — Cross-source rate per 100k (Unfallatlas + Destatis)
- **Q7** `GET /api/questions/trend-by-state` — Year-over-year trend

### License
All data published under **Datenlizenz Deutschland — Namensnennung — Version 2.0** (dl-de/by-2-0).
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ─────────────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_provenance_headers(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.time() - start) * 1000:.1f}"
    response.headers["X-Data-License"]    = "dl-de/by-2-0"
    response.headers["X-Data-Source"]     = "Unfallatlas, Destatis"
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(ValueError)
async def value_error_handler(req: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc), "status": 400})


@app.exception_handler(Exception)
async def generic_error_handler(req: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc), "status": 500},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(locations.router,  prefix="/api/locations",  tags=["Locations"])
app.include_router(accidents.router,  prefix="/api/accidents",  tags=["Accidents"])
app.include_router(aggregates.router, prefix="/api/aggregates", tags=["Aggregates"])
app.include_router(questions.router,  prefix="/api/questions",  tags=["Mandatory Questions"])
app.include_router(provenance.router, prefix="/api",            tags=["Provenance"])


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "api_docs": "/api/docs", "frontend": "/"}


# ─────────────────────────────────────────────────────────────────────────────
# Frontend — served at /
# ─────────────────────────────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    print("=" * 55)
    print("  German Road Accident Platform — API Ready")
    print("  API:          http://localhost:8000/api/docs")
    print("  Frontend:     http://localhost:8000/")
    print("  Health:       http://localhost:8000/health")
    print("=" * 55)
