"""
THIRUMBU - central configuration.

Every tunable number lives here so a judge can see nothing is hidden inside
the algorithms.

Label key:
  [ESTABLISHED]        published/known result
  [PROPOSED]           our design choice
  [ENGINEERING TARGET] a number we chose, not a measured result
  [OPEN QUESTION]      we do not know the right value; needs patient data
"""

# ----------------------------------------------------------------------
# TIME BASE
# One simulation frame = one 5-minute observation window of patient time.
# The GUI runs 20 frames/second, so ~10 real seconds = one 16-hour day.
# ----------------------------------------------------------------------
MINUTES_PER_FRAME = 5.0
FRAMES_PER_SECOND = 20
HOURS_PER_FRAME = MINUTES_PER_FRAME / 60.0
WAKING_HOURS_PER_DAY = 16.0

# ----------------------------------------------------------------------
# PATIENT MODEL (simulated ground truth - never shown as a real measurement)
# severity s in [0,1]: 0 = symmetric exploration, 1 = severe left neglect
# ----------------------------------------------------------------------
PATIENT = dict(
    initial_severity=0.72,
    recovery_per_hour=0.016,      # when genuine recovery is active
    transient_relief=0.34,        # a good spell: real but temporary
    transient_hours=4.0,          # ~one waking half-day
    deterioration_step=0.38,      # new clinical decline
    diurnal_amplitude=0.06,       # mild fatigue cycle
    floor=0.05,
    ceiling=0.98,
)

# ----------------------------------------------------------------------
# SENSING
# Passive channel : exploration asymmetry from relative head yaw
# Active channel  : sparse orienting probes with known ground truth
# ----------------------------------------------------------------------
SENSING = dict(
    passive_noise_sd=0.10,        # [ENGINEERING TARGET]
    probe_noise_sd=0.055,         # probes are ground-truthed, so cleaner
    probe_probability=0.14,       # chance a window contains a probe trial
    probe_weight=0.60,            # weight of probe vs passive in the estimate
    invalid_bias=0.34,            # confound injected by an invalid context
    invalid_noise_sd=0.24,
    probe_memory=6,               # probes remembered for confidence scoring
    probe_expiry_hours=4.0,       # a probe older than this no longer counts
)

# ----------------------------------------------------------------------
# CONFIDENCE
# The same confidence state gates BOTH the cue and the learning.
# ----------------------------------------------------------------------
CONFIDENCE = dict(
    context_floor=0.05,           # confidence when context is invalid
    agreement_scale=0.40,         # passive/probe disagreement that kills trust
    ewma_tau_hours=1.5,
    cue_reject_below=0.35,        # below this we do not cue at all
    learn_reject_below=0.20,      # below this we do not learn at all
)

# ----------------------------------------------------------------------
# MEMRISTIVE MULTI-TIMESCALE PLASTICITY (behavioural model)
#   G_total = G_slow + g_fast
# ----------------------------------------------------------------------
FAST = dict(
    eta=0.55,                     # fast learning rate, scaled by confidence
    tau_hours=6.0,                # volatile relaxation toward the slow state
)
SLOW = dict(
    eta=0.60,                     # fraction of fast state promoted per event
)

# ----------------------------------------------------------------------
# CONSOLIDATION GATE
# Promotion requires confidence AND a stable direction AND persistence.
# persist_hours is deliberately longer than one waking half-day, so a single
# good afternoon cannot become a permanent therapy reduction.
# [ENGINEERING TARGET] [OPEN QUESTION] - needs clinical data to set properly
# ----------------------------------------------------------------------
GATE = dict(
    confidence_min=0.55,
    magnitude_min=0.055,          # nothing meaningful to consolidate below this
    agreement_min=0.80,
    persist_hours=7.0,
    decay_multiplier=2.0,         # how fast the persistence timer unwinds
    agreement_tau_hours=2.5,
)

# ----------------------------------------------------------------------
# BOUNDED ROLLBACK
# After a consolidation we keep watching. If high-confidence evidence
# contradicts what we just committed, we revert to the last checkpoint.
# ----------------------------------------------------------------------
ROLLBACK = dict(
    watch_hours=14.0,
    contradiction_min=0.20,
    sustain_hours=2.5,
    max_checkpoints=8,
)

# ----------------------------------------------------------------------
# THERAPY DOSE
# dose in [0,1] -> cue intensity and cue rate
# ----------------------------------------------------------------------
DOSE = dict(
    minimum=0.10,
    maximum=1.00,
    max_cues_per_hour=12.0,
)

# ----------------------------------------------------------------------
# COMPARISON CONTROLLERS
# ----------------------------------------------------------------------
NAIVE = dict(tau_hours=1.2)       # rolling-average fading, no gating

# ----------------------------------------------------------------------
# DISPLAY
# ----------------------------------------------------------------------
PLOT_POINTS = 420
GUI_REFRESH_MS = 50
