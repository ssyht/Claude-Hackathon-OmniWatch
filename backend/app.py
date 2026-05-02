import math
import os
import queue
import threading
import time
from dataclasses import dataclass

import cv2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from gemini_api import analyze_situation, detect_sudden_motion
from speech_api import process_audio
from vision_api import analyze_frame

from database import Base, engine
from auth.webauthn_routes import router as auth_router

VIDEO_PATH = os.path.join(os.path.dirname(__file__), "data", "Footage-1.mp4")
PROCESSED_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "data", "Footage-1-processed.mp4")

app = FastAPI(title="OmniWatch Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
app.include_router(auth_router)

metrics_store = []
metrics_lock = threading.Lock()
current_decision = "CLEAR"
last_gemini_frame = -999
analysis_queue = queue.Queue(maxsize=2)
analysis_pending = threading.Event()
emergency_start_time = None

@dataclass
class FrameAnalysisTask:
    frame: object
    frame_count: int
    trigger: str
    sudden_fall: bool
    fps: float


def get_confidence(decision: str) -> float:
    return {
        "CRITICAL": 0.95,
        "HIGH": 0.80,
        "LOW": 0.45,
        "CLEAR": 0.05,
    }.get(decision, 0.0)


def survival_prob(t_minutes: float) -> float:
    return 0.70 * math.exp(-0.10 * t_minutes) * 100


def fused_confidence(cv_score: float, ca_score: float) -> float:
    return 0.65 * cv_score + 0.35 * ca_score


def build_metric(
    frame_count: int,
    timestamp: float,
    trigger: str,
    labels,
    audio_decision: str,
    transcript: str,
    keywords,
    vision_decision: str,
    final_decision: str,
    emergency_start_time: float,
) -> dict:
    cv_score = get_confidence(vision_decision)
    ca_score = get_confidence(audio_decision)
    fused = fused_confidence(cv_score, ca_score)

    if final_decision in ["CRITICAL", "HIGH"]:
        if emergency_start_time is None:
            emergency_start_time = time.time()
        t_min = (time.time() - emergency_start_time) / 60.0
        survival = survival_prob(t_min)
    else:
        survival = 70.0
        emergency_start_time = None

    return {
        "frame": frame_count,
        "timestamp": round(timestamp, 2),
        "trigger": trigger,
        "vision_labels": labels,
        "audio_decision": audio_decision,
        "transcript": transcript,
        "keywords": keywords,
        "vision_decision": vision_decision,
        "final_decision": final_decision,
        "confidence": {
            "vision": cv_score,
            "audio": ca_score,
            "fused": round(fused, 2),
        },
        "survival_probability": round(survival, 1),
        "emergency_active": final_decision in ["CRITICAL", "HIGH"],
        "emergency_start_time": emergency_start_time,
    }


def analysis_worker() -> None:
    global current_decision, last_gemini_frame, emergency_start_time

    severity = {"CLEAR": 0, "LOW": 1, "HIGH": 2, "CRITICAL": 3}

    while True:
        task = analysis_queue.get()
        if task is None:
            analysis_queue.task_done()
            break

        analysis_pending.set()

        labels = analyze_frame(task.frame)
        audio_decision, transcript, keywords = process_audio(VIDEO_PATH, task.frame_count, task.fps)
        vision_decision = analyze_situation(
            labels,
            audio_text=transcript,
            sudden_fall=task.sudden_fall,
            prev_decision=current_decision,
        )

        final_decision = vision_decision
        if severity.get(audio_decision, 0) > severity.get(vision_decision, 0):
            final_decision = audio_decision

        with metrics_lock:
            metric = build_metric(
                frame_count=task.frame_count,
                timestamp=task.frame_count / task.fps,
                trigger=task.trigger,
                labels=labels,
                audio_decision=audio_decision,
                transcript=transcript,
                keywords=keywords,
                vision_decision=vision_decision,
                final_decision=final_decision,
                emergency_start_time=emergency_start_time,
            )
            metrics_store.append(metric)

        current_decision = final_decision

        if final_decision in ["CRITICAL", "HIGH"]:
            if emergency_start_time is None:
                emergency_start_time = time.time()
        else:
            emergency_start_time = None

        analysis_pending.clear()
        analysis_queue.task_done()


def annotate_frame(frame, decision, frame_count, total_frames):
    h, w = frame.shape[:2]
    color = {
        "CRITICAL": (0, 0, 255),
        "HIGH": (0, 100, 255),
        "LOW": (0, 200, 200),
        "CLEAR": (0, 255, 0),
    }.get(decision, (255, 255, 255))

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 60), (0, 0, 0), -1)
    cv2.putText(overlay, f"OmniWatch | {decision}", (10, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    cv2.putText(
        overlay,
        f"Frame: {frame_count}/{total_frames}",
        (w - 260, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (200, 200, 200),
        1,
    )

    if decision == "CRITICAL":
        cv2.rectangle(overlay, (0, h - 60), (w, h), (0, 0, 180), -1)
        cv2.putText(
            overlay,
            "CRITICAL — PERSON DOWN — CALL FOR HELP",
            (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
    elif decision == "HIGH":
        cv2.rectangle(overlay, (0, h - 60), (w, h), (0, 80, 200), -1)
        cv2.putText(
            overlay,
            "HIGH PRIORITY INCIDENT DETECTED",
            (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
    elif decision == "LOW":
        cv2.rectangle(overlay, (0, h - 60), (w, h), (0, 150, 150), -1)
        cv2.putText(
            overlay,
            "LOW PRIORITY — MONITORING",
            (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

    return overlay


def generate_processed_video() -> None:
    if os.path.exists(PROCESSED_VIDEO_PATH):
        return

    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    processed_fps = min(8.0, max(1.0, fps / 3.0))
    writer = cv2.VideoWriter(
        PROCESSED_VIDEO_PATH,
        cv2.VideoWriter_fourcc(*"mp4v"),
        processed_fps,
        (width, height),
    )

    frame_count = 0
    last_analysis_frame = -999
    current_decision = "CLEAR"
    severity = {"CLEAR": 0, "LOW": 1, "HIGH": 2, "CRITICAL": 3}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        fall_detected, _ = detect_sudden_motion(frame)
        frames_since_last = frame_count - last_analysis_frame
        should_analyze = (
            (fall_detected and frames_since_last > 5)
            or (frame_count % int(fps) == 0 and frames_since_last >= int(fps * 2))
        )

        if should_analyze:
            labels = analyze_frame(frame)
            audio_decision, transcript, keywords = process_audio(VIDEO_PATH, frame_count, fps)
            vision_decision = analyze_situation(
                labels,
                audio_text=transcript,
                sudden_fall=fall_detected,
                prev_decision=current_decision,
            )

            final_decision = vision_decision
            if severity.get(audio_decision, 0) > severity.get(vision_decision, 0):
                final_decision = audio_decision

            current_decision = final_decision
            last_analysis_frame = frame_count

        annotated = annotate_frame(frame, current_decision, frame_count, total_frames)
        writer.write(annotated)

    cap.release()
    writer.release()


def process_video() -> None:
    global last_gemini_frame, current_decision
    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps else 0

    sample_every = 10 if duration < 15 else int(fps)
    min_gemini_gap = 10 if duration < 15 else int(fps * 2)

    frame_count = 0
    last_gemini_frame = -999

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1

        fall_detected, _ = detect_sudden_motion(frame)
        frames_since_last = frame_count - last_gemini_frame
        should_analyze = (
            (fall_detected and frames_since_last > 5)
            or (frame_count % sample_every == 0 and frames_since_last >= min_gemini_gap)
        )

        if should_analyze:
            trigger = "⚡ FALL MOTION" if fall_detected else "🕐 INTERVAL"
            task = FrameAnalysisTask(frame.copy(), frame_count, trigger, fall_detected, fps)
            if not analysis_queue.full():
                analysis_queue.put(task)
                last_gemini_frame = frame_count
            else:
                # keep the pipeline timely if analysis can't keep up
                continue

        time.sleep(0.01)

    cap.release()
    for _ in range(2):
        analysis_queue.put(None)


@app.on_event("startup")
def startup_event() -> None:
    threading.Thread(target=analysis_worker, daemon=True).start()
    threading.Thread(target=analysis_worker, daemon=True).start()
    threading.Thread(target=process_video, daemon=True).start()
    threading.Thread(target=generate_processed_video, daemon=True).start()


@app.get("/status")
def status() -> JSONResponse:
    return JSONResponse({"status": "ok", "video": os.path.basename(VIDEO_PATH)})


@app.get("/metrics")
def get_metrics() -> JSONResponse:
    with metrics_lock:
        return JSONResponse({"metrics": metrics_store, "current_decision": current_decision})


@app.get("/metrics/latest")
def get_latest_metric() -> JSONResponse:
    with metrics_lock:
        if not metrics_store:
            return JSONResponse({"metric": None})
        return JSONResponse({"metric": metrics_store[-1]})


@app.get("/video")
def get_video() -> FileResponse:
    if os.path.exists(PROCESSED_VIDEO_PATH):
        return FileResponse(PROCESSED_VIDEO_PATH, media_type="video/mp4")
    return FileResponse(VIDEO_PATH, media_type="video/mp4")
