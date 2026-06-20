// Data access facade. Switches between offline fixtures and the live FastAPI
// backend via NEXT_PUBLIC_DATA_MODE. Fixtures is the default so the demo link
// works with zero backend. The live client (client.ts) mirrors these signatures.

import * as fixtures from "./fixtures";

export const DATA_MODE = process.env.NEXT_PUBLIC_DATA_MODE ?? "fixtures";
export const isLive = DATA_MODE === "live";

// Until the live client lands, everything routes through fixtures.
export const listCases = fixtures.listCases;
export const getCase = fixtures.getCase;
