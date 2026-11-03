"""
Experiment metrics.

Every number produced here describes the SIMULATION, not a patient and not a
device. The GUI labels them SIMULATED RESULTS and the PPT must do the same.

Dose error is the headline metric: how far each controller's therapy dose sat
from the dose the simulated ground truth would have justified. It is only
computable because we built the patient; a real device cannot compute it,
which is exactly why the confidence and consolidation machinery exists.
"""

from config import HOURS_PER_FRAME, DOSE


def ideal_dose(true_severity):
    lo, hi = DOSE["minimum"], DOSE["maximum"]
    return lo + (hi - lo) * max(0.0, min(1.0, true_severity))


class MetricsTracker:
    def __init__(self, controllers):
        self.controllers = controllers
        self.reset()

    def reset(self):
        self.frames = 0
        self.hours = 0.0
        self.dose_error_sum = {c.name: 0.0 for c in self.controllers}
        self.overdose_hours = {c.name: 0.0 for c in self.controllers}
        self.underdose_hours = {c.name: 0.0 for c in self.controllers}
        self.transient_episodes = 0
        self.transient_consolidations = 0
        self.persistent_episodes = 0
        self.persistent_consolidations = 0
        self.deterioration_episodes = 0
        self.reescalation_hours = None
        self._reescalation_clock = None
        self._transient_watch = None
        self._persistent_watch = None

    # ------------------------------------------------------------------
    def note_transient(self, thirumbu):
        self.transient_episodes += 1
        self._transient_watch = {"start": thirumbu.state.consolidations,
                                 "hours": 0.0}

    def note_persistent(self, thirumbu):
        self.persistent_episodes += 1
        self._persistent_watch = {"start": thirumbu.state.consolidations,
                                  "hours": 0.0}

    def note_deterioration(self, thirumbu, true_severity):
        self.deterioration_episodes += 1
        self._reescalation_clock = {"hours": 0.0,
                                    "target": ideal_dose(true_severity) - 0.12}

    # ------------------------------------------------------------------
    def update(self, true_severity, thirumbu):
        self.frames += 1
        self.hours += HOURS_PER_FRAME
        target = ideal_dose(true_severity)

        for c in self.controllers:
            err = c.dose - target
            self.dose_error_sum[c.name] += abs(err) * HOURS_PER_FRAME
            if err > 0.12:
                self.overdose_hours[c.name] += HOURS_PER_FRAME
            elif err < -0.12:
                self.underdose_hours[c.name] += HOURS_PER_FRAME

        # transient window: consolidation here would be a specificity failure
        if self._transient_watch is not None:
            self._transient_watch["hours"] += HOURS_PER_FRAME
            if thirumbu.state.consolidations > self._transient_watch["start"]:
                self.transient_consolidations += 1
                self._transient_watch = None
            elif self._transient_watch["hours"] > 12.0:
                self._transient_watch = None

        # persistent window: consolidation here is a sensitivity success
        if self._persistent_watch is not None:
            self._persistent_watch["hours"] += HOURS_PER_FRAME
            if thirumbu.state.consolidations > self._persistent_watch["start"]:
                self.persistent_consolidations += 1
                self._persistent_watch = None
            elif self._persistent_watch["hours"] > 72.0:
                self._persistent_watch = None

        # time for THIRUMBU to raise the dose again after a decline
        if self._reescalation_clock is not None:
            self._reescalation_clock["hours"] += HOURS_PER_FRAME
            if thirumbu.dose >= self._reescalation_clock["target"]:
                self.reescalation_hours = self._reescalation_clock["hours"]
                self._reescalation_clock = None
            elif self._reescalation_clock["hours"] > 96.0:
                self._reescalation_clock = None

    # ------------------------------------------------------------------
    def mean_dose_error(self, name):
        if self.hours <= 0:
            return 0.0
        return self.dose_error_sum[name] / self.hours

    def specificity(self):
        if self.transient_episodes == 0:
            return None
        kept = self.transient_episodes - self.transient_consolidations
        return kept / self.transient_episodes

    def sensitivity(self):
        if self.persistent_episodes == 0:
            return None
        return self.persistent_consolidations / self.persistent_episodes

    def table(self):
        rows = []
        for c in self.controllers:
            rows.append({
                "name": c.name,
                "dose_error": self.mean_dose_error(c.name),
                "over_h": self.overdose_hours[c.name],
                "under_h": self.underdose_hours[c.name],
                "cues": c.cues_delivered,
                "bad_cues": c.cues_in_invalid_context,
            })
        return rows
