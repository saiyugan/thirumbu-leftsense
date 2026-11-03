"""
THIRUMBU - entry point.

    python src/main.py              open the interactive dashboard
    python src/main.py --selftest   run the scripted experiment headlessly

The dashboard is the artefact for the pitch. The selftest exists so that the
behaviour can be checked without a display, and so that the claims made in the
slides can be regenerated on demand.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import HOURS_PER_FRAME, CONFIDENCE                     # noqa: E402
from controllers import build_controllers, estimate_confidence     # noqa: E402
from metrics import MetricsTracker, ideal_dose                     # noqa: E402
from patient import SensorModel, SimulatedPatient                  # noqa: E402


class Simulation:
    """Owns the patient, the sensors, the three controllers and the metrics."""

    def __init__(self, seed=11, gui=None):
        self.seed = seed
        self.gui = gui
        self._build()

    def _build(self):
        self.patient = SimulatedPatient(self.seed)
        self.sensor = SensorModel(self.seed + 12)
        self.controllers = build_controllers(self.patient.severity)
        self.thirumbu = self.controllers[2]
        self.metrics = MetricsTracker(self.controllers)
        self.confidence = 0.5
        self.phase = "IDLE"
        self.last_obs = None
        self.last_event = ""
        self.hours = 0.0

    # ---------------- commands ----------------
    def calibrate(self):
        """Per-patient calibration: cervical range of motion and a symmetric
        baseline. Modelled here as establishing the initial estimate."""
        self.phase = "CALIBRATED"
        self.controllers = build_controllers(self.patient.severity)
        self.thirumbu = self.controllers[2]
        self.metrics = MetricsTracker(self.controllers)
        self.last_event = ""

    def start_monitoring(self):
        if self.phase == "IDLE":
            self.calibrate()
        self.phase = "MONITORING"

    def transient(self):
        self.patient.start_transient_relief()
        self.metrics.note_transient(self.thirumbu)
        self.last_event = ""

    def persistent(self):
        self.patient.start_persistent_recovery()
        self.metrics.note_persistent(self.thirumbu)
        self.last_event = ""

    def deterioration(self):
        self.patient.trigger_deterioration()
        self.metrics.note_deterioration(self.thirumbu,
                                        self.patient.effective_severity())
        self.last_event = ""

    def toggle_context(self):
        self.sensor.set_context(not self.sensor.context_valid)

    def power_cycle(self):
        for c in self.controllers:
            c.power_cycle()
        self.last_event = "POWER CYCLE"

    def reset(self):
        self._build()
        if self.gui is not None:
            self.gui.clear_plots()

    # ---------------- per-frame ----------------
    def step(self):
        if self.phase != "MONITORING":
            return None
        s_eff = self.patient.step()
        self.hours += HOURS_PER_FRAME
        obs = self.sensor.observe(s_eff)
        self.confidence = estimate_confidence(obs, self.confidence)

        doses = [c.step(obs, self.confidence) for c in self.controllers]
        self.metrics.update(s_eff, self.thirumbu)

        event = self.thirumbu.state.last_event
        fire = ""
        if event and event != self.last_event:
            fire = event
        self.last_event = event
        self.last_obs = obs

        return {
            "confidence": self.confidence,
            "g_fast": self.thirumbu.state.g_fast,
            "G_slow": self.thirumbu.state.G_slow,
            "true_severity": s_eff,
            "ideal_dose": ideal_dose(s_eff),
            "doses": doses,
            "consolidation": self.thirumbu.state.consolidation,
            "event": fire,
        }

    # ---------------- view model ----------------
    def snapshot(self):
        obs = self.last_obs or {"passive": 0.0, "probe": None, "z": 0.0,
                                "n_probes": 0, "context_valid":
                                    self.sensor.context_valid}
        s_eff = self.patient.effective_severity()
        st = self.thirumbu.state
        return {
            "phase": self.phase,
            "hours": self.hours,
            "passive": obs["passive"],
            "probe_text": ("-" if obs["probe"] is None
                           else "{:.3f}".format(obs["probe"])),
            "n_probes": obs["n_probes"],
            "z": obs["z"],
            "context_valid": obs["context_valid"],
            "true_severity": s_eff,
            "ideal_dose": ideal_dose(s_eff),
            "confidence": self.confidence,
            "controllers": [{
                "name": c.name, "estimate": c.estimate, "dose": c.dose,
                "action": c.action, "cues": c.cues_delivered,
                "bad_cues": c.cues_in_invalid_context, "status": c.status,
            } for c in self.controllers],
            "state": {
                "G_slow": st.G_slow, "g_fast": st.g_fast, "total": st.total,
                "agreement": st.agreement, "persist_hours": st.persist_hours,
                "gate_open": st.gate_open, "consolidation": st.consolidation,
                "consolidations": st.consolidations, "rollbacks": st.rollbacks,
                "checkpoints": len(st.checkpoints),
                "last_event": st.last_event,
                "learning": self.thirumbu.learning,
            },
            "metrics": {
                "table": self.metrics.table(),
                "specificity": self.metrics.specificity(),
                "sensitivity": self.metrics.sensitivity(),
                "transient_episodes": self.metrics.transient_episodes,
                "persistent_episodes": self.metrics.persistent_episodes,
                "reescalation": self.metrics.reescalation_hours,
            },
        }


# ======================================================================
def run(sim, hours):
    for _ in range(int(hours / HOURS_PER_FRAME)):
        sim.step()


def selftest():
    """Scripted version of the live demo, checked automatically.

    The sequence is deliberately realistic: clean stretches, a good spell,
    genuine recovery, confounded windows, a doffing, and a decline.
    """
    sim = Simulation()
    sim.start_monitoring()
    ok = True

    def check(label, condition, detail=""):
        nonlocal ok
        ok = ok and bool(condition)
        print("  [{}] {}{}".format("PASS" if condition else "FAIL", label,
                                   "  " + detail if detail else ""))

    run(sim, 10.0)
    base_slow = sim.thirumbu.state.G_slow
    print("\n1. baseline")
    check("confidence above the cue threshold",
          sim.confidence >= CONFIDENCE["cue_reject_below"],
          "conf={:.2f}".format(sim.confidence))

    print("\n2. transient good spell  (must NOT consolidate)")
    before = sim.thirumbu.state.consolidations
    sim.transient()
    run(sim, 3.0)
    fast_moved = abs(sim.thirumbu.state.g_fast)
    naive_during = sim.controllers[1].dose
    thirumbu_during = sim.thirumbu.dose
    run(sim, 12.0)
    check("fast memory responded", fast_moved > 0.03,
          "|g_fast|={:.3f}".format(fast_moved))
    check("slow memory did NOT consolidate",
          sim.thirumbu.state.consolidations == before)
    check("slow memory unchanged",
          abs(sim.thirumbu.state.G_slow - base_slow) < 0.02,
          "G_slow={:.3f}".format(sim.thirumbu.state.G_slow))
    # Both controllers reduce cueing during a genuinely good spell, and that
    # is CORRECT - the patient really is exploring better right now. The
    # difference is not the momentary dose, it is whether the therapy PLAN
    # changes. THIRUMBU's plan (slow memory) is untouched above.
    check("THIRUMBU did respond in the moment",
          thirumbu_during < 0.72 - 0.08,
          "thirumbu={:.2f} naive={:.2f}".format(thirumbu_during, naive_during))
    check("THIRUMBU dose recovered after the spell ended",
          abs(sim.thirumbu.dose - 0.72) < 0.12,
          "dose={:.2f}".format(sim.thirumbu.dose))

    print("\n3. confounded window  (must withhold cue, suppress learning)")
    slow_before = sim.thirumbu.state.G_slow
    naive_before = sim.controllers[1].estimate
    withheld_before = sim.thirumbu.cues_withheld
    sim.toggle_context()
    run(sim, 3.0)                      # let confidence collapse
    slow_mark = sim.thirumbu.state.G_slow
    run(sim, 9.0)
    check("confidence collapsed",
          sim.confidence < CONFIDENCE["cue_reject_below"],
          "conf={:.2f}".format(sim.confidence))
    check("cues withheld rather than fired on bad data",
          sim.thirumbu.cues_withheld > withheld_before,
          "withheld={}".format(sim.thirumbu.cues_withheld))
    check("consolidated memory not corrupted by the confound",
          abs(sim.thirumbu.state.G_slow - slow_mark) < 0.02)
    check("naive controller WAS corrupted by the confound",
          sim.controllers[1].estimate > naive_before + 0.06,
          "naive {:.2f} -> {:.2f}".format(naive_before,
                                          sim.controllers[1].estimate))
    sim.toggle_context()
    run(sim, 8.0)

    print("\n4. persistent recovery  (MUST consolidate)")
    before = sim.thirumbu.state.consolidations
    mark = sim.thirumbu.state.G_slow
    sim.persistent()
    run(sim, 60.0)
    check("consolidation occurred",
          sim.thirumbu.state.consolidations > before,
          "n={}".format(sim.thirumbu.state.consolidations))
    check("slow memory tracked the recovery",
          sim.thirumbu.state.G_slow < mark - 0.15,
          "G_slow {:.3f} -> {:.3f}".format(mark, sim.thirumbu.state.G_slow))

    print("\n5. power cycle  (volatile lost, consolidated retained)")
    slow_before = sim.thirumbu.state.G_slow
    sim.power_cycle()
    check("volatile state cleared", sim.thirumbu.state.g_fast == 0.0)
    check("consolidated state retained",
          abs(sim.thirumbu.state.G_slow - slow_before) < 1e-9,
          "G_slow={:.3f}".format(sim.thirumbu.state.G_slow))
    check("naive lost its session adaptation",
          abs(sim.controllers[1].estimate - sim.controllers[1].initial) < 1e-9)
    run(sim, 6.0)

    print("\n6. deterioration  (dose must climb again)")
    dose_before = sim.thirumbu.dose
    sim.deterioration()
    run(sim, 40.0)
    check("therapy dose re-escalated", sim.thirumbu.dose > dose_before + 0.10,
          "{:.2f} -> {:.2f}".format(dose_before, sim.thirumbu.dose))

    print("\n6b. premature commitment  (bounded rollback must fire)")
    rb_before = sim.thirumbu.state.rollbacks
    sim.persistent()
    run(sim, 26.0)                      # long enough to consolidate downward
    consolidated = sim.thirumbu.state.consolidations
    sim.deterioration()                 # contradicted almost immediately
    run(sim, 10.0)
    check("a consolidation had occurred before the contradiction",
          consolidated > 0)
    check("rollback reverted the premature commitment",
          sim.thirumbu.state.rollbacks > rb_before,
          "rollbacks={}".format(sim.thirumbu.state.rollbacks))
    run(sim, 20.0)

    print("\n7. end-to-end, mixed conditions")
    rows = sim.metrics.table()
    for r in rows:
        print("   {:<20} mean |dose-ideal| = {:.3f}   cues {:<4} "
              "of which on bad data {}".format(
                  r["name"], r["dose_error"], r["cues"], r["bad_cues"]))
    check("THIRUMBU beat the fixed-dose controller",
          rows[2]["dose_error"] < rows[0]["dose_error"])
    check("THIRUMBU emitted fewer cues on untrustworthy data than naive",
          rows[2]["bad_cues"] < rows[1]["bad_cues"],
          "{} vs {}".format(rows[2]["bad_cues"], rows[1]["bad_cues"]))

    spec, sens = sim.metrics.specificity(), sim.metrics.sensitivity()
    print("\n   consolidation specificity: {}".format(
        "n/a" if spec is None else "{:.0f}%".format(spec * 100)))
    print("   consolidation sensitivity: {}".format(
        "n/a" if sens is None else "{:.0f}%".format(sens * 100)))
    print("   rollbacks: {}".format(sim.thirumbu.state.rollbacks))
    print("\nSELFTEST: {}".format("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="THIRUMBU proof of concept")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    import tkinter as tk
    from gui import ThirumbuGUI

    root = tk.Tk()
    sim = Simulation(args.seed)
    app = ThirumbuGUI(root, sim)
    sim.gui = app
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
