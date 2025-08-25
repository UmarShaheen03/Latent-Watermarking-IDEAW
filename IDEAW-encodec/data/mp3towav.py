from pydub import AudioSegment
import os

# Input/output directories
input_dir = "./data/fma_medium"
output_dir = "./data/fma_wav"
os.makedirs(output_dir, exist_ok=True)

# Target sample rate
target_sr = 16000

# Iterate over audio files
for root, _, files in os.walk(input_dir):
    for file in files:
        if file.lower().endswith((".mp3", ".flac", ".wav")):
            input_path = os.path.join(root, file)
            output_path = os.path.join(output_dir, os.path.splitext(file)[0] + ".wav")
            try:
                # Load audio
                audio = AudioSegment.from_file(input_path)

                # Resample to target sample rate
                audio = audio.set_frame_rate(target_sr).set_channels(1)

                # Export as WAV
                audio.export(output_path, format="wav")
                print(f"[Converted] {input_path} -> {output_path}, sr={target_sr}")
            except Exception as e:
                print(f"[Error] {input_path}: {e}")