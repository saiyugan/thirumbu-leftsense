"""
Simulated patient and sensor model.

NOTHING IN THIS FILE IS A MEASUREMENT. It is a synthetic generator used to
exercise the controller architecture. The GUI labels every number it produces
as SIMULATED, and the true severity is shown only because we, the engineers,
need a ground truth to score the controllers against - a real device never
has it.

Two sensing channels, and the distinction matters:

  PASSIVE  exploration asymmetry derived from head-yaw-relative-to-trunk.
           Dense and free, but only a proxy for attention, and confounded by
           context (a wall on the left, lying down, a vehicle turning).

  ACTIVE   sparse orienting probes. The device emits a low-intensity lateral
           cue at a known time on a known side and measures the response.
           Because we know when and where the probe was, the response is
           ground-truthed rather than correlational. This is the answer to
           "head movement is not attention".
"""

import math
import random

from config import PATIENT, SENSING, HOURS_PER_FRAME


class SimulatedPatient:
    """Latent neglect severity with recovery, transient spells and decline."""

    def __init__(self, seed=11):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.severity = PATIENT["initial_severity"]
        self.hours = 0.0
        self.recovering = False
        self.transient_until = None
        self.transient_events = 0
        self.persistent_events = 0
        self.deterioration_events = 0

    # ---------------- externally triggered events ----------------
    def start_transient_relief(self):
        """A genuinely better few hours: rested, quiet room, good light.
        Real, but not a lasting change in the deficit."""
        self.transient_until = self.hours + PATIENT["transient_hours"]
        self.transient_events += 1

    def start_persistent_recovery(self):
        """Genuine neurological/functional recovery over days."""
        self.recovering = True
        self.persistent_events += 1

    def trigger_deterioration(self):
        """A new decline - fatigue, illness, a further event."""
        self.severity = min(PATIENT["ceiling"],
                            self.severity + PATIENT["deterioration_step"])
        self.recovering = False
        self.deterioration_events += 1

    # ---------------- per-frame update ----------------
    def step(self):
        self.hours += HOURS_PER_FRAME
        if self.recovering:
            self.severity = max(PATIENT["floor"],
                                self.severity
                                - PATIENT["recovery_per_hour"] * HOURS_PER_FRAME)
        if self.transient_until is not None and self.hours > self.transient_until:
            self.transient_until = None
        return self.effective_severity()

    @property
    def in_transient(self):
        return self.transient_until is not None

    def effective_severity(self):
        """What the patient's behaviour actually looks like right now."""
        s = self.severity
        if self.in_transient:
            s -= PATIENT["transient_relief"]
        # mild fatigue cycle across the waking day
        phase = 2.0 * math.pi * (self.hours % 16.0) / 16.0
        s += PATIENT["diurnal_amplitude"] * math.sin(phase)
        return max(0.0, min(1.0, s))


class SensorModel:
    """Turns latent severity into the two observable channels."""

    def __init__(self, seed=23):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.context_valid = True
        self.recent_probes = []          # list of (hours, value)
        self.last_probe = None
        self.probe_count = 0
        self.hours = 0.0

    def set_context(self, valid: bool):
        self.context_valid = bool(valid)

    def observe(self, s_eff):
        """Returns a dict describing this observation window."""
        cfg = SENSING
        self.hours += HOURS_PER_FRAME
        # A probe is only evidence while it is fresh. Stale probes must not
        # keep propping up confidence after the context has gone bad - that
        # was a real bug found by the selftest, not a hypothetical.
        self.recent_probes = [(t, v) for (t, v) in self.recent_probes
                              if self.hours - t <= cfg["probe_expiry_hours"]]

        # ---- passive channel: exploration asymmetry index ----
        if self.context_valid:
            passive = s_eff + self.rng.gauss(0.0, cfg["passive_noise_sd"])
        else:
            # an invalid context biases the passive channel: the patient is
            # not failing to explore left, there is simply nothing to explore
            passive = (s_eff + cfg["invalid_bias"]
                       + self.rng.gauss(0.0, cfg["invalid_noise_sd"]))
        passive = max(0.0, min(1.0, passive))

        # ---- active channel: orienting probe ----
        probe = None
        if self.context_valid and self.rng.random() < cfg["probe_probability"]:
            probe = max(0.0, min(1.0,
                                 s_eff + self.rng.gauss(0.0, cfg["probe_noise_sd"])))
            self.recent_probes.append((self.hours, probe))
            if len(self.recent_probes) > cfg["probe_memory"]:
                self.recent_probes.pop(0)
            self.last_probe = probe
            self.probe_count += 1

        probe_estimate = (sum(v for _, v in self.recent_probes)
                          / len(self.recent_probes)
                          if self.recent_probes else None)

        # ---- fused observation ----
        if probe_estimate is None:
            z = passive
        else:
            w = cfg["probe_weight"]
            z = w * probe_estimate + (1.0 - w) * passive

        return {
            "passive": passive,
            "probe": probe,
            "probe_estimate": probe_estimate,
            "n_probes": len(self.recent_probes),
            "z": max(0.0, min(1.0, z)),
            "context_valid": self.context_valid,
        }
