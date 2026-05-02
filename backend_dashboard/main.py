import cv2
import settings
import threading
import subprocess
import time
import queue
import math
from dataclasses import dataclass
from vision_api import analyze_frame
from gemini_api import analyze_situation, detect_sudden_motion
from speech_api import process_audio

print("✅ Vision API working")

VIDEO_PATH = "data/Footage-1.mp4"

# ── METRICS HELPERS ───────────────────────────────────────────────
emergency_start_time = None

def get_confidence(decision):
    return {
        "CRITICAL": 0.95,
        "HIGH":     0.80,
        "LOW":      0.45,
        "CLEAR":    0.05
    }.get(decision, 0.0)

def survival_prob(t_minutes):
    return 0.70 * math.exp(-0.10 * t_minutes) * 100

def fused_confidence(cv, ca):
    return 0.65 * cv + 0.35 * ca

def print_metrics(vision_decision, audio_decision, final_decision):
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
# ─────────────────────────────────────────────────────────────────

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps

print(f"Video FPS: {fps:.1f}, Duration: {duration:.1f}s, Total frames: {total_frames}")

sample_every = 10 if duration < 15 else int(fps)
min_gemini_gap = 10 if duration < 15 else int(fps * 2)

frame_count = 0
last_gemini_frame = -999

COLORS = {
    "CRITICAL": (0, 0, 255),
    "HIGH":     (0, 100, 255),
    "LOW":      (0, 200, 200),
    "CLEAR":    (0, 255, 0),
}
current_decision = "CLEAR"

def play_audio(video_path, delay=0.0):
    time.sleep(delay)
    subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-vn", video_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

audio_thread = threading.Thread(target=play_audio, args=(VIDEO_PATH, 0.0), daemon=True)
audio_thread.start()

analysis_queue = queue.Queue(maxsize=2)
analysis_lock = threading.Lock()
analysis_pending = threading.Event()
active_analysis = 0
active_analysis_lock = threading.Lock()
last_analysis_frame = -1

@dataclass
class FrameAnalysisTask:
    frame: object
    frame_count: int
    trigger: str
    sudden_fall: bool
    fps: float


def analysis_worker():
    global current_decision, last_analysis_frame, active_analysis
    severity = {"CLEAR": 0, "LOW": 1, "HIGH": 2, "CRITICAL": 3}

    while True:
        task = analysis_queue.get()
        if task is None:
            analysis_queue.task_done()
            break

        with active_analysis_lock:
            active_analysis += 1
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
            prev_decision=current_decision
        )

        final_decision = vision_decision
        if severity.get(audio_decision, 0) > severity.get(vision_decision, 0):
            final_decision = audio_decision
            print(f"  [Fusion] Audio escalated → {audio_decision}")

        with analysis_lock:
            if task.frame_count > last_analysis_frame:
                current_decision = final_decision
                last_analysis_frame = task.frame_count
                print(f"[Frame {task.frame_count}] FINAL: {final_decision}")
                if final_decision == "CRITICAL":
                    print("🚨 CRITICAL EMERGENCY DETECTED — person down!")
                elif final_decision == "HIGH":
                    print("⚠️ HIGH PRIORITY INCIDENT")
                elif final_decision == "LOW":
                    print("⚡ LOW PRIORITY ALERT")
                else:
                    print("✅ Scene clear")

                # ── PRINT METRICS ─────────────────────────────────
                print_metrics(vision_decision, audio_decision, final_decision)
                # ─────────────────────────────────────────────────

            else:
                print(f"[Frame {task.frame_count}] RESULT ignored (older than frame {last_analysis_frame})")

        with active_analysis_lock:
            active_analysis -= 1
            if active_analysis == 0:
                analysis_pending.clear()

        analysis_queue.task_done()


analysis_threads = [threading.Thread(target=analysis_worker, daemon=True) for _ in range(2)]
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

    color = COLORS.get(current_decision, (255, 255, 255))
    h, w = frame.shape[:2]

    cv2.rectangle(frame, (0, 0), (w, 50), (0, 0, 0), -1)
    cv2.putText(frame, f"OmniWatch | {current_decision}",
                (10, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(frame, f"Frame: {frame_count}/{total_frames}",
                (w - 200, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    if current_decision == "CRITICAL":
        cv2.rectangle(frame, (0, h - 60), (w, h), (0, 0, 180), -1)
        cv2.putText(frame, "CRITICAL - CALL FOR HELP",
                    (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    elif current_decision == "HIGH":
        cv2.rectangle(frame, (0, h - 60), (w, h), (0, 80, 200), -1)
        cv2.putText(frame, "HIGH PRIORITY INCIDENT DETECTED",
                    (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    elif current_decision == "LOW":
        cv2.rectangle(frame, (0, h - 60), (w, h), (0, 150, 150), -1)
        cv2.putText(frame, "LOW PRIORITY — MONITORING",
                    (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    if analysis_pending.is_set():
        cv2.putText(frame, "ANALYSIS PENDING...",
                    (10, h - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    cv2.imshow("OmniWatch Emergency Detection", frame)

    expected_time = frame_count / fps
    actual_time = time.time() - video_start_time
    wait = max(1, int((expected_time - actual_time) * 1000))
    if analysis_pending.is_set():
        wait = max(wait, 500)
    if cv2.waitKey(wait) == 27:
        break

cap.release()

analysis_queue.put(None)
analysis_queue.put(None)
for thread in analysis_threads:
    thread.join(timeout=2)

cv2.destroyAllWindows()