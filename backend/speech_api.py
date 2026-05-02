from audio_extract import (
    extract_audio_chunk,
    transcribe_audio,
    analyze_audio_emergency,
    get_audio_energy
)

def process_audio(video_path, current_frame, fps):
    """Extract and analyze audio around current frame position."""
    current_sec = current_frame / fps
    start_sec = max(0, current_sec - 2)  # 2 seconds before current frame

    audio_path = extract_audio_chunk(video_path, start_sec, duration_sec=3)
    if not audio_path:
        return "CLEAR", "", []

    # check energy first (fast — detects screams without API call)
    energy = get_audio_energy(audio_path)
    print(f"  [Audio] Energy: {energy:.0f}")

    # transcribe if energy is above silence threshold
    transcript = ""
    if energy > 500:  # adjust threshold based on your videos
        transcript = transcribe_audio(audio_path)
        if transcript:
            print(f"  [Audio] Transcript: '{transcript}'")

    audio_decision, keywords = analyze_audio_emergency(transcript)

    # high energy even without keywords = possible scream
    if energy > 3000 and audio_decision == "CLEAR":
        audio_decision = "LOW"
        print(f"  [Audio] High energy detected (possible scream): {energy:.0f}")

    if keywords:
        print(f"  [Audio] Emergency keywords: {keywords}")

    return audio_decision, transcript, keywords