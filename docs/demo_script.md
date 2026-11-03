# THIRUMBU - live demo script (2-3 minutes)

Run `python src/main.py --selftest` before you walk in. Last line must read
`SELFTEST: PASS`. If it does not, do not demo.

Timing: the dashboard runs ~1.5 patient-hours per real second, so one waking
day takes about 11 seconds on screen.

| # | You click | Say | Watch for |
|---|---|---|---|
| 1 | START CALIBRATION | "Per-patient calibration: we normalise to this person's own cervical range, because a stiff neck is not neglect." | phase CALIBRATED |
| 2 | START MONITORING | "Two channels. Passive head-yaw-relative-to-trunk exploration, and sparse active orienting probes where we know the answer." | confidence climbs past 0.9 |
| 3 | TRANSIENT GOOD SPELL | "The patient has a genuinely good few hours. Both controllers reduce cueing, and that is correct. Watch what does NOT happen." | g_fast moves, G_slow flat, consolidation bar stays low |
| 4 | INVALID CONTEXT | "Now the patient is lying on their left side. There is nothing on the left to explore. The passive channel says severe neglect and it is lying." | confidence collapses, THIRUMBU withholds cues, naive estimate climbs |
| 5 | (click again to restore) | "Context restored." | confidence recovers |
| 6 | PERSISTENT RECOVERY | "Genuine recovery over days. Same fast response - but now the evidence is consistent and it persists." | consolidation bar fills, CONSOLIDATED fires, G_slow steps down |
| 7 | POWER CYCLE | "Device comes off overnight. Volatile state is gone. The committed therapy plan survives." | g_fast zeroes, G_slow unchanged, naive resets to enrolment |
| 8 | DETERIORATION | "A new decline. Therapy has to climb back." | dose re-escalates |

Close on the metrics panel: mean dose error, and cues delivered on
untrustworthy data.

**Say this once, out loud:** "Every number on this screen comes from a
synthetic patient model. Memristive dynamics are modelled; physical device
implementation is the proposed scaling path."
