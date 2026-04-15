# Gemma Model Files for Alchemy Task App

This directory is intentionally empty in the repository.

## Setup instructions

1. Download the Gemma 2B-IT quantised model from Kaggle:
   https://www.kaggle.com/models/google/gemma/frameworks/tfLite

2. Copy the downloaded `.bin` file here:
   `android-task-app/app/src/main/assets/models/`
   
   OR push directly to a connected device via ADB:
   ```bash
   adb shell mkdir -p /data/data/com.alchemy.taskapp/files/models
   adb push gemma-2b-it-gpu-int4.bin /data/data/com.alchemy.taskapp/files/models/
   ```

Model files are excluded from git via `.gitignore` due to their size (~1.3 GB).
