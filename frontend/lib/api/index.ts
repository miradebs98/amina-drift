// Data access facade. Case data switches between offline fixtures and the live
// FastAPI backend via NEXT_PUBLIC_DATA_MODE (fixtures = default, demo-safe).
// Governance (decisions + audit) is ALWAYS live — the audit log is real, never faked.

import * as fixtures from "./fixtures";
import * as client from "./client";

export const DATA_MODE = process.env.NEXT_PUBLIC_DATA_MODE ?? "fixtures";
export const isLive = DATA_MODE === "live";

// case data — fixtures unless explicitly live
export const getCase = isLive ? client.getCase : fixtures.getCase;
export const listCases = isLive ? client.listCases : fixtures.listCases;

// governance — real backend regardless of data mode
export const postDecision = client.postDecision;
export const getAudit = client.getAudit;
export const verifyAudit = client.verifyAudit;
export { ApiError } from "./client";
