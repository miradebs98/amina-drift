"""Tunable knobs for the drift engine — all transparent (a compliance officer can read these).

Risk is a 0–100 `risk_score` (tier = derived band). The scorer is a weighted sum of drift terms;
nothing is a black box. Tuned for the Meridian Sands hero case (onboards 28/LOW → ~82/HIGH).
"""
from __future__ import annotations

# --- Concept axes for the interpretable profile embedding (Meridian: SaaS→crypto, UAE→offshore) ---
CONCEPT_AXES = ["saas_analytics", "crypto_web3", "offshore_expansion", "uae_domestic"]

AXIS_SEEDS = {
    "saas_analytics": ["saas", "analytics", "dashboard", "subscription", "software", "sme"],
    "crypto_web3": ["crypto", "web3", "bitcoin", "btc", "eth", "stablecoin", "token", "brokerage", "trading", "digital asset", "treasury"],
    "offshore_expansion": ["bvi", "seychelles", "offshore", "expansion", "subsidiary", "international", "corridor"],
    "uae_domestic": ["uae", "abu dhabi", "adgm", "emirates", " ae "],
}

# When a concept axis MOVES, which assertion predicate it implicates (slow drift -> assertion).
AXIS_TO_PREDICATE = {
    "crypto_web3": "business_model",
    "offshore_expansion": "operating_geographies",
}

# --- Risk taxonomy: how much breaking THIS belief moves the score (RM-grade predicate set) -------
RISK_WEIGHT = {
    "sanctions_status": 1.0,
    "pep_status": 0.95,
    "ubo": 0.9,
    "adverse_media_status": 0.9,
    "regulatory_status": 0.85,
    "source_of_funds": 0.75,
    "business_model": 0.7,
    "product_mix": 0.7,
    "digital_asset_policy": 0.7,
    "expected_monthly_volume": 0.7,
    "operating_geographies": 0.55,
    "counterparty_geographies": 0.55,
    "source_of_wealth": 0.5,
    "ownership_structure": 0.6,
    "domicile": 0.4,
    "legal_form": 0.4,
    "activity_level": 0.45,
    "domain": 0.25,
}
DEFAULT_RISK_WEIGHT = 0.4

# --- Evidence reliability by SOURCE TYPE: how much a contradiction from this kind of event counts ---
# A homepage/website diff is SOFT evidence (a marketing tweak, not a confirmed change), so it must not
# score like a regulatory filing — this is what separates organic expansion (HashKey, website-driven)
# from confirmed escalation (enforcement/registry/screen). Scales the cheap-LLM verdict strength; the
# deterministic paths (sanctions/PEP screen, envelope) are authoritative and already full-weight.
EVIDENCE_WEIGHT = {
    "sanctions_hit": 1.0, "pep_hit": 1.0, "registry_change": 1.0,   # authoritative records
    "ownership_change": 0.95, "transaction": 0.9, "news": 0.85,     # reported / confirmed events
    "funding": 0.8,
    "website_change": 0.45,                                         # a site diff is a SOFT signal
}
DEFAULT_EVIDENCE_WEIGHT = 0.7

# direction of the risk impact when this predicate drifts (+1 up, 0 neutral, -1 down/positive).
# Most KYC drifts increase risk; SoW/funding is a *question* not a hit, so a softer +.
# This is the seam for case (c) — a big surprise with ~0 risk impact. TODO: LLM/taxonomy sets sign.
RISK_DIRECTION = {
    "source_of_wealth": 0.4,
}
DEFAULT_RISK_DIRECTION = 1.0

# --- Risk score (0–100): two-channel re-derived level -----------------------------------------
RISK_SCORE_FULL_DRIFT = 10.0        # (legacy, unused) Σ risk_impact for the old saturate() mapping
ACCUMULATION_CAP = 88               # non-designation drift asymptotes here (high-HIGH); 88–100 reserved
                                    # for an actual sanctions designation so "lots of drift" ≠ "sanctioned"
BREADTH_DECAY = 0.6                 # each ADDITIONAL co-moving drift counts × decay^rank (connect-the-dots
                                    # weight); higher → breadth matters more, lower → more single-driver
DRIFT_SATURATION = 1.0             # accumulated severity-weighted drift that maps ~63% toward the cap
CRITICAL_DESIGNATION = ("sanctions_status",)   # authoritative-only beliefs that jump straight to ceiling
CRIT_DESIGNATION_MIN = 0.7          # min invalidation for the critical channel to fire (a real hit)
TIER_BANDS = [("LOW", 0), ("MEDIUM", 34), ("HIGH", 67)]   # 0–100 bands — a LABEL/cadence only, NOT a trigger

# --- Flagging: a flag needs both enough surprise AND enough risk movement -----------------------
SURPRISE_FLAG_THRESHOLD = 0.30      # below this = case (a): score drifts gently, visualize only
RISK_DELTA_FLAG_POINTS = 6          # min risk_score jump (points) to raise a flag

# --- Breadth: connect-the-dots — co-movement ACROSS dimensions is the real KYC-drift signal ------
VELOCITY_ALERT_POINTS = 8           # a one-tick jump of ≥ this many score points → drift alert (rate, not band)
BREADTH_MIN_DIMS = 3                 # ≥ this many distinct dimensions drifting → combination alert + score boost
BREADTH_BONUS = 0.12                # ×Σimpact per dimension beyond 2 (3 dims = +0.12, 4 = +0.24)
MATERIAL_IMPACT = 0.05              # a per-assertion risk_impact above this counts toward breadth
CRITICAL_PREDICATES = ("sanctions_status", "pep_status", "adverse_media_status")
CRITICAL_CONTRA = 0.7               # one high-severity hit on these fires an alert regardless of tier/breadth

# --- Slow-drift trajectory alarms (early warning, before any hard contradiction) ----------------
TRAJECTORY_NOISE_FLOOR = 0.10
TRAJECTORY_ALARM_DISTANCE = 0.33
TRAJECTORY_VELOCITY_ALARM = 0.18

# --- Envelope breach -------------------------------------------------------------------------
ENVELOPE_NEW_JURISDICTION = 0.6     # one out-of-set jurisdiction = material drift (offshore = higher)

# --- Confidence decay -------------------------------------------------------------------------
STALENESS_DECAY_PER_YEAR = 0.02
STALENESS_CAP = 0.30
STALE_STATUS_BELOW = 0.45

# --- Drift-magnitude (SURPRISE) term weights — the transparent weighted sum ----------------------
W_CONTRADICTION = 1.0
W_STALENESS = 0.4
W_ENVELOPE = 0.9
W_TRAJECTORY = 1.0
