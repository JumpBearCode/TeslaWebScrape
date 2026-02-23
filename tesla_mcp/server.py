"""Tesla Inventory MCP Server — tools for scraping Tesla inventory.

Tools:
    acquire_cookies  — nodriver bypasses Akamai, returns cookie status
    search_inventory — curl_cffi calls Tesla API, returns vehicles (slim fields)
    search_top_n     — auto-pagination + VIN dedup, saves raw + slim JSON
    merge_results    — merge raw files into one CSV
    save_results     — save content to results/ directory
"""

from __future__ import annotations

import builtins
import csv
import io
import json
import time
from pathlib import Path

from fastmcp import FastMCP

from tesla_mcp.scraper import CookieManager, InventoryClient

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

mcp = FastMCP("tesla-inventory")

# Only return these fields per vehicle (instead of all 123)
_SLIM_FIELDS = [
    "VIN", "Year", "Model", "TrimName", "TotalPrice", "Odometer",
    "ActualRange", "PAINT", "INTERIOR", "WHEELS",
    "City", "StateProvince",
    "FactoryGatedDate", "FirstRegistrationDate",
    "VehicleHistory", "PriceAdjustmentUsed",
    "DamageDisclosure", "DamageDisclosureStatus", "CPORefurbishmentStatus",
    "AcquisitionSubType", "FleetVehicle", "IsDemo",
    "VehicleSubType", "TitleSubtype",
    "AUTOPILOT", "TransportationFee",
    "HasVehiclePhotos",
]


def _slim_vehicle(v: dict) -> dict:
    """Extract only essential fields from a vehicle record."""
    return {k: v.get(k) for k in _SLIM_FIELDS}


def _flatten_vehicle(v: dict) -> dict:
    """Flatten a slim vehicle record for CSV output (lists → comma-joined strings)."""
    out = {}
    for k, val in v.items():
        if isinstance(val, list):
            out[k] = ", ".join(str(x) for x in val)
        elif isinstance(val, bool):
            out[k] = str(val)
        elif val is None:
            out[k] = ""
        else:
            out[k] = val
    return out

# Shared cookie manager — caches cookies for 10 minutes
_cookies = CookieManager(ttl=600)


@mcp.tool()
async def acquire_cookies(
    model: str = "my",
    condition: str = "used",
) -> str:
    """Launch undetected Chrome to bypass Akamai and acquire cookies for Tesla API.

    Only opens a browser if cached cookies have expired (10-min TTL).

    Args:
        model: Model code for the inventory page visit (my/m3/ms/mx).
        condition: 'used' or 'new'.

    Returns:
        Status message with cookie count and cache info.
    """
    was_cached = _cookies.valid
    cookies = await _cookies.acquire(model=model, condition=condition)
    has_abck = "_abck" in cookies

    if was_cached:
        remaining = int(_cookies._ttl - (time.time() - _cookies._acquired_at))
        return (
            f"Using cached cookies ({len(cookies)} cookies, "
            f"_abck={has_abck}, {remaining}s remaining)"
        )
    return f"Acquired {len(cookies)} fresh cookies (_abck={has_abck})"


