# OmniWatch — Real-Time AI Emergency Detection & Smart Medical Response

> *Watches your cameras. Listens to your building. The moment someone is in danger — it finds the fastest way to get them help.*

Built for the **Claude Hackathon** · 
**Sanjit Subhash**

---

## What Is OmniWatch?

OmniWatch is a real-time AI safety system that monitors live camera feeds and audio streams to detect emergencies — falls, fights, medical collapses — classify their severity, and automatically route the optimal medical response. All within **under 10 seconds**.

Traditional emergency response chains rely on humans noticing, calling, and deciding. OmniWatch automates all three steps, targeting a **30× reduction in response delay** and up to a **+41 percentage-point improvement in survival probability** for time-critical cardiac events.

---

## How It Works

OmniWatch has three intelligent layers working simultaneously:

### Layer 1 — Vision AI (YOLOv8)
The eyes of the system. YOLOv8 runs on live camera frames to detect and track persons in real time. It flags:
- **Falls** — sudden downward motion spike followed by sustained stillness
- **Motionless persons** — no movement detected beyond threshold duration
- **Fights** — high-frequency, high-amplitude motion between two or more people
- **Distress postures** — raised arms, erratic movement patterns

Optical flow energy `E(t)` is computed across the detected bounding box. A fall is declared when:

```
E(t*) > θ_fall  AND  E(t) < θ_still  for all t in [t* + 1, t* + T_wait]
```

where `T_wait = 8s` by default.

### Layer 2 — Audio AI (Whisper + librosa)
The ears of the system. Audio streams are analysed in 64ms windows using short-time energy detection. Flagged signals include:
- Screams and distress calls
- Speech pattern matching ("help", "call 911")
- Impact sounds — sudden low-frequency impulse (body hitting floor)

Audio acts as a confirmation layer — boosting confidence when both video and audio agree.

### Layer 3 — Agentic AI (Claude)
The brain of the system. Once an incident is flagged, Claude:

1. **Fuses** vision and audio confidence scores into a unified signal:
   ```
   C_fused = 0.65 · C_vision + 0.35 · C_audio
   ```
2. **Classifies** severity using the fused score:
   ```
   CLEAR    →  C < 0.25
   LOW      →  0.25 ≤ C < 0.50
   MEDIUM   →  0.50 ≤ C < 0.70
   HIGH     →  0.70 ≤ C < 0.88
   CRITICAL →  C ≥ 0.88
   ```
3. **Reasons** over real hospital data to select the optimal facility:
   ```
   h* = argmin [ w1·ETA(h) + w2·(1/TraumaLevel(h)) + w3·distance(h) ]
   ```
   Weights: `w1=0.5, w2=0.3, w3=0.2`
4. **Generates** a plain-English incident report for security staff
5. **Dispatches** the optimal response automatically

---

## Tech Stack

| Layer | Tool | Role |
|---|---|---|
| Vision detection | **YOLOv8** (Ultralytics) | Person detection, bounding boxes, pose |
| Optical flow | **OpenCV** | Frame-level motion energy computation |
| Audio analysis | **Whisper + librosa** | Distress detection, waveform classification |
| Agentic reasoning | **Claude API** (Anthropic) | Fusion, severity classification, routing decisions |
| Backend | **FastAPI + WebSocket** | Real-time async data pipeline |
| Hospital data | **DataSF Open Data API** | Real SF hospital locations and trauma levels |
| Routing | **OSRM** (open source) | Real road routing and ETA — no API key required |
| Map | **Leaflet.js + CartoDB Dark Matter** | Free tile map, no API key required |
| Auth | **WebAuthn + JWT** | Biometric login (Touch ID), password fallback |
| Database | **MySQL** | Users, sessions, incident logs |
| Frontend | **Vanilla JS + CSS** | Real-time security operations dashboard |

> No Google APIs. No Google Cloud. No paid mapping services. Fully open-source infrastructure.

---

## System Architecture

