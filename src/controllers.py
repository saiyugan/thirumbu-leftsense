"""
Three therapy-dosing controllers, run side by side on the identical
observation stream. That is what turns the demo into an experiment.

  A  FIXED DOSE       the current standard: a cue schedule set at discharge
                      and never revisited.
  B  NAIVE ADAPTIVE   rolling-average fading. Adapts to every observation,
                      including unreliable ones. This is the obvious design,
                      and it is the one we are arguing against.
  C  THIRUMBU         confidence-gated action + consolidation-gated learning.

All three receive the same confidence value; only C is allowed to use it.
"""

import math

from config import (CONFIDENCE, DOSE, NAIVE, SENSING, HOURS_PER_FRAME)
from plasticity import ConsolidationGatedState


def estimate_confidence(obs, prev_conf):
    """Confidence that this observation window means what it appears to mean.

    Three ingredients, all defensible:
      context validity  - an invalid context makes the passive channel lie
      probe support     - ground-truthed probes in recent memory
      channel agreement - passive and probe channels telling the same story
    """
    if not obs["context_valid"]:
        raw = CONFIDENCE["context_floor"]
    else:
        probe_support = min(1.0, obs["n_probes"] / 2.0)
        if obs["probe_estimate"] is None:
            agreement = 0.45
        else:
            gap = abs(obs["passive"] - obs["probe_estimate"])
            agreement = max(0.0, 1.0 - gap / CONFIDENCE["agreement_scale"])
        raw = 0.30 + 0.40 * probe_support + 0.30 * agreement
        raw = max(0.0, min(1.0, raw))

    a = min(1.0, HOURS_PER_FRAME / CONFIDENCE["ewma_tau_hours"])
    return (1 - a) * prev_conf + a * raw


def dose_from_estimate(estimate):
    lo, hi = DOSE["minimum"], DOSE["maximum"]
    return lo + (hi - lo) * max(0.0, min(1.0, estimate))


class BaseController:
    name = "BASE"

    def __init__(self, initial_estimate):
        self.estimate = float(initial_estimate)
        self.dose = dose_from_estimate(self.estimate)
        self.cues_delivered = 0
        self.cues_withheld = 0
        self.cues_in_invalid_context = 0
        self.status = "-"
        self.action = "CUE"
        self._cue_credit = 0.0

    def _deliver(self, obs, allow):
        """Cue emission. Cues accrue at a rate proportional to dose, so even
        a low dose still produces cues - just fewer of them."""
        self._cue_credit += self.dose * DOSE["max_cues_per_hour"] * HOURS_PER_FRAME
        fires = self._cue_credit >= 1.0
        if fires:
            self._cue_credit -= 1.0
        if allow and fires:
            self.cues_delivered += 1
            if not obs["context_valid"]:
                self.cues_in_invalid_context += 1
            self.action = "CUE"
        elif fires:
            self.cues_withheld += 1
            self.action = "WITHHELD"
        else:
            self.action = "IDLE"

    def step(self, obs, confidence):
        raise NotImplementedError


class FixedDoseController(BaseController):
    name = "A - FIXED DOSE"

    def step(self, obs, confidence):
        self.status = "no adaptation"
        self._deliver(obs, allow=True)
        return self.dose

    def power_cycle(self):
        pass


class NaiveAdaptiveController(BaseController):
    """Rolling-average fading with no gating at all. Adapts to good spells,
    bad hours and invalid-context readings identically, and has a single
    timescale, so it cannot both track recovery and ignore noise."""
    name = "B - NAIVE ADAPTIVE"

    def step(self, obs, confidence):
        a = min(1.0, HOURS_PER_FRAME / NAIVE["tau_hours"])
        self.estimate = (1 - a) * self.estimate + a * obs["z"]
        self.dose = dose_from_estimate(self.estimate)
        self.status = "adapting (ungated)"
        self._deliver(obs, allow=True)
        return self.dose

    def power_cycle(self):
        """Session adaptation held in volatile working memory is lost when the
        device is doffed, unless explicitly committed to storage - which this
        controller has no mechanism to decide about."""
        self.estimate = self.initial
        self.dose = dose_from_estimate(self.estimate)


class ThirumbuController(BaseController):
    name = "C - THIRUMBU"

    def __init__(self, initial_estimate):
        super().__init__(initial_estimate)
        self.state = ConsolidationGatedState()
        self.state.reset(initial_estimate)
        self.learning = False
        self.last_event = ""

    def step(self, obs, confidence):
        learn = confidence >= CONFIDENCE["learn_reject_below"]
        info = self.state.update(obs["z"], confidence, learn_enabled=learn)
        self.learning = learn
        self.estimate = self.state.total
        self.dose = dose_from_estimate(self.estimate)

        if info["event"]:
            self.last_event = info["event"]

        if not learn:
            self.status = "learning suppressed"
        elif self.state.gate_open:
            self.status = "accumulating evidence"
        else:
            self.status = "fast adaptation only"

        allow_cue = confidence >= CONFIDENCE["cue_reject_below"]
        self._deliver(obs, allow=allow_cue)
        return self.dose

    def power_cycle(self):
        self.state.power_cycle()
        self.estimate = self.state.total
        self.dose = dose_from_estimate(self.estimate)


def build_controllers(initial_estimate):
    a = FixedDoseController(initial_estimate)
    b = NaiveAdaptiveController(initial_estimate)
    b.initial = initial_estimate
    c = ThirumbuController(initial_estimate)
    return [a, b, c]
