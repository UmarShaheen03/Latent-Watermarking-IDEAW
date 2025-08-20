import yaml
import os
import random
from pydub import AudioSegment

from utils import *

if __name__ == "__main__":
    config_path = "./data/config.yaml"
    export_path = "./data/fma_wav"

    # Read from dataConfig, get hyper parameters for STFT
    with open(config_path) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

        data_path = config["mp3_path"]

        audio_path_list = []  # save absolute paths of audio files
        for root_path, dirs, files in os.walk(data_path):
            for file in files:
                file_path = os.path.join(root_path, file)
                if file_path.split(".")[-1].lower() in ["mp3", "flac", "wav"]:
                    audio_path_list.append(file_path)
        random.shuffle(audio_path_list)
        print(f"[Dataset]got {len(audio_path_list)} audio files")

    for i, audio_path in enumerate(audio_path_list):
        try:
            song = AudioSegment.from_mp3(audio_path)
            newsong = song.set_frame_rate(16000).set_channels(1)
            newpath = audio_path.split(".")[1]
            filename = export_path+"/"+ newpath.split("/")[-1]+".wav"
            newsong.export(filename, format="wav")
        except Exception as e:
            print(f"[WARN] Skipping {audio_path} ({e})")
            
        print(f"[Dataset]exported {i+1} audio file(s) as wav",end="\r")




        