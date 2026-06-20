# Layer-1 sources — connector roster & status

Every source is a `Connector` that emits the same `EvidenceEvent` shape (schema in
`shared/schemas/evidence.py`). The drift engine (Miguel) consumes the merged stream — it doesn't
care which source an event came from. **Add a source = subclass `Connector`, add one line to
`runner.LIVE_CONNECTORS`.**

## Status (2026-06-20)
| Connector | Source | Key needed | Status | Emits | Cases |
|---|---|---|---|---|---|
| `sec_earnings.py` | **SEC EDGAR** filings (+ earnings calls) | none (UA) / AV for calls | ✅ **live, tested** (12 real Coinbase filings) | NEWS, OWNERSHIP_CHANGE | Coinbase |
| `wayback.py` | **Wayback Machine** CDX (website change over time) | none | ✅ **live, tested** (8 real homepage changes 2019→2024) | WEBSITE_CHANGE | Coinbase |
| `news_rss.py` | **Google News RSS** | none | ✅ **live, tested** (12 articles) | NEWS | both |
| `gleif.py` | **GLEIF** LEI + ownership graph | none | ✅ **live, tested** (real LEI record) | REGISTRY_CHANGE, OWNERSHIP_CHANGE | Coinbase |
| `gdelt.py` | **GDELT** adverse media + tone | none | ✅ live (rate-limited on burst → degrades gracefully) | NEWS | both |
| `fixtures.py` | authored/cached events | none | ✅ tested (8 Meridian, 7 Coinbase) | all | both (Meridian only) |
| `stubs.py::SanctionsConnector` | OpenSanctions / yente | none (free) | ⬜ stub | SANCTIONS_HIT, PEP_HIT | both |
| `stubs.py::RegistryConnector` | ZEFIX / Companies House / ADGM | varies | ⬜ stub | REGISTRY_CHANGE | both |
| `stubs.py::FundingConnector` | Crunchbase / funding news | — | ⬜ stub (derivable from news) | FUNDING | both |

**Meridian Sands is fictional** → it has no live data; its 8 events come from the authored
fixture and that's correct. **Coinbase is real** → it gets real, cited evidence from the live
connectors. The `evidence_quote`/`source_url` on each event is the citation the engine grounds on.

## Run it
```bash
# offline (default): replay fixtures, no network, no keys — deterministic demo
python -m backend.ingest.runner meridian-sands
python -m backend.ingest.runner coinbase-global

# live: hit the real sources (each caches to data/fixtures/*.cache.json for offline reuse)
export SEC_USER_AGENT="amina-drift (you@email)"
OFFLINE_DEMO=false python -m backend.ingest.runner coinbase-global --live
```

## Design notes
- **Connectors stay dumb**: they emit facts + a `source_url`. They do NOT decide relevance or
  drift — that's the engine. (Keeps Mira's lane clean from Miguel's.)
- **Resolution**: events are stamped `customer_id` here because we query the source BY the
  customer's identifiers (ticker/LEI/domain/name) with a `resolution_confidence` (name-only
  matches get a lower score). The dedicated `resolve/` step refines borderline cases.
- **Offline-safe**: every live fetch caches to `data/fixtures/`; on any error the connector falls
  back to cache → 0 events, never a crash. The stage demo runs with `OFFLINE_DEMO=true`.
- **Cost**: these connectors are ~free HTTP (no LLM). The optional Level-2 SEC enhancement
  (filing text → embed → relevance-filter) is where grain_lite's embedder = the Stage-1 gate.

## Next (Mira's creative space)
1. Fill the **sanctions** stub (OpenSanctions match API — doubles as entity resolution).
2. Add **Level-2 SEC**: download filing text → `grain_lite` chunk/embed → keep passages relevant
   to each assertion → richer cited events.
3. Add a **registry** for non-US entities (ZEFIX/ADGM) so future non-listed customers work live.
4. Wire the **cost meter** around any LLM use (Level-2) for the Cost-Efficiency axis.
