"""Network graph — the Network Risk dimension (who the customer is connected to).

Assembles a graph of connected entities for a customer from the signals we already collect, then
propagates risk: a customer connected to a sanctioned/PEP node is itself a network-risk concern.
This is the dimension almost nobody builds, and it's where "shell companies in the chain" and
"connected to a sanctioned party" become visible.

Nodes  = the customer + its UBOs/directors + investors + partners + screened entities.
Edges  = founder/director · investor · partner · owner · connection.
Flags  = sanctioned / pep (from the OpenSanctions screen; name-only matches carry needs_verify).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.ingest.base import CustomerRef, load_assertions
from backend.ingest.runner import collect

# Extract connected-entity names from event summaries (conservative: needs a corporate suffix or
# an explicit relation verb, to avoid pulling generic capitalised words).
_SUFFIX = r"(?:Ventures|Capital|Partners|Holdings|Group|Labs|Fund|Management|Bank|Securities|Technologies|Inc|Ltd|LLC|AG|GmbH)"
_INVESTOR_PATTERNS = [
    re.compile(rf"investment from (?:[A-Za-z ]*?)([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})"),
    re.compile(rf"\bfrom (?:Chinese VC |VC )?([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})"),
    re.compile(rf"led by ([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*)"),
    re.compile(rf"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})\s+invests"),
]
_PARTNER_PATTERNS = [
    re.compile(rf"partners? with ([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})", re.I),
    re.compile(rf"partnership with ([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})", re.I),
    re.compile(rf"acqui(?:re|res|sition of) ([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s+{_SUFFIX})", re.I),
]


@dataclass
class Node:
    id: str
    label: str
    type: str                       # customer | person | investor | partner | entity
    flags: list[str] = field(default_factory=list)   # sanctioned | pep
    needs_verification: bool = False
    note: str = ""


@dataclass
class Edge:
    source: str
    target: str
    relation: str                   # founder | director | investor | partner | owner | connection
    source_url: Optional[str] = None


def _nid(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" .,&")


def build_graph(customer_id: str, live: Optional[bool] = None) -> dict:
    customer = CustomerRef.load(customer_id)
    assertions = load_assertions(customer_id)
    events = collect(customer_id, live=live)

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    def add_node(name: str, ntype: str) -> Optional[str]:
        name = _clean(name)
        if not name or name.lower() == customer.legal_name.lower():
            return central
        nid = _nid(name)
        if nid not in nodes:
            nodes[nid] = Node(id=nid, label=name, type=ntype)
        return nid

    # central customer node
    central = _nid(customer.legal_name)
    nodes[central] = Node(id=central, label=customer.legal_name, type="customer")

    # 1) UBOs / directors from the KYC assertions (Identity → ownership edges)
    for a in assertions:
        pred = a.get("predicate")
        if pred in ("ubo", "directors"):
            val = a.get("value", "")
            names: list[str] = []
            try:
                names = list(json.loads(val).keys())
            except Exception:
                if val:
                    names = [val[:60]]
            for nm in names:
                nid = add_node(nm, "person")
                if nid and nid != central:
                    edges.append(Edge(central, nid, "founder" if pred == "ubo" else "director",
                                      a.get("source_url")))

    # 2) Investors / partners / acquisitions from the event stream
    for e in events:
        text = e.summary
        payload = e.payload or {}
        inv = payload.get("lead_investor")
        if inv:
            nid = add_node(inv, "investor")
            if nid and nid != central:
                edges.append(Edge(nid, central, "investor", e.source_url))
        for pat in _INVESTOR_PATTERNS:
            m = pat.search(text)
            if m:
                nid = add_node(m.group(1), "investor")
                if nid and nid != central:
                    edges.append(Edge(nid, central, "investor", e.source_url))
        for pat in _PARTNER_PATTERNS:
            m = pat.search(text)
            if m:
                nid = add_node(m.group(1), "partner")
                if nid and nid != central:
                    edges.append(Edge(central, nid, "partner", e.source_url))

    # 3) Sanctions / PEP flags from the screen (flag the matching node)
    for e in events:
        if e.type.value in ("sanctions_hit", "pep_hit"):
            screened = (e.payload or {}).get("screened_name", "")
            nid = _nid(_clean(screened))
            target = nid if nid in nodes else central
            node = nodes[target]
            flag = "pep" if e.type.value == "pep_hit" else "sanctioned"
            if flag not in node.flags:
                node.flags.append(flag)
            node.needs_verification = bool((e.payload or {}).get("needs_human_verification", True))
            node.note = e.summary[:140]

    # de-dupe edges (same relation reported by multiple articles)
    seen_e, uniq_edges = set(), []
    for e in edges:
        k = (e.source, e.target, e.relation)
        if k not in seen_e:
            seen_e.add(k)
            uniq_edges.append(e)
    edges = uniq_edges

    # 4) risk propagation: connections to a flagged node are the network-risk signal
    flagged = [n for n in nodes.values() if n.flags]
    edge_pairs = {(e.source, e.target) for e in edges} | {(e.target, e.source) for e in edges}
    connected_flagged = [n for n in flagged if n.id == central or (central, n.id) in edge_pairs]

    return {
        "customer_id": customer_id,
        "nodes": [n.__dict__ for n in nodes.values()],
        "edges": [e.__dict__ for e in edges],
        "network_risk": {
            "connected_entities": len(nodes) - 1,
            "flagged_nodes": [n.label for n in flagged],
            "elevated": bool(connected_flagged),
            "summary": (f"{len(nodes)-1} connected entities; "
                        f"{len(flagged)} carry a sanctions/PEP name-match (verify identity)."
                        if flagged else f"{len(nodes)-1} connected entities; no screening hits."),
        },
    }