@mcp.tool()
async def search_inventory(
    model: str = "my",
    condition: str = "used",
    zip: str = "30096",
    range: int = 0,
    sort: str = "Price",
    sort_order: str = "asc",
    offset: int = 0,
    count: int = 50,
    year_min: int = 0,
    year_max: int = 0,
    odometer_max: int = 0,
) -> str:
    """Search Tesla inventory using the v4 API.

    Requires acquire_cookies() to have been called first.

    Args:
        model: Model code — my (Model Y), m3 (Model 3), ms (Model S), mx (Model X).
        condition: 'used' or 'new'.
        zip: ZIP code for location-based search.
        range: Search radius in miles. 0 = nationwide.
        sort: Sort field — Price, Year, or Odometer.
        sort_order: 'asc' or 'desc'.
        offset: Pagination offset (0-based).
        count: Number of results to request (API returns max ~24 per page).
        year_min: Minimum year filter (e.g. 2024). 0 = no filter.
        year_max: Maximum year filter (e.g. 2026). 0 = no filter.
        odometer_max: Maximum odometer in miles (e.g. 21000). 0 = no filter.

    Returns:
        JSON string with {total, count, raw_file, vehicles: [{VIN, Year, TrimName, TotalPrice, Odometer, ...}]}.
        Vehicles contain only essential fields (~18 fields instead of 123).
        Raw full data is saved to results/ for offline processing.
    """
    cookies = _cookies.cookies
    if not cookies:
        return json.dumps({"error": "No cookies available. Call acquire_cookies() first."})

    client = InventoryClient(cookies)

    # Build API-level options for year filtering
    options: dict = {}
    if year_min or year_max:
        y_lo = year_min or 2010
        y_hi = year_max or 2030
        options["Year"] = [str(y) for y in builtins.range(y_lo, y_hi + 1)]

    try:
        data = client.fetch_page(
            model=model,
            condition=condition,
            zip_code=zip,
            search_range=range,
            offset=offset,
            count=count,
            arrangeby=sort,
            order=sort_order,
            options=options,
        )
    except RuntimeError as e:
        if "403" in str(e) or "429" in str(e):
            _cookies.invalidate()
        return json.dumps({"error": str(e)})

    total = data.get("total_matches_found", 0)
    results = data.get("results", [])

    # Save raw full data to disk (for offline processing)
    RESULTS_DIR.mkdir(exist_ok=True)
    raw_file = RESULTS_DIR / f"raw_{model}_{condition}_{int(time.time())}.json"
    raw_file.write_text(json.dumps({"total": total, "count": len(results), "results": results}))

    # Client-side filtering (safety net if API options don't fully work)
    if year_min:
        results = [v for v in results if v.get("Year", 0) >= year_min]
    if year_max:
        results = [v for v in results if v.get("Year", 9999) <= year_max]
    if odometer_max:
        results = [v for v in results if v.get("Odometer", 999999) <= odometer_max]

    # Return slim fields only
    return json.dumps({
        "total": total,
        "count": len(results),
        "offset": offset,
        "raw_file": str(raw_file),
        "vehicles": [_slim_vehicle(v) for v in results],
    })


@mcp.tool()
async def search_top_n(
    model: str = "my",
    condition: str = "used",
    zip: str = "30096",
    range: int = 0,
    sort: str = "Price",
    sort_order: str = "asc",
    top_n: int = 30,
    year_min: int = 0,
    year_max: int = 0,
    odometer_max: int = 0,
) -> str:
    """Search Tesla inventory with automatic pagination and VIN deduplication.

    Internally pages through results until top_n unique vehicles are collected
    (or results are exhausted). Much more efficient than calling search_inventory
    multiple times — one call returns up to top_n deduplicated vehicles.

    Requires acquire_cookies() to have been called first.

    Args:
        model: Model code — my (Model Y), m3 (Model 3), ms (Model S), mx (Model X).
        condition: 'used' or 'new'.
        zip: ZIP code for location-based search.
        range: Search radius in miles. 0 = nationwide.
        sort: Sort field — Price, Year, or Odometer.
        sort_order: 'asc' or 'desc'.
        top_n: Number of unique vehicles to return (default 30).
        year_min: Minimum year filter (e.g. 2024). 0 = no filter.
        year_max: Maximum year filter (e.g. 2026). 0 = no filter.
        odometer_max: Maximum odometer in miles (e.g. 21000). 0 = no filter.

    Returns:
        JSON string with {total, returned, raw_file, vehicles: [{VIN, Year, TrimName, TotalPrice, Odometer, ...}]}.
        Vehicles contain only essential fields (~18 fields instead of 123).
        Raw full data is saved to results/ for offline processing.
    """
    cookies = _cookies.cookies
    if not cookies:
        return json.dumps({"error": "No cookies available. Call acquire_cookies() first."})

    client = InventoryClient(cookies)

    # Build API-level options for year filtering
    options: dict = {}
    if year_min or year_max:
        y_lo = year_min or 2010
        y_hi = year_max or 2030
        options["Year"] = [str(y) for y in builtins.range(y_lo, y_hi + 1)]

    try:
        total, vehicles = client.fetch_top_n(
            model=model,
            condition=condition,
            n=top_n,
            zip_code=zip,
            search_range=range,
            arrangeby=sort,
            order=sort_order,
            options=options,
            year_min=year_min,
            year_max=year_max,
            odometer_max=odometer_max,
        )
    except RuntimeError as e:
        if "403" in str(e) or "429" in str(e):
            _cookies.invalidate()
        return json.dumps({"error": str(e)})

    # Save raw full data to disk (one combined file)
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = int(time.time())
    raw_file = RESULTS_DIR / f"topn_{model}_{condition}_{ts}.json"
    raw_file.write_text(json.dumps({"total": total, "count": len(vehicles), "results": vehicles}))

    # Save slim version to disk for inspection
    slim_vehicles = [_slim_vehicle(v) for v in vehicles]
    slim_file = RESULTS_DIR / f"topn_{model}_{condition}_{ts}_slim.json"
    slim_file.write_text(json.dumps({"total": total, "returned": len(slim_vehicles), "vehicles": slim_vehicles}, indent=2))

    # Return file paths only (no vehicles in response — data stays on disk)
    return json.dumps({
        "total": total,
        "returned": len(slim_vehicles),
        "raw_file": str(raw_file),
        "slim_file": str(slim_file),
    })


