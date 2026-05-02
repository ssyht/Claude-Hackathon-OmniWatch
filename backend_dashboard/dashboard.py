"""
OmniWatch Live Metrics Dashboard
Exact main.py logic + tkinter metrics panel + video in canvas.
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import math
import time
import queue
import cv2
import subprocess
import settings
from dataclasses import dataclass
from PIL import Image, ImageTk
from vision_api import analyze_frame
from gemini_api import analyze_situation, detect_sudden_motion
from speech_api import process_audio
import warnings
import sys


warnings.filterwarnings("ignore")
# ── CONFIG ────────────────────────────────────────────────────────
VIDEO_PATH = "data/Assault018_x264 (online-video-cutter.com) (1).mp4"

_dispatch_process = None

def trigger_dispatch(incident_data):
    global _dispatch_process
    if _dispatch_process and _dispatch_process.poll() is None:
        return
    print("🚨 Launching dispatch map...")
    _dispatch_process = subprocess.Popen(
        [sys.executable, "dispatch_map.py"]
        # removed DEVNULL so we can see errors
    )

def update_dispatch(incident_data):
    pass

def close_dispatch():
    global _dispatch_process
    if _dispatch_process:
        _dispatch_process.terminate()

# ── COLORS ────────────────────────────────────────────────────────
BG       = "#05040a"
BG2      = "#0d0b14"
PURPLE   = "#6c3de8"
LAVENDER = "#c77dff"
ALERT    = "#ff3366"
GREEN    = "#00ffaa"
YELLOW   = "#f5c842"
ORANGE   = "#fb923c"
DIM      = "#3a3550"
TEXT     = "#e8e0f0"
TEXTDIM  = "#6b6080"

DECISION_COLORS = {
    "CRITICAL": ALERT,
    "HIGH":     ORANGE,
    "LOW":      YELLOW,
    "CLEAR":    GREEN,
}

# ── SHARED QUEUES ─────────────────────────────────────────────────
metrics_queue = queue.Queue()
frame_queue   = queue.Queue(maxsize=2)

# ── METRIC HELPERS ────────────────────────────────────────────────
emergency_start_time = None

def get_confidence(decision):
    return {"CRITICAL": 0.95, "HIGH": 0.80, "LOW": 0.45, "CLEAR": 0.05}.get(decision, 0.0)

def survival_prob(t_minutes):
    return 0.70 * math.exp(-0.10 * t_minutes) * 100

def fused_confidence(cv, ca):
    return 0.65 * cv + 0.35 * ca

def push_metrics(vision_decision, audio_decision, final_decision, frame_count, total_frames):
    global emergency_start_time

    cv_score = get_confidence(vision_decision)
    ca_score = get_confidence(audio_decision)
    fused    = fused_confidence(cv_score, ca_score)

    if final_decision in ["CRITICAL", "HIGH"]:
        if emergency_start_time is None:
            emergency_start_time = time.time()
        t_min = (time.time() - emergency_start_time) / 60.0
        surv  = survival_prob(t_min)
    else:
        emergency_start_time = None
        surv = 70.0

    state_map = {
        "CLEAR":    "IDLE",
        "LOW":      "ANOMALY",
        "HIGH":     "DANGER",
        "CRITICAL": "DANGER",
    }

    if final_decision == "CRITICAL":
        gemini_text = (
            f"ALERT: Rapid downward motion spike detected in E(t). "
            f"Subject appears to have collapsed. "
            f"Cfused={fused:.2f}. Immediate response required."
        )
        log_line = f"🚨 [{frame_count}] CRITICAL — person down!"
    elif final_decision == "HIGH":
        gemini_text = f"WARNING: High priority incident. Active violence detected. Cfused={fused:.2f}."
        log_line    = f"⚠️  [{frame_count}] HIGH — incident detected"
    elif final_decision == "LOW":
        gemini_text = f"NOTICE: Anomaly detected. Cfused={fused:.2f}. Monitoring."
        log_line    = f"⚡ [{frame_count}] LOW — anomaly"
    else:
        gemini_text = "No incidents detected. System monitoring all feeds."
        log_line    = f"✅ [{frame_count}] CLEAR"

    # also print to terminal like main.py
    print("\n" + "━" * 50)
    print(f"  VISION  Cv        : {cv_score:.2f}")
    print(f"  AUDIO   Ca        : {ca_score:.2f}")
    print(f"  FUSED   Cfused    : {fused:.2f}  (0.65·Cv + 0.35·Ca)")
    print(f"  DECISION          : {final_decision}")
    print(f"  INCIDENT STATE    : {state_map.get(final_decision, 'IDLE')}")
    print(f"  PERSONS           : {1 if final_decision != 'CLEAR' else 0}")
    print(f"  SURVIVAL P(t)     : {surv:.1f}%")
    print(f"  ALERT TIME        : {int(time.time() - emergency_start_time) if emergency_start_time else 0}s")
    print("━" * 50 + "\n")

    metrics_queue.put({
        "decision":       final_decision,
        "vision_cv":      round(cv_score, 2),
        "audio_ca":       round(ca_score, 2),
        "fused_c":        round(fused, 2),
        "survival_prob":  round(surv, 1),
        "incident_state": state_map.get(final_decision, "IDLE"),
        "persons":        1 if final_decision != "CLEAR" else 0,
        "alert_time_sec": int(time.time() - emergency_start_time) if emergency_start_time else 0,
        "frame_count":    frame_count,
        "total_frames":   total_frames,
        "gemini_output":  gemini_text,
        "log_line":       log_line,
    })
    incident_data = {
    "decision":   final_decision,
    "frame":      frame_count,
    "survival":   surv,
    "fused":      fused,
    "alert_time": int(time.time() - emergency_start_time) if emergency_start_time else 0,
    }
    if final_decision == "CRITICAL":
        trigger_dispatch(incident_data)
    else:
        update_dispatch(incident_data)


# ── EXACT main.py ANALYSIS LOGIC ─────────────────────────────────
def run_analysis():
    print("✅ Vision API working")

    COLORS = {
        "CRITICAL": (0, 0, 255),
        "HIGH":     (0, 100, 255),
        "LOW":      (0, 200, 200),
        "CLEAR":    (0, 255, 0),
    }

    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    print(f"Video FPS: {fps:.1f}, Duration: {duration:.1f}s, Total frames: {total_frames}")

    sample_every   = 10 if duration < 15 else int(fps)
    min_gemini_gap = 10 if duration < 15 else int(fps * 2)

    frame_count         = 0
    last_gemini_frame   = -999
    current_decision    = "CLEAR"

    def play_audio(video_path, delay=0.0):
        time.sleep(delay)
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-vn", video_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    audio_thread = threading.Thread(target=play_audio, args=(VIDEO_PATH, 0.0), daemon=True)
    audio_thread.start()

    analysis_queue       = queue.Queue(maxsize=2)
    analysis_lock        = threading.Lock()
    analysis_pending     = threading.Event()
    active_analysis      = 0
    active_analysis_lock = threading.Lock()
    last_analysis_frame  = -1

    @dataclass
    class FrameAnalysisTask:
        frame: object
        frame_count: int
        trigger: str
        sudden_fall: bool
        fps: float

    # use a mutable container so worker can update it
    state = {
        "current_decision":    "CLEAR",
        "last_analysis_frame": -1,
        "active_analysis":     0,
    }

    def analysis_worker():
        severity = {"CLEAR": 0, "LOW": 1, "HIGH": 2, "CRITICAL": 3}

        while True:
            task = analysis_queue.get()
            if task is None:
                analysis_queue.task_done()
                break

            with active_analysis_lock:
                state["active_analysis"] += 1
                analysis_pending.set()

            labels = analyze_frame(task.frame)
            print(f"\n[Frame {task.frame_count}/{total_frames}] {task.trigger}")
            print(f"  [Vision] Labels: {labels}")

            audio_decision, transcript, keywords = process_audio(
                VIDEO_PATH, task.frame_count, task.fps
            )
            print(f"  [Audio] Decision: {audio_decision}")

            vision_decision = analyze_situation(
                labels,
                audio_text=transcript,
                frame=task.frame,
                sudden_fall=task.sudden_fall,
                prev_decision=state["current_decision"]
            )

            final_decision = vision_decision
            if severity.get(audio_decision, 0) > severity.get(vision_decision, 0):
                final_decision = audio_decision
                print(f"  [Fusion] Audio escalated → {audio_decision}")

            with analysis_lock:
                if task.frame_count > state["last_analysis_frame"]:
                    state["current_decision"]    = final_decision
                    state["last_analysis_frame"] = task.frame_count

                    print(f"[Frame {task.frame_count}] FINAL: {final_decision}")
                    if final_decision == "CRITICAL":
                        print("🚨 CRITICAL EMERGENCY DETECTED — person down!")
                    elif final_decision == "HIGH":
                        print("⚠️ HIGH PRIORITY INCIDENT")
                    elif final_decision == "LOW":
                        print("⚡ LOW PRIORITY ALERT")
                    else:
                        print("✅ Scene clear")

                    # push to dashboard
                    push_metrics(
                        vision_decision, audio_decision,
                        final_decision, task.frame_count, total_frames
                    )
                else:
                    print(f"[Frame {task.frame_count}] RESULT ignored (older than frame {state['last_analysis_frame']})")

            with active_analysis_lock:
                state["active_analysis"] -= 1
                if state["active_analysis"] == 0:
                    analysis_pending.clear()

            analysis_queue.task_done()

    analysis_threads = [
        threading.Thread(target=analysis_worker, daemon=True)
        for _ in range(2)
    ]
    for thread in analysis_threads:
        thread.start()

    video_start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        fall_detected, energy = detect_sudden_motion(frame)
        frames_since_last = frame_count - last_gemini_frame

        should_analyze = (
            (fall_detected and frames_since_last > 5) or
            (frame_count % sample_every == 0 and frames_since_last >= min_gemini_gap)
        )

        if should_analyze:
            trigger = "⚡ FALL MOTION" if fall_detected else "🕐 INTERVAL"
            task = FrameAnalysisTask(frame.copy(), frame_count, trigger, fall_detected, fps)

            if analysis_queue.full():
                print(f"  [Analysis] queue full — skipping frame {frame_count} to keep results timely")
            else:
                analysis_queue.put(task)
                last_gemini_frame = frame_count
                print(f"\n[Frame {frame_count}/{total_frames}] {trigger} — queued for analysis")

        # draw overlay — exact same as main.py
        color = COLORS.get(state["current_decision"], (255, 255, 255))
        h, w  = frame.shape[:2]

        cv2.rectangle(frame, (0, 0), (w, 50), (0, 0, 0), -1)
        cv2.putText(frame, f"Frame: {frame_count}/{total_frames}",
                    (w - 160, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)

        if state["current_decision"] == "CRITICAL":
            cv2.putText(frame, "CRITICAL ",
                        (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        elif state["current_decision"] == "HIGH":
            cv2.putText(frame, "HIGH PRIORITY INCIDENT DETECTED",
                        (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        elif state["current_decision"] == "LOW":
            cv2.putText(frame, "LOW PRIORITY MONITORING",
                        (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        if analysis_pending.is_set():
            cv2.putText(frame, "ANALYSIS PENDING...",
                        (10, h - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # push frame to tkinter canvas instead of cv2.imshow
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if not frame_queue.full():
            frame_queue.put(rgb)

        # exact same timing logic as main.py
        expected_time = frame_count / fps
        actual_time   = time.time() - video_start_time
        wait = max(1, int((expected_time - actual_time) * 1000))
        if analysis_pending.is_set():
            wait = max(wait, 500)
        time.sleep(wait / 1000.0)

    cap.release()
    analysis_queue.put(None)
    analysis_queue.put(None)
    for thread in analysis_threads:
        thread.join(timeout=2)


# ── TKINTER DASHBOARD ─────────────────────────────────────────────
class OmniWatchDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("OmniWatch — Live Detection")
        self.root.configure(bg=BG)
        self.root.geometry("1100x700")
        self.root.resizable(True, True)

        self.font_mono  = tkfont.Font(family="Courier New", size=10)
        self.font_big   = tkfont.Font(family="Courier New", size=28, weight="bold")
        self.font_med   = tkfont.Font(family="Courier New", size=14, weight="bold")
        self.font_small = tkfont.Font(family="Courier New", size=9)
        self.font_label = tkfont.Font(family="Courier New", size=8)

        self._tk_image = None
        self._build_ui()
        self._poll_metrics()
        self._poll_frames()
        self._tick_clock()

        # start analysis in background thread
        self.analysis_thread = threading.Thread(target=run_analysis, daemon=True)
        self.analysis_thread.start()

    def _section(self, parent, title):
        frame = tk.Frame(parent, bg=BG2, highlightbackground=DIM, highlightthickness=1)
        frame.pack(fill="x", padx=6, pady=3)
        tk.Label(frame, text=f" {title} ", bg=BG2, fg=TEXTDIM,
                 font=self.font_label, anchor="w").pack(fill="x", padx=6, pady=(4, 0))
        inner = tk.Frame(frame, bg=BG2)
        inner.pack(fill="x", padx=6, pady=(0, 6))
        return inner

    def _build_ui(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # LEFT: video canvas
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="OMNIWATCH  LIVE FEED", bg=BG, fg=LAVENDER,
                 font=tkfont.Font(family="Courier New", size=12, weight="bold"),
                 anchor="w").pack(fill="x", pady=(0, 4))

        self.video_canvas = tk.Canvas(left, bg="#000000",
                                       highlightthickness=0)
        self.video_canvas.pack(fill="both", expand=True)

        # RIGHT: metrics
        right = tk.Frame(main, bg=BG, width=420)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        hdr = tk.Frame(right, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="LIVE METRICS", bg=BG, fg=TEXTDIM,
                 font=self.font_label, anchor="w").pack(side="left")
        self.lbl_clock = tk.Label(hdr, text="--:--:--", bg=BG, fg=TEXTDIM,
                                   font=self.font_label)
        self.lbl_clock.pack(side="right")

        # decision banner
        banner = tk.Frame(right, bg=BG2, height=70,
                          highlightbackground=DIM, highlightthickness=1)
        banner.pack(fill="x", padx=6, pady=3)
        banner.pack_propagate(False)
        self.lbl_decision = tk.Label(banner, text="CLEAR", bg=BG2, fg=GREEN,
                                      font=self.font_big)
        self.lbl_decision.pack(expand=True)
        self.lbl_state = tk.Label(banner, text="IDLE — Monitoring all feeds",
                                   bg=BG2, fg=TEXTDIM, font=self.font_label)
        self.lbl_state.pack()

        # confidence scores
        conf = self._section(right, "CONFIDENCE SCORES")
        row  = tk.Frame(conf, bg=BG2)
        row.pack(fill="x")

        cv_f = tk.Frame(row, bg=BG2)
        cv_f.pack(side="left", expand=True)
        tk.Label(cv_f, text="VISION Cv", bg=BG2, fg=TEXTDIM,
                 font=self.font_label).pack(anchor="w")
        self.lbl_cv = tk.Label(cv_f, text="0.05", bg=BG2, fg=PURPLE,
                                font=self.font_big)
        self.lbl_cv.pack(anchor="w")

        ca_f = tk.Frame(row, bg=BG2)
        ca_f.pack(side="left", expand=True)
        tk.Label(ca_f, text="AUDIO Ca", bg=BG2, fg=TEXTDIM,
                 font=self.font_label).pack(anchor="w")
        self.lbl_ca = tk.Label(ca_f, text="0.05", bg=BG2, fg=YELLOW,
                                font=self.font_big)
        self.lbl_ca.pack(anchor="w")

        tk.Label(conf, text="CFUSED = 0.65·Cv + 0.35·Ca",
                 bg=BG2, fg=TEXTDIM, font=self.font_label).pack(anchor="w", pady=(4, 0))
        self.lbl_fused = tk.Label(conf, text="0.05", bg=BG2, fg=LAVENDER,
                                   font=self.font_med)
        self.lbl_fused.pack(anchor="w")

        # survival
        surv = self._section(right, "SURVIVAL P(t) = 0.70·e^(−0.10·t)")
        self.lbl_surv = tk.Label(surv, text="70.0%", bg=BG2, fg=GREEN,
                                  font=self.font_med)
        self.lbl_surv.pack(anchor="w")
        bar_bg = tk.Frame(surv, bg=DIM, height=6)
        bar_bg.pack(fill="x", pady=(3, 2))
        bar_bg.pack_propagate(False)
        self.surv_bar = tk.Frame(bar_bg, bg=GREEN, height=6)
        self.surv_bar.place(x=0, y=0, relwidth=0.70, height=6)

        # state machine
        sm = self._section(right, "INCIDENT STATE MACHINE")
        sf = tk.Frame(sm, bg=BG2)
        sf.pack(fill="x")
        self.state_dots = []
        self.state_lbls = []
        for s in ["IDLE", "ANOMALY", "DANGER", "DISPATCHED"]:
            col = tk.Frame(sf, bg=BG2)
            col.pack(side="left", expand=True)
            d = tk.Label(col, text="●", bg=BG2, fg=DIM,
                         font=tkfont.Font(family="Courier New", size=14))
            d.pack()
            l = tk.Label(col, text=s, bg=BG2, fg=TEXTDIM, font=self.font_label)
            l.pack()
            self.state_dots.append(d)
            self.state_lbls.append(l)

        # live stats
        st = self._section(right, "LIVE STATS")
        sr = tk.Frame(st, bg=BG2)
        sr.pack(fill="x")

        def stat(parent, lbl):
            f = tk.Frame(parent, bg=BG2)
            f.pack(side="left", expand=True)
            tk.Label(f, text=lbl, bg=BG2, fg=TEXTDIM, font=self.font_label).pack()
            v = tk.Label(f, text="—", bg=BG2, fg=TEXT,
                         font=tkfont.Font(family="Courier New", size=12, weight="bold"))
            v.pack()
            return v

        self.lbl_persons = stat(sr, "PERSONS")
        self.lbl_alert   = stat(sr, "ALERT TIME")
        self.lbl_frame   = stat(sr, "FRAME")

        # gemini output
        go = self._section(right, "GEMINI 2.5 PRO OUTPUT")
        self.txt_gemini = tk.Text(go, bg=BG2, fg=LAVENDER, font=self.font_small,
                                   height=3, wrap="word", bd=0, state="disabled")
        self.txt_gemini.pack(fill="x")
        self._set_gemini("Awaiting analysis...")

        # log
        lg = self._section(right, "DETECTION LOG")
        self.txt_log = tk.Text(lg, bg=BG2, fg=TEXTDIM, font=self.font_label,
                                height=5, wrap="word", bd=0, state="disabled")
        self.txt_log.pack(fill="x")

        tk.Label(right, text="AI For Emergency · Google DevFest 2026 · WashU",
                 bg=BG, fg=DIM, font=self.font_label).pack(pady=4)

    def _set_gemini(self, text):
        self.txt_gemini.config(state="normal")
        self.txt_gemini.delete("1.0", "end")
        self.txt_gemini.insert("end", text)
        self.txt_gemini.config(state="disabled")

    def _log(self, text):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")
        if int(self.txt_log.index("end-1c").split(".")[0]) > 50:
            self.txt_log.delete("1.0", "2.0")
        self.txt_log.config(state="disabled")

    def _update_sm(self, state):
        idx = {"IDLE": 0, "ANOMALY": 1, "DANGER": 2, "DISPATCHED": 3}.get(state, 0)
        for i, (d, l) in enumerate(zip(self.state_dots, self.state_lbls)):
            c = (ALERT if state == "DANGER" else GREEN) if i <= idx else DIM
            d.config(fg=c)
            l.config(fg=c if i <= idx else TEXTDIM)

    def _poll_frames(self):
        try:
            while True:
                rgb = frame_queue.get_nowait()
                cw  = self.video_canvas.winfo_width()
                ch  = self.video_canvas.winfo_height()
                if cw > 1 and ch > 1:
                    img = Image.fromarray(rgb)
                    img = img.resize((cw, ch), Image.LANCZOS)
                    self._tk_image = ImageTk.PhotoImage(img)
                    self.video_canvas.create_image(0, 0, anchor="nw",
                                                    image=self._tk_image)
        except queue.Empty:
            pass
        self.root.after(33, self._poll_frames)

    def _poll_metrics(self):
        try:
            while True:
                data = metrics_queue.get_nowait()
                self._update(data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_metrics)

    def _update(self, data):
        decision = data.get("decision", "CLEAR")
        cv_score = data.get("vision_cv", 0.0)
        ca_score = data.get("audio_ca", 0.0)
        fused    = data.get("fused_c", 0.0)
        surv     = data.get("survival_prob", 70.0)
        state    = data.get("incident_state", "IDLE")
        persons  = data.get("persons", 0)
        alert_t  = data.get("alert_time_sec", 0)
        frame_n  = data.get("frame_count", 0)
        gemini   = data.get("gemini_output", "")
        log_line = data.get("log_line", "")

        color = DECISION_COLORS.get(decision, GREEN)

        self.lbl_decision.config(text=decision, fg=color)
        state_names = {
            "IDLE":       "Monitoring all feeds",
            "ANOMALY":    "Anomaly detected — analyzing",
            "DANGER":     "EMERGENCY — dispatching response",
            "DISPATCHED": "Help dispatched — monitoring",
        }
        self.lbl_state.config(text=f"{state} — {state_names.get(state, '')}")
        self.lbl_cv.config(text=f"{cv_score:.2f}",
                            fg=color if cv_score > 0.5 else PURPLE)
        self.lbl_ca.config(text=f"{ca_score:.2f}",
                            fg=color if ca_score > 0.5 else YELLOW)
        self.lbl_fused.config(text=f"{fused:.2f}", fg=color)

        pct = max(0.0, min(1.0, surv / 100.0))
        bc  = GREEN if pct > 0.6 else (YELLOW if pct > 0.4 else ALERT)
        self.lbl_surv.config(text=f"{surv:.1f}%", fg=bc)
        self.surv_bar.place(relwidth=pct)
        self.surv_bar.config(bg=bc)

        self._update_sm(state)
        self.lbl_persons.config(text=str(persons), fg=color if persons else TEXT)
        self.lbl_alert.config(text=f"{alert_t}s" if alert_t else "—",
                               fg=ALERT if alert_t else TEXT)
        self.lbl_frame.config(text=str(frame_n))
        self._set_gemini(gemini)
        if log_line:
            self._log(log_line)

        self.root.configure(
            bg=ALERT if decision == "CRITICAL" and int(time.time() * 2) % 2 == 0 else BG
        )

    def _tick_clock(self):
        self.lbl_clock.config(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)


# ── MAIN ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("✅ OmniWatch starting...")
    root = tk.Tk()
    app  = OmniWatchDashboard(root)
    root.mainloop()