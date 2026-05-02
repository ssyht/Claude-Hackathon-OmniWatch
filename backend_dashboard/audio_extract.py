import subprocess
import os
import wave
import json
from google.cloud import speech
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "omniwatch-493021-989e97f5204a.json"
)

speech_client = speech.SpeechClient(credentials=credentials)

EMERGENCY_KEYWORDS = [
    "help", "fire", "call 911", "emergency", "somebody help",
    "please help", "i can't breathe", "can't breathe", "heart attack",
    "he's not breathing", "she's not breathing", "call an ambulance",
    "stop", "let me go", "get off", "scream", "no no no",
    "i fell", "i'm falling", "i fell down", "i'm hurt",
    "ambulance", "doctor", "pain", "my chest", "i can't move"
]

def extract_audio_chunk(video_path, start_sec, duration_sec=3, output_path="temp_audio.wav"):
    """Extract a chunk of audio from video at given timestamp."""
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", video_path,
            "-t", str(duration_sec),
            "-vn",                    # no video
            "-acodec", "pcm_s16le",   # WAV format
            "-ar", "16000",           # 16kHz for Speech API
            "-ac", "1",               # mono
            output_path
        ], capture_output=True, check=True)
        return output_path
    except Exception as e:
        print(f"Audio extract error: {e}")
        return None

def transcribe_audio(audio_path):
    """Transcribe audio using Google Cloud Speech-to-Text."""
    try:
        with open(audio_path, "rb") as f:
            audio_content = f.read()

        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
        )

        response = speech_client.recognize(config=config, audio=audio)

        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript + " "

        return transcript.strip().lower()
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""

def analyze_audio_emergency(transcript):
    """Analyze transcript for emergency keywords and patterns."""
    if not transcript:
        return "CLEAR", []

    found_keywords = []
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in transcript:
            found_keywords.append(keyword)

    # classify based on keywords found
    if any(k in found_keywords for k in [
        "call 911", "emergency", "heart attack", "can't breathe",
        "he's not breathing", "she's not breathing", "call an ambulance",
        "i fell down", "ambulance"
    ]):
        return "CRITICAL", found_keywords

    elif any(k in found_keywords for k in [
        "help", "somebody help", "please help", "stop",
        "let me go", "get off", "no no no", "i'm hurt"
    ]):
        return "HIGH", found_keywords

    elif any(k in found_keywords for k in [
        "i fell", "i'm falling", "pain", "my chest",
        "i can't move", "doctor"
    ]):
        return "LOW", found_keywords

    return "CLEAR", []

def get_audio_energy(audio_path):
    """Detect screams/loud sounds via audio energy even without transcription."""
    try:
        import wave, struct, math
        with wave.open(audio_path, 'r') as wf:
            frames = wf.readframes(wf.getnframes())
            samples = struct.unpack(f"{len(frames)//2}h", frames)
            if not samples:
                return 0.0
            rms = math.sqrt(sum(s**2 for s in samples) / len(samples))
            return rms
    except Exception as e:
        print(f"Energy error: {e}")
        return 0.0