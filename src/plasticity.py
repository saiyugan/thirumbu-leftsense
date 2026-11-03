"""
Behavioural model of memristive multi-timescale plasticity.

  G_total = G_slow + g_fast

  g_fast   volatile state. Updated every window at a rate scaled by
           confidence, and relaxing exponentially toward zero. An isolated
           observation moves it and then fades away.

  G_slow   non-volatile state. Changes ONLY when the consolidation gate
           opens: sustained, confident, directionally consistent evidence.

This is the computational abstraction of the volatile-to-non-volatile
transition reported for memristive devices under repeated stimulation.

IMPORTANT FRAMING, stated the same way everywhere:
  "Memristive dynamics are modelled in the prototype; physical device
   implementation is the proposed scaling path."

No device material, topology, fabrication process, energy, retention or
endurance figure is claimed anywhere in this code or its outputs.
"""

import math

from config import FAST, SLOW, GATE, ROLLBACK, HOURS_PER_FRAME


class ConsolidationGatedState:
    def __init__(self):
        self.reset(0.0)

    # ------------------------------------------------------------------
    def reset(self, initial_slow):
        self.G_slow = float(initial_slow)
        self.g_fast = 0.0
        self._direction_ewma = 0.0
        self.agreement = 0.0
        self.persist_hours = 0.0
        self.consolidation = 0.0
        self.gate_open = False
        self.consolidations = 0
        self.rollbacks = 0
        self.checkpoints = []
        self._watch = None
        self.last_event = ""

    @property
    def total(self):
        return max(0.0, min(1.0, self.G_slow + self.g_fast))

    # ------------------------------------------------------------------
    def update(self, observation, confidence, learn_enabled=True):
        """One observation window. Returns a dict describing what happened."""
        dt = HOURS_PER_FRAME
        error = observation - self.total

        # ---- fast, volatile adaptation (rate scaled by confidence) ----
        if learn_enabled:
            self.g_fast += FAST["eta"] * confidence * error * dt * 4.0

        # ---- volatile relaxation toward the consolidated state ----
        self.g_fast *= math.exp(-dt / FAST["tau_hours"])

        # ---- directional stability of the fast state ----
        a = min(1.0, dt / GATE["agreement_tau_hours"])
        self._direction_ewma = (1 - a) * self._direction_ewma + a * self.g_fast
        self.agreement = self._compute_agreement()

        # ---- consolidation gate ----
        self.gate_open = (
            confidence >= GATE["confidence_min"]
            and abs(self.g_fast) >= GATE["magnitude_min"]
            and self.agreement >= GATE["agreement_min"]
        )
        if self.gate_open:
            self.persist_hours += dt
        else:
            self.persist_hours = max(
                0.0, self.persist_hours - GATE["decay_multiplier"] * dt)
        self.consolidation = min(1.0, self.persist_hours / GATE["persist_hours"])

        event = ""
        if self.consolidation >= 1.0:
            event = self._consolidate()

        # NOTE: rollback must be judged against the COMMITTED state, not the
        # prediction error. Fast memory erases the prediction error within
        # about an hour, so using it meant rollback could never fire - found
        # by the selftest.
        slow_error = observation - self.G_slow
        rollback_event = self._check_rollback(slow_error, confidence, dt)
        if rollback_event:
            event = rollback_event

        if event:
            self.last_event = event

        return {
            "error": error,
            "gate_open": self.gate_open,
            "agreement": self.agreement,
            "consolidation": self.consolidation,
            "event": event,
        }

    # ------------------------------------------------------------------
    def _compute_agreement(self):
        """Directional consistency of the volatile state.

        The fast state must point the same way as its own recent average, and
        that average must be substantial. Note what this deliberately does NOT
        require: that the fast state has stopped moving. An earlier version
        scored agreement as |u|/|g|, which suppressed consolidation during
        exactly the sustained changes we most want to commit - the EWMA always
        lags a steadily growing signal. Found by the selftest.

        Division of labour: agreement rejects NOISY evidence, the persistence
        timer rejects SHORT evidence. Both must pass."""
        g, u = self.g_fast, self._direction_ewma
        if abs(g) < 1e-6 or abs(u) < 1e-6:
            return 0.0
        if (g > 0) != (u > 0):
            return 0.0
        return min(1.0, abs(u) / GATE["magnitude_min"])

    def _consolidate(self):
        self.checkpoints.append(self.G_slow)
        if len(self.checkpoints) > ROLLBACK["max_checkpoints"]:
            self.checkpoints.pop(0)
        moved = SLOW["eta"] * self.g_fast
        self.G_slow = max(0.0, min(1.0, self.G_slow + moved))
        self.g_fast -= moved
        self.persist_hours = 0.0
        self.consolidation = 0.0
        self.consolidations += 1
        self._watch = {"hours": 0.0, "sign": 1.0 if moved > 0 else -1.0,
                       "against": 0.0}
        return "CONSOLIDATED"

    def _check_rollback(self, slow_error, confidence, dt):
        """After committing, keep watching. If confident evidence contradicts
        what we just wrote, revert to the checkpoint rather than living with a
        permanent mistake.

        slow_error = observation - G_slow, i.e. how wrong the COMMITTED plan
        is right now, independent of whatever the volatile state is doing."""
        if self._watch is None:
            return ""
        self._watch["hours"] += dt
        if self._watch["hours"] > ROLLBACK["watch_hours"]:
            self._watch = None
            return ""
        contradicts = (confidence >= GATE["confidence_min"]
                       and abs(slow_error) >= ROLLBACK["contradiction_min"]
                       and ((slow_error > 0) != (self._watch["sign"] > 0)))
        if contradicts:
            self._watch["against"] += dt
        else:
            self._watch["against"] = max(0.0, self._watch["against"] - dt)
        if self._watch["against"] >= ROLLBACK["sustain_hours"]:
            if self.checkpoints:
                self.G_slow = self.checkpoints.pop()
            self.rollbacks += 1
            self._watch = None
            self.persist_hours = 0.0
            self.consolidation = 0.0
            return "ROLLBACK"
        return ""

    # ------------------------------------------------------------------
    def power_cycle(self):
        """Device removed overnight. The volatile state is lost; the
        consolidated state is retained.

        MODELLED non-volatile behaviour - not measured hardware retention."""
        self.g_fast = 0.0
        self._direction_ewma = 0.0
        self.persist_hours = 0.0
        self.consolidation = 0.0
        self.agreement = 0.0
        self.last_event = "POWER CYCLE"
