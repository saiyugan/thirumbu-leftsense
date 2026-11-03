"""
THIRUMBU interactive dashboard (tkinter only - no third-party packages).

Layout
  TOP     control buttons
  LEFT    patient / sensing panel
  CENTRE  three-controller comparison
  RIGHT   THIRUMBU internal state
  BOTTOM  four large live plots in a 2x2 grid (~35% of the window)
  STATUS  permanent SIMULATED RESULTS banner
"""

import tkinter as tk

from config import (CONFIDENCE, GATE, PLOT_POINTS, GUI_REFRESH_MS,
                    WAKING_HOURS_PER_DAY)

BG = "#0f1219"
PANEL = "#181d28"
CARD = "#1f2634"
FG = "#e9edf5"
MUTED = "#8a95ab"
ACCENT = "#5aa9ff"
GOOD = "#37c98a"
WARN = "#e8b53a"
BAD = "#e5564b"
VIOLET = "#b083f0"
GRID = "#2a3242"


class Plot(tk.Canvas):
    """Small multi-series line plot on a canvas."""

    def __init__(self, master, title, series, ymin=0.0, ymax=1.0, height=210,
                 ylabel="", show_legend=True):
        super().__init__(master, height=height, bg="#0a0d13",
                         highlightthickness=1, highlightbackground=GRID)
        self.title = title
        self.series = series            # list of (label, colour)
        self.ymin, self.ymax = ymin, ymax
        self.ylabel = ylabel
        self.show_legend = show_legend
        self.data = {label: [] for label, _ in series}
        self.markers = []

    def push(self, values, marker=None):
        for label, _ in self.series:
            v = values.get(label)
            self.data[label].append(v)
            if len(self.data[label]) > PLOT_POINTS:
                del self.data[label][:-PLOT_POINTS]
        self.markers.append(marker)
        if len(self.markers) > PLOT_POINTS:
            del self.markers[:-PLOT_POINTS]

    def clear(self):
        for k in self.data:
            self.data[k] = []
        self.markers = []

    def draw(self):
        self.delete("all")
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        top = 26          # room for the title bar
        bot = 20          # room for the x-axis caption
        left = 44         # room for the y-axis scale labels

        def y(v):
            frac = (v - self.ymin) / (self.ymax - self.ymin + 1e-9)
            frac = max(0.0, min(1.0, frac))
            return (h - bot) - (h - top - bot) * frac

        def x(i, n):
            return left + (w - left - 8) * i / max(n - 1, 1)

        # ---- plot frame + gridlines at 0, mid, max ----
        self.create_rectangle(left, top, w - 8, h - bot,
                              outline=GRID, width=1)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            val = self.ymin + frac * (self.ymax - self.ymin)
            yy = y(val)
            if frac in (0.0, 1.0):          # Tk rejects a zero-length dash
                self.create_line(left, yy, w - 8, yy, fill=GRID)
            else:
                self.create_line(left, yy, w - 8, yy, fill=GRID, dash=(2, 5))
            if frac in (0.0, 0.5, 1.0):
                self.create_text(left - 6, yy, text=f"{val:+.2f}"
                                 if self.ymin < 0 else f"{val:.2f}",
                                 fill=MUTED, anchor="e",
                                 font=("Segoe UI", 8))
        # emphasise the zero line when the axis spans negative values
        if self.ymin < 0 < self.ymax:
            self.create_line(left, y(0.0), w - 8, y(0.0), fill="#4a5568", width=1)

        n = max(len(self.markers), 1)

        # ---- event markers (CONSOLIDATED / ROLLBACK / POWER CYCLE) ----
        for i, m in enumerate(self.markers):
            if m:
                col = {"CONSOLIDATED": GOOD, "ROLLBACK": BAD,
                       "POWER CYCLE": VIOLET}.get(m, MUTED)
                xx = x(i, n)
                self.create_line(xx, top, xx, h - bot, fill=col, width=2)

        # ---- trajectories ----
        for label, colour in self.series:
            pts = []
            for i, v in enumerate(self.data[label]):
                if v is None:
                    continue
                pts += [x(i, n), y(v)]
            if len(pts) >= 4:
                self.create_line(*pts, fill=colour, width=3, smooth=False)
                self.create_oval(pts[-2] - 3, pts[-1] - 3,
                                 pts[-2] + 3, pts[-1] + 3,
                                 fill=colour, outline="")

        # ---- title, axis caption, legend ----
        self.create_text(8, 12, text=self.title, fill=FG, anchor="w",
                         font=("Segoe UI", 10, "bold"))
        cap = self.ylabel + ("   |   " if self.ylabel else "") + "time \u2192"
        self.create_text(left, h - 6, text=cap, fill=MUTED, anchor="w",
                         font=("Segoe UI", 8))
        if self.show_legend:
            lx = w - 10
            for label, colour in reversed(self.series):
                self.create_text(lx, 12, text=label, fill=colour, anchor="e",
                                 font=("Segoe UI", 9, "bold"))
                lx -= (len(label) * 8 + 20)


