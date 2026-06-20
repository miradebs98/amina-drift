"""Clock — the engine is clock-agnostic, which is what makes the demo possible.

In production a `RealClock` ticks once a day. In the demo a `SimClock` fast-forwards through
the GenTwo timeline (2019->2026) in ~30 seconds. The SAME engine code runs against both — only
the clock source changes. So we don't wait months to collect data; we replay real history fast.
"""
from __future__ import annotations

from datetime import date, datetime, timezone


class Clock:
    """Source of 'now'. The drift engine reads this; it never calls datetime.now() directly."""

    def now(self) -> date:
        raise NotImplementedError


class RealClock(Clock):
    def now(self) -> date:
        return datetime.now(timezone.utc).date()


class SimClock(Clock):
    """A virtual clock you advance manually over a compressed timeline."""

    def __init__(self, start: date):
        self._now = start

    def now(self) -> date:
        return self._now

    def advance_to(self, d: date) -> None:
        if d < self._now:
            raise ValueError(f"clock cannot go backwards: {d} < {self._now}")
        self._now = d