@mcp.tool()
async def merge_results(
    raw_files: list[str],
    filename: str,
) -> str:
    """Merge multiple search_top_n raw files into one CSV file.

    Reads raw files server-side, extracts slim fields, flattens for CSV,
    and saves a combined CSV — avoids passing large data through the LLM context.

    Args:
        raw_files: List of raw file paths returned by search_top_n.
        filename: Output filename within results/ directory (should end with .csv).

    Returns:
        Confirmation with file path and row count.
    """
    RESULTS_DIR.mkdir(exist_ok=True)

    all_rows: list[dict] = []

    for fpath in raw_files:
        p = Path(fpath)
        if not p.exists():
            continue

        data = json.loads(p.read_text())
        vehicles = data.get("results", [])
        for v in vehicles:
            all_rows.append(_flatten_vehicle(_slim_vehicle(v)))

    if not all_rows:
        return "No vehicles found in the provided files."

    # Sort by TotalPrice ascending
    all_rows.sort(key=lambda r: r.get("TotalPrice", 0))

    # Write CSV
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_SLIM_FIELDS)
    writer.writeheader()
    writer.writerows(all_rows)

    out = RESULTS_DIR / filename
    out.write_text(buf.getvalue())

    return f"Saved {len(all_rows)} vehicles to {out}"


@mcp.tool()
async def save_to_postgres(
    raw_files: list[str],
    condition: str = "used",
) -> str:
    """Save scraped vehicles from raw JSON files into PostgreSQL.

    Reads raw files server-side, extracts slim fields, and inserts into
    tesla_used or tesla_new table. Each call is a timestamped snapshot
    (INSERT, not UPSERT) so price changes are tracked over time.

    Requires PostgreSQL running at 192.168.31.61:5432.

    Args:
        raw_files: List of raw file paths returned by search_top_n.
        condition: 'used' or 'new' — determines target table.

    Returns:
        Confirmation with row count.
    """
    from tesla_mcp.db import insert_vehicles

    all_vehicles: list[dict] = []
    for fpath in raw_files:
        p = Path(fpath)
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        for v in data.get("results", []):
            all_vehicles.append(_slim_vehicle(v))

    if not all_vehicles:
        return "No vehicles found in the provided files."

    count = await insert_vehicles(all_vehicles, condition=condition)
    table = "tesla_used" if condition == "used" else "tesla_new"
    return f"Inserted {count} vehicles into {table}"


@mcp.tool()
async def save_results(content: str, filename: str) -> str:
    """Save content to the results/ directory.

    Args:
        content: String content to save (typically JSON).
        filename: Filename within results/ directory.

    Returns:
        Confirmation with file path and size.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / filename
    path.write_text(content)
    return f"Saved to {path} ({len(content)} bytes)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