class ThirumbuGUI:
    def __init__(self, root, sim):
        self.root = root
        self.sim = sim
        root.title("THIRUMBU  -  Consolidation-Gated Closed-Loop Therapy "
                   "Dosing for Post-Stroke Hemispatial Neglect")
        root.configure(bg=BG)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = min(1360, sw - 40)
        h = min(1010, sh - 70)          # never taller than the screen
        root.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+10")
        root.minsize(1100, 620)
        self.running = False
        self.body_visible = True
        self._build()
        # the top/bottom split is PROPORTIONAL, so a 768px laptop still gets
        # usable plots instead of 30px slivers
        self.root.bind("<Configure>", self._layout)
        self.root.after(80, self._layout)
        self.root.after(GUI_REFRESH_MS, self._tick)

    # ------------------------------------------------------------------
    def _layout(self, event=None):
        """Give the upper panels a share of the window, never a fixed slab."""
        if not self.body_visible:
            return
        avail = self.root.winfo_height() - 150      # buttons + banner + pads
        if avail < 200:
            return
        self.body.configure(height=max(312, min(470, int(avail * 0.57))))

    def toggle_panels(self):
        """Collapse the whole upper half - plots then fill the window.
        This is the button to hit if the projector is low-resolution."""
        if self.body_visible:
            self.body.pack_forget()
            self.body_visible = False
            self.b_toggle.configure(text="SHOW PANELS")
        else:
            self.body.pack(fill="x", expand=False, padx=8, after=self.bar2)
            self.body_visible = True
            self.b_toggle.configure(text="BIG PLOTS")
            self._layout()

    # ------------------------------------------------------------------
    def _button(self, parent, text, cmd, bg=CARD, fg=FG, width=19):
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                      activebackground=ACCENT, activeforeground="#06101f",
                      font=("Segoe UI", 9, "bold"), width=width, relief="flat",
                      bd=0, pady=7, cursor="hand2")
        b.pack(side="left", padx=3)
        return b

    def _build(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 2))
        self._button(bar, "START CALIBRATION", self.sim.calibrate, width=17)
        self._button(bar, "START MONITORING", self.start, width=17)
        self._button(bar, "TRANSIENT GOOD SPELL", self.sim.transient,
                     bg="#2a3a52", width=20)
        self._button(bar, "PERSISTENT RECOVERY", self.sim.persistent,
                     bg="#1f4436", width=20)

        bar2 = tk.Frame(self.root, bg=BG)
        bar2.pack(fill="x", padx=8, pady=(0, 4))
        self.bar2 = bar2
        self._button(bar2, "INVALID CONTEXT", self.sim.toggle_context,
                     bg="#4a3a1c", width=17)
        self._button(bar2, "DETERIORATION", self.sim.deterioration,
                     bg="#4a2530", width=17)
        self._button(bar2, "POWER CYCLE", self.sim.power_cycle,
                     bg="#372a4c", width=14)
        self._button(bar2, "RESET", self.sim.reset, width=11)
        self.b_toggle = self._button(bar2, "BIG PLOTS", self.toggle_panels,
                                     bg="#20404f", width=13)

        # Height is set proportionally in _layout() so the plots always get a
        # real share of whatever screen this runs on.
        body = tk.Frame(self.root, bg=BG, height=380)
        body.pack(fill="x", expand=False, padx=8)
        body.pack_propagate(False)
        self.body = body

        # ---------------- LEFT : patient / sensing ----------------
        left = tk.LabelFrame(body, text=" PATIENT / SENSING  (simulated) ",
                             bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"),
                             bd=1, relief="solid", width=300)
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)
        self.left_lbl = tk.Label(left, text="", bg=PANEL, fg=FG, justify="left",
                                 anchor="nw", font=("Consolas", 8))
        self.left_lbl.pack(fill="x", padx=8, pady=(4, 2))

        self.eai_canvas = tk.Canvas(left, height=74, bg="#0a0d13",
                                    highlightthickness=1, highlightbackground=GRID)
        self.eai_canvas.pack(fill="x", padx=8, pady=2)
        self.ctx_lbl = tk.Label(left, text="", bg=PANEL, fg=GOOD,
                                font=("Segoe UI", 9, "bold"))
        self.ctx_lbl.pack(pady=2)

        mf = tk.LabelFrame(left, text=" SIMULATED METRICS ", bg=PANEL,
                           fg=MUTED, font=("Segoe UI", 7, "bold"), bd=1,
                           relief="solid")
        mf.pack(fill="both", expand=True, padx=6, pady=(2, 4))
        self.metrics_lbl = tk.Label(mf, text="", bg=PANEL, fg=FG,
                                    justify="left", anchor="nw",
                                    font=("Consolas", 7), wraplength=280)
        self.metrics_lbl.pack(fill="both", expand=True, padx=5, pady=2)

        # ---------------- CENTRE : three controllers ----------------
        centre = tk.Frame(body, bg=BG)
        centre.pack(side="left", fill="both", expand=True)
        tk.Label(centre, text="THREE-CONTROLLER EXPERIMENT  -  identical "
                              "observation stream", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(2, 3))
        self.cards = []
        for i in range(3):
            f = tk.Frame(centre, bg=CARD, bd=1, relief="solid")
            f.pack(fill="x", pady=2)
            title = tk.Label(f, text="", bg=CARD, fg=FG,
                             font=("Segoe UI", 9, "bold"), anchor="w")
            title.pack(fill="x", padx=8, pady=(3, 0))
            body_lbl = tk.Label(f, text="", bg=CARD, fg=FG, justify="left",
                                anchor="w", font=("Consolas", 8))
            body_lbl.pack(fill="x", padx=8, pady=(1, 2))
            bar_c = tk.Canvas(f, height=12, bg="#0a0d13", highlightthickness=0)
            bar_c.pack(fill="x", padx=8, pady=(0, 4))
            self.cards.append((title, body_lbl, bar_c))

        # ---------------- RIGHT : internal state ----------------
        right = tk.LabelFrame(body, text=" THIRUMBU INTERNAL STATE ", bg=PANEL,
                              fg=MUTED, font=("Segoe UI", 8, "bold"), bd=1,
                              relief="solid", width=330)
        right.pack(side="left", fill="y", padx=(6, 0))
        right.pack_propagate(False)
        self.state_lbl = tk.Label(right, text="", bg=PANEL, fg=FG,
                                  justify="left", anchor="nw",
                                  font=("Consolas", 8))
        self.state_lbl.pack(fill="x", padx=8, pady=(4, 2))

        tk.Label(right, text="CONSOLIDATION", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10)
        self.cons_canvas = tk.Canvas(right, height=22, bg="#0a0d13",
                                     highlightthickness=1,
                                     highlightbackground=GRID)
        self.cons_canvas.pack(fill="x", padx=8, pady=(1, 4))

        tk.Label(right, text="MEMORY", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10)
        self.mem_canvas = tk.Canvas(right, height=50, bg="#0a0d13",
                                    highlightthickness=1,
                                    highlightbackground=GRID)
        self.mem_canvas.pack(fill="x", padx=8, pady=(1, 4))

        self.event_lbl = tk.Label(right, text="", bg=PANEL, fg=GOOD,
                                  font=("Segoe UI", 10, "bold"), wraplength=300)
        self.event_lbl.pack(pady=(0, 2))

        # ---------------- BOTTOM : plots ----------------
        status = tk.Frame(self.root, bg="#3a2c10")
        status.pack(side="bottom", fill="x", padx=8, pady=(0, 6))
        self.status_lbl = tk.Label(
            status,
            text=("SIMULATED RESULTS  -  synthetic patient model, not measured "
                  "patient or device data.   Memristive dynamics are MODELLED; "
                  "physical device implementation is the proposed scaling path."),
            bg="#3a2c10", fg=WARN, font=("Segoe UI", 8, "bold"),
            wraplength=1330, justify="center")
        self.status_lbl.pack(pady=3)

        plots = tk.Frame(self.root, bg=BG)
        plots.pack(side="bottom", fill="both", expand=True, padx=8, pady=(4, 2))
        for c in range(2):
            plots.columnconfigure(c, weight=1, uniform="pcol")
        for r in range(2):
            plots.rowconfigure(r, weight=1, uniform="prow")

        self.plots = {}
        spec = [
            ("confidence", "1.  CONFIDENCE   (gates both the cue and the learning)",
             [("confidence", ACCENT)], 0.0, 1.0, "0 = untrusted   1 = trusted"),
            ("fast", "2.  FAST / VOLATILE MEMORY   g_fast",
             [("g_fast", WARN)], -0.45, 0.45, "moves on ANY evidence, then decays"),
            ("slow", "3.  SLOW / CONSOLIDATED MEMORY   G_slow  vs  truth",
             [("G_slow", GOOD), ("truth", MUTED)], 0.0, 1.0,
             "only moves when the gate opens"),
            ("dose", "4.  THERAPY DOSE + CONSOLIDATION",
             [("FIXED", BAD), ("NAIVE", WARN), ("THIRUMBU", GOOD),
              ("ideal", MUTED), ("consol.", VIOLET)], 0.0, 1.05,
             "green bar = CONSOLIDATED, red = ROLLBACK, violet = POWER CYCLE"),
        ]
        for i, (key, title, series, lo, hi, ylab) in enumerate(spec):
            p = Plot(plots, title, series, lo, hi, ylabel=ylab)
            p.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            self.plots[key] = p


    # ------------------------------------------------------------------
    def start(self):
        self.running = True
        self.sim.start_monitoring()

    # ------------------------------------------------------------------
    def _tick(self):
        try:
            if self.running:
                snap = self.sim.step()
                if snap:
                    self._push(snap)
            self._render()
        except Exception as exc:                      # never die mid-demo
            try:
                self.status_lbl.configure(text=f"non-fatal GUI error: {exc}")
            except Exception:
                pass
        self.root.after(GUI_REFRESH_MS, self._tick)

    def _push(self, s):
        """Unchanged data, four panels instead of six: dose error now lives in
        the metrics table and consolidation shares the dose panel."""
        ev = s["event"]
        self.plots["confidence"].push({"confidence": s["confidence"]}, ev)
        self.plots["fast"].push({"g_fast": s["g_fast"]}, ev)
        self.plots["slow"].push({"G_slow": s["G_slow"],
                                 "truth": s["true_severity"]}, ev)
        self.plots["dose"].push({"FIXED": s["doses"][0],
                                 "NAIVE": s["doses"][1],
                                 "THIRUMBU": s["doses"][2],
                                 "ideal": s["ideal_dose"],
                                 "consol.": s["consolidation"]}, ev)

    def clear_plots(self):
        for p in self.plots.values():
            p.clear()

    # ------------------------------------------------------------------
    def _render(self):
        s = self.sim.snapshot()

        day = int(s["hours"] // WAKING_HOURS_PER_DAY) + 1
        hod = s["hours"] % WAKING_HOURS_PER_DAY
        self.left_lbl.configure(text=(
            f"phase      {s['phase']}   day {day}, {hod:4.1f} h\n"
            f"PASSIVE EAI {s['passive']:.3f}  (head-yaw vs trunk)\n"
            f"ACTIVE probe {s['probe_text']}   held {s['n_probes']}\n"
            f"FUSED     z  {s['z']:.3f}\n"
            f"ground truth {s['true_severity']:.3f}  (simulated)\n"
            f"ideal dose   {s['ideal_dose']:.2f}"))

        ok = s["context_valid"]
        self.ctx_lbl.configure(
            text="CONTEXT VALID" if ok else "CONTEXT INVALID\nmeasurement untrusted",
            fg=GOOD if ok else BAD)
        self._draw_eai(s)

        for i, (title, body, bar) in enumerate(self.cards):
            c = s["controllers"][i]
            col = GOOD if c["name"].startswith("C") else (
                WARN if c["name"].startswith("B") else BAD)
            title.configure(text=c["name"], fg=col)
            body.configure(text=(
                f"estimate {c['estimate']:.3f}   dose {c['dose']:.2f}   "
                f"err {abs(c['dose'] - s['ideal_dose']):.2f}\n"
                f"action   {c['action']:<10} cues {c['cues']:<5} "
                f"bad-context cues {c['bad_cues']}\n"
                f"state    {c['status']}"))
            self._draw_dose_bar(bar, c["dose"], s["ideal_dose"], col)

        st = s["state"]
        self.state_lbl.configure(text=(
            f"confidence     {s['confidence']:.3f}   "
            f"{'CUE OK' if s['confidence'] >= CONFIDENCE['cue_reject_below'] else 'CUE WITHHELD'}\n"
            f"learning       {'ENABLED' if st['learning'] else 'SUPPRESSED'}\n"
            f"G_slow         {st['G_slow']:.3f}   (non-volatile)\n"
            f"g_fast         {st['g_fast']:+.3f}   (volatile)\n"
            f"G_total        {st['total']:.3f}\n"
            f"agreement      {st['agreement']:.2f}  (need >= {GATE['agreement_min']:.2f})\n"
            f"persistence    {st['persist_hours']:.1f} h  "
            f"(need {GATE['persist_hours']:.0f} h)\n"
            f"gate           {'OPEN' if st['gate_open'] else 'CLOSED'}\n"
            f"consolidations {st['consolidations']}\n"
            f"rollbacks      {st['rollbacks']}\n"
            f"checkpoints    {st['checkpoints']}"))

        self._draw_bar(self.cons_canvas, st["consolidation"],
                       VIOLET if st["consolidation"] < 1 else GOOD)
        self._draw_memory(st)

        ev = st["last_event"]
        colour = {"CONSOLIDATED": GOOD, "ROLLBACK": BAD,
                  "POWER CYCLE": VIOLET}.get(ev, MUTED)
        self.event_lbl.configure(text=ev, fg=colour)

        for p in self.plots.values():
            p.draw()

        m = s["metrics"]
        spec, sens = m["specificity"], m["sensitivity"]
        spec_txt = "n/a" if spec is None else "{:.0f}%".format(spec * 100)
        sens_txt = "n/a" if sens is None else "{:.0f}%".format(sens * 100)
        resc = m["reescalation"]
        resc_txt = "n/a" if resc is None else "{:.1f} h".format(resc)
        # headline numbers first - they must survive a short panel
        lines = ["specificity {}  ({} transient)".format(
                     spec_txt, m["transient_episodes"]),
                 "sensitivity {}  ({} persistent)".format(
                     sens_txt, m["persistent_episodes"]),
                 "re-escalation {}".format(resc_txt), ""]
        for row in m["table"]:
            lines.append("{:<11} err {:.3f}  bad-data cues {}".format(
                row["name"].split(" - ")[-1][:11], row["dose_error"],
                row["bad_cues"]))
        self.metrics_lbl.configure(text="\n".join(lines))

    # ------------------------------------------------------------------
    def _draw_eai(self, s):
        c = self.eai_canvas
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        mid = w / 2
        c.create_line(mid, 14, mid, h - 4, fill=MUTED, dash=(3, 3))
        c.create_text(8, 8, text="exploration  LEFT | RIGHT", fill=MUTED,
                      anchor="w", font=("Segoe UI", 7))
        # severity 0 -> symmetric, 1 -> all exploration on the right
        sev = s["true_severity"]
        left_frac = max(0.02, (1.0 - sev) * 0.5)
        right_frac = 1.0 - left_frac
        y0, y1 = 24, 48
        c.create_rectangle(mid - left_frac * (w / 2 - 6), y0, mid, y1,
                           fill="#2b4f74", outline="")
        c.create_rectangle(mid, y0, mid + right_frac * (w / 2 - 6), y1,
                           fill="#4f7a2b", outline="")
        c.create_text(mid, y1 + 14,
                      text=f"EAI (measured) {s['passive']:.2f}",
                      fill=FG, font=("Segoe UI", 8, "bold"))

    def _draw_dose_bar(self, canvas, dose, ideal, colour):
        canvas.delete("all")
        w = max(canvas.winfo_width(), 10)
        h = max(canvas.winfo_height(), 10)
        canvas.create_rectangle(0, 3, w * min(dose, 1.0), h - 3,
                                fill=colour, outline="")
        x = w * min(ideal, 1.0)
        canvas.create_line(x, 0, x, h, fill=FG, width=2)

    def _draw_bar(self, canvas, value, colour):
        canvas.delete("all")
        w = max(canvas.winfo_width(), 10)
        h = max(canvas.winfo_height(), 10)
        canvas.create_rectangle(0, 2, w * max(0.0, min(1.0, value)), h - 2,
                                fill=colour, outline="")
        canvas.create_text(w / 2, h / 2, text=f"{value*100:.0f}%", fill=FG,
                           font=("Segoe UI", 8, "bold"))

    def _draw_memory(self, st):
        c = self.mem_canvas
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        # slow memory bar
        c.create_text(6, 11, text="G_slow", fill=GOOD, anchor="w",
                      font=("Segoe UI", 8))
        c.create_rectangle(60, 5, 60 + (w - 70) * st["G_slow"], 17,
                           fill=GOOD, outline="")
        # fast memory, signed around a centre line
        c.create_text(6, 35, text="g_fast", fill=WARN, anchor="w",
                      font=("Segoe UI", 8))
        base = 60 + (w - 70) / 2
        c.create_line(base, 25, base, 46, fill=MUTED, dash=(2, 3))
        span = (w - 70) / 2
        g = max(-0.5, min(0.5, st["g_fast"])) * 2.0
        if g >= 0:
            c.create_rectangle(base, 28, base + span * g, 43, fill=WARN,
                               outline="")
        else:
            c.create_rectangle(base + span * g, 28, base, 43, fill=WARN,
                               outline="")