```
Camera Feed (OpenCV)       Audio Stream (Web Audio API)
        │                           │
   Frame Extractor              Audio Windowing
   (YOLOv8 detection)           (64ms windows)
        │                           │
        └──────────┬────────────────┘
                   │
          Incident Classifier
          (C_fused via Eq. above)
                   │
            Claude Agentic AI
        (reasoning + tool calls)
                   │
         ┌─────────┴──────────┐
    SF Hospital Data      OSRM Routing
    (DataSF API)          (road ETA)
                   │
           Alert Engine (WebSocket)
                   │
         Security Dashboard (browser)
```

---

## Running Locally

### Prerequisites

- Python 3.12 (not 3.14 — pydantic-core incompatibility)
- MySQL 9.x
- Node.js (for http-server)

### Setup

```bash
# 1. Clone and enter backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp env.example .env
# Edit .env — key values:
# DB_HOST=127.0.0.1
# DB_PASSWORD=yourpassword   ← if using special chars, URL-encode them (@ → %40)
# ANTHROPIC_API_KEY=sk-ant-...
# WEBAUTHN_RP_ID=localhost
# WEBAUTHN_ORIGIN=http://localhost:3000
# FRONTEND_ORIGIN=http://localhost:3000

# 3. Start MySQL
sudo /usr/local/mysql/support-files/mysql.server start

# 4. Start backend
uvicorn main:app --reload --port 8000

# 5. Serve frontend (separate terminal)
npx http-server . -p 3000
```

> **Always access the app at `http://localhost:3000`** — never via IP address. WebAuthn requires `localhost` or HTTPS and will break on raw IP.

### Seeded Users

| Username | Role | Password |
|---|---|---|
| sanjit | admin | (biometric / set on first login) |
| lomesh | admin | (biometric / set on first login) |
| shinoy | admin | (biometric / set on first login) |
| judge1 | viewer | |
| judge2 | viewer | |

---

## Key Design Decisions

**Why YOLOv8 for vision?**  
YOLOv8 gives us real-time person detection and bounding boxes at high frame rates with no API dependency. Optical flow runs on top of the detected bounding boxes, making motion analysis both fast and person-specific rather than scene-wide.

**Why Claude for the agentic layer?**  
The routing and severity decisions require genuine multi-factor reasoning — balancing ETA, trauma level, hospital capacity, and distance simultaneously. Claude handles this as a natural language reasoning task, calling tool functions to fetch live hospital data and returning structured dispatch decisions. This is a better fit than a hardcoded scoring function.

**Why OSRM for routing?**  
Free, open-source, no API key, accurate real-road geometry. The public OSRM server handles route requests with sub-second response times.

**Why WebAuthn?**  
A security operations system should use strong authentication. Touch ID via WebAuthn gives judges and operators a seamless, password-free login experience while being cryptographically secure.

---

## Impact Targets

| Metric | Traditional | OmniWatch | Improvement |
|---|---|---|---|
| Detection time | 2.5 – 8 min | < 10 seconds | **30× faster** |
| Survival probability (cardiac, t=5min) | ~42% | ~70% | **+41 percentage points** |
| False positive rate | — | < 5% (target) | Multimodal fusion |

---

## Privacy & Ethics

- **Face blurring** available on all feeds by default
- **No continuous storage** — only encrypted clips of confirmed incidents (`C_fused > 0.50`) are saved
- **Human in the loop** — Claude recommends; humans act
- **Transparent AI logs** — every fusion and routing decision is recorded and reviewable
- **GDPR / CCPA** considerations built in from day one

---

## Future Work

- Wearable integration (smartwatch accelerometer feeding into `E(t)`)
- Multi-camera Kalman-filter tracking across feeds
- Crowd density risk detection before incidents occur
- Direct 911 CAD system integration when `C_fused ≥ 0.97`
- Online learning to update `θ_fall` thresholds from confirmed vs. false positives

---

*Built with Claude · YOLOv8 · FastAPI · Leaflet · OSRM · WebAuthn*  
*University of Missouri Columbia · Claude Hackathon 2026*