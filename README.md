# TeslaWebScrape

A Tesla inventory scraper built as an [MCP](https://modelcontextprotocol.io/) server, designed to run inside [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

## Why I Built This

I was shopping for a Tesla and got tired of refreshing Tesla's website every day — manually re-selecting the model, year, and filters each time. So I built this tool to scrape Tesla's inventory programmatically and save the results locally or to a database for tracking price changes over time.

## Why Not Playwright?

Tesla's inventory pages are protected by **Akamai Bot Manager**, which is one of the more aggressive bot detection systems out there. Here's what I tried and what happened:

| Approach | Result |
|----------|--------|
| `requests` / `httpx` | 403 Forbidden |
| `cloudscraper` | 403 Forbidden |
| `curl_cffi` alone | 429 with Akamai challenge page |
| Playwright (even with `stealth.js`) | 403 Forbidden |
| Puppeteer + stealth plugin | 403 Forbidden |

**What actually works:** [`nodriver`](https://github.com/nicegui-development/nodriver) — an undetected Chrome automation library. It launches a real Chrome instance that passes Akamai's fingerprinting checks. Once the cookies are acquired through `nodriver`, the actual API calls are made with [`curl_cffi`](https://github.com/lexiforest/curl_cffi), which impersonates Chrome's TLS fingerprint.

### The Two-Step Approach

```
1. nodriver (Chrome)          2. curl_cffi (API calls)
┌─────────────────────┐      ┌─────────────────────────┐
│ Visit tesla.com     │      │ Reuse Akamai cookies     │
│ Wait for Akamai JS  │ ───→ │ Call /inventory/api/v4   │
│ Extract cookies     │      │ Impersonate Chrome TLS   │
│ (~15 sec)           │      │ (~0.5 sec per page)      │
└─────────────────────┘      └─────────────────────────┘
```

Cookies are cached for 10 minutes, so subsequent searches within that window skip the browser step entirely.

## Architecture

This project is an MCP server that exposes tools to Claude Code. You interact with it through natural language via the `/tesla` skill.

```
You (natural language)
  │
  ▼
Claude Code ──→ /tesla skill ──→ MCP Server (tesla-inventory)
                                    ├── acquire_cookies()   ← nodriver
                                    ├── search_top_n()      ← curl_cffi + pagination
                                    ├── merge_results()     ← CSV export
                                    └── save_to_postgres()  ← PostgreSQL storage
```

### Two Storage Modes

1. **Local files** — Results are saved as JSON/CSV in the `results/` directory. Good for quick one-off searches.

2. **PostgreSQL** — Each scrape is inserted (not upserted) as a timestamped snapshot, so you can track price changes over time. Requires a PostgreSQL server. I run mine on a home server.

## MCP Tools

| Tool | Description |
|------|-------------|
| `acquire_cookies` | Launch Chrome via nodriver, bypass Akamai, cache cookies (10-min TTL) |
| `search_inventory` | Single-page API query with filters (model, condition, year, mileage, etc.) |
| `search_top_n` | Auto-paginating search with VIN deduplication — returns top N unique vehicles |
| `merge_results` | Merge multiple raw JSON files into a single CSV |
| `save_to_postgres` | Insert scraped vehicles into PostgreSQL for historical tracking |

## Supported Models

| Code | Model |
|------|-------|
| `my` | Model Y |
| `m3` | Model 3 |
| `ms` | Model S |
| `mx` | Model X |

Both **used** and **new** inventory are supported.

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Google Chrome installed (for nodriver)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (to use the MCP server)

### Install

```bash
git clone https://github.com/JumpBearCode/TeslaWebScrape.git
cd TeslaWebScrape
uv sync
```

### Configure MCP Server

Add to your Claude Code MCP config (`.mcp.json`):

```json
{
  "mcpServers": {
    "tesla-inventory": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/TeslaWebScrape",
        "python", "-m", "tesla_mcp.server"
      ]
    }
  }
}
```

### PostgreSQL (Optional)

If you want to use the database storage mode:

1. Set up a PostgreSQL server
2. Create a `.env` file in the project root:

```
POSTGRES_PASSWORD=your_password
```

3. The tables (`tesla_used`, `tesla_new`) are created automatically on first insert

## Usage Examples

Through Claude Code with the `/tesla` skill:

```
> Scrape the top 30 cheapest used Model Y nationwide and save to CSV

> Find new Model 3 under 20,000 miles, save to PostgreSQL

> Get used Model S from 2023+, sorted by price
```

## Data Fields

Each vehicle record from Tesla's API contains 123 fields. This tool extracts 27 essential fields:

- **Identity** — VIN, Year, Model, TrimName
- **Pricing** — TotalPrice, PriceAdjustmentUsed, TransportationFee
- **Mileage** — Odometer, ActualRange
- **Appearance** — Paint, Interior, Wheels
- **Location** — City, StateProvince
- **History** — VehicleHistory, DamageDisclosure, CPORefurbishmentStatus
- **Provenance** — AcquisitionSubType, FleetVehicle, IsDemo
- **Features** — Autopilot package, HasVehiclePhotos

See [`data dictionary.md`](data%20dictionary.md) for the full field reference.

## Tech Stack

- [`fastmcp`](https://github.com/jlowin/fastmcp) — MCP server framework
- [`nodriver`](https://github.com/nicegui-development/nodriver) — Undetected Chrome automation (bypasses Akamai)
- [`curl_cffi`](https://github.com/lexiforest/curl_cffi) — HTTP client with TLS fingerprint impersonation
- [`asyncpg`](https://github.com/MagicStack/asyncpg) — Async PostgreSQL driver

## License

MIT
