# Alchemy Task App — Android

An AI-powered task management app for Android featuring **on-device LLM inference**, capable of creating tasks from photos, voice commands, or manual entry.

---

## Features

| Feature | Description |
|---------|-------------|
| 📸 **Image → Task** | Photograph a whiteboard, sticky note, or document — ML Kit OCR extracts the text, then the local Gemma 2B LLM structures it into a task |
| 🎤 **Voice → Task** | Speak your task naturally — Android SpeechRecognizer transcribes it, then the LLM extracts title, priority, assignee, and due date |
| 🤖 **Local LLM** | 100% on-device inference using Google MediaPipe + Gemma 2B-IT (no cloud calls, no API key required) |
| 📅 **Full metadata** | Title, description, priority, status, due date/time, reminder, assignee, assigned-by, tags |
| 🔍 **Search & filter** | Full-text search across title/description/tags/assignees; status filter chips |
| 🌓 **Material You** | Dynamic colour theming on Android 12+, dark mode support |
| 💾 **Offline-first** | Room (SQLite) database — all data stays on device |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Jetpack Compose UI (screens + navigation)          │
├─────────────────────────────────────────────────────┤
│  TaskViewModel (Hilt, StateFlow, MVVM)              │
├───────────────────────┬─────────────────────────────┤
│  TaskRepository       │  AI Layer                   │
│  (Room DAO)           │  ├─ LocalLLMManager          │
│                       │  │   (MediaPipe Gemma 2B)   │
│                       │  ├─ ImageToTaskProcessor     │
│                       │  │   (ML Kit OCR + LLM)     │
│                       │  └─ VoiceToTaskProcessor     │
│                       │      (SpeechRecognizer+LLM) │
├───────────────────────┴─────────────────────────────┤
│  Room Database (alchemy_tasks.db)                   │
└─────────────────────────────────────────────────────┘
```

### Key packages

```
app/src/main/java/com/alchemy/taskapp/
├── AlchemyTaskApplication.kt   ← Hilt app + WorkManager config
├── MainActivity.kt             ← Edge-to-edge entry point
├── ai/
│   ├── LocalLLMManager.kt      ← MediaPipe Gemma 2B loader & inference
│   ├── ImageToTaskProcessor.kt ← ML Kit OCR → LLM → Task
│   └── VoiceToTaskProcessor.kt ← SpeechRecognizer → LLM → Task
├── data/
│   ├── Task.kt                 ← Room entity with full metadata
│   ├── TaskDao.kt              ← CRUD + search queries (Flow-based)
│   ├── TaskDatabase.kt         ← Room database definition
│   └── TaskRepository.kt       ← Single data source for ViewModels
├── di/
│   └── DatabaseModule.kt       ← Hilt DB + DAO providers
├── ui/
│   ├── navigation/AppNavGraph.kt
│   ├── screens/
│   │   ├── TaskListScreen.kt   ← Search, filter, list, delete, toggle done
│   │   ├── TaskDetailScreen.kt ← Full detail view with image preview
│   │   └── CreateTaskScreen.kt ← Form + AI image/voice create
│   └── theme/Theme.kt          ← Material You / dark mode
├── util/
│   └── TaskJsonParser.kt       ← LLM JSON → Task data class
└── viewmodel/
    └── TaskViewModel.kt        ← All UI logic + AI orchestration
```

---

## Prerequisites

- **Android Studio Hedgehog (2023.1.1)** or newer
- **Android SDK 26+** (minSdk 26 / API 26 = Android 8)
- **Java 17**
- **Gemma 2B model file** (see below)

---

## LLM Model Setup

The app uses **Google Gemma 2B-IT** quantised for on-device inference via MediaPipe.

### 1. Download the model

1. Create a free account at [kaggle.com](https://www.kaggle.com)
2. Go to: https://www.kaggle.com/models/google/gemma/frameworks/tfLite
3. Download one of:
   - `gemma-2b-it-gpu-int4.bin` (~1.3 GB) — recommended for Vulkan-capable devices (most modern Android phones)
   - `gemma-2b-it-cpu-int4.bin` (~1.3 GB) — CPU-only fallback

### 2. Install the model on device

**Option A – ADB (fastest for development):**
```bash
adb shell mkdir -p /data/data/com.alchemy.taskapp/files/models
adb push gemma-2b-it-gpu-int4.bin /data/data/com.alchemy.taskapp/files/models/
```

**Option B – In-app download (production):**
Add a first-run setup screen that downloads the model to `context.filesDir/models/` using `WorkManager` + `DownloadManager`.

### 3. App behaviour without model

- Image tasks: falls back to raw OCR text as title + description (no LLM structuring)
- Voice tasks: raw transcript becomes the task title + description
- The AI status chip in the app bar shows "AI offline" in orange

### Device requirements for GPU inference

| Requirement | Minimum |
|-------------|---------|
| RAM | 4 GB (6 GB+ recommended) |
| Storage free | 2 GB |
| Android | 8.0 (API 26) |
| GPU | Vulkan 1.0+ (for GPU variant) |

---

## Build Instructions

```bash
# Clone (already done if you're in the alchemy repo)
cd android-task-app

# Build debug APK
./gradlew assembleDebug

# Run unit tests
./gradlew test

# Install on connected device
./gradlew installDebug

# Build release APK (requires signing config)
./gradlew assembleRelease
```

---

## Task Data Model

```kotlin
data class Task(
    val id: String,          // UUID
    val title: String,       // Short summary (required)
    val description: String, // Full details
    val priority: TaskPriority,   // LOW | MEDIUM | HIGH | URGENT
    val status: TaskStatus,       // PENDING | IN_PROGRESS | DONE | CANCELLED
    val source: TaskSource,       // MANUAL | IMAGE | VOICE
    val dueDate: Long?,      // Epoch millis UTC
    val reminderDate: Long?, // Epoch millis UTC
    val assignedBy: String,  // Name of person assigning
    val assignedTo: String,  // Name of person responsible
    val tags: String,        // Comma-separated
    val imageUri: String?,   // Source photo URI (image tasks)
    val createdAt: Long,
    val updatedAt: Long
)
```

---

## AI Pipeline Detail

### Image → Task

```
[Camera / Gallery] → InputImage
        ↓
[ML Kit TextRecognition]  (on-device, ~50ms)
        ↓ extracted text
[Gemma 2B LLM Prompt]    (on-device, ~5–30s depending on GPU)
        ↓ structured JSON
[TaskJsonParser]
        ↓
[Task ready for review]
```

**Prompt template used:**
```
Analyse the following text extracted from an image and output a single JSON object:
{ "title", "description", "priority", "assignedTo", "assignedBy", "dueDate", "tags" }
```

### Voice → Task

```
[Microphone] → SpeechRecognizer (Android on-device, streaming)
        ↓ transcript (partial + final)
[Gemma 2B LLM Prompt]    (on-device)
        ↓ structured JSON
[TaskJsonParser]
        ↓
[Task ready for review]
```

---

## Permissions Required

| Permission | Purpose |
|-----------|---------|
| `CAMERA` | Capture photos for image-to-task |
| `READ_MEDIA_IMAGES` (API 33+) / `READ_EXTERNAL_STORAGE` (≤API 32) | Pick images from gallery |
| `RECORD_AUDIO` | Voice-to-task speech recognition |
| `VIBRATE` | Haptic feedback |
| `POST_NOTIFICATIONS` | Task reminder notifications (API 33+) |

All sensitive permissions are requested at runtime with Accompanist Permissions.

---

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| MediaPipe Tasks GenAI | 0.10.14 | On-device Gemma LLM inference |
| MediaPipe Tasks Vision | 0.10.14 | Vision pipeline support |
| ML Kit Text Recognition | 16.0.1 | On-device OCR for image-to-task |
| Room | 2.6.1 | SQLite ORM for task persistence |
| Hilt | 2.52 | Dependency injection |
| Jetpack Compose BOM | 2024.11.00 | Declarative UI |
| Navigation Compose | 2.8.4 | Screen navigation |
| Accompanist Permissions | 0.36.0 | Runtime permission handling |
| Coil | 2.7.0 | Image loading (source image preview) |
| WorkManager | 2.10.0 | Background processing |

---

## Roadmap

- [ ] First-run model download wizard with progress indicator
- [ ] Task reminders via `AlarmManager` + `NotificationCompat`
- [ ] Multi-page image support (process PDF/document scans)
- [ ] Teams / user directory for assignee autocomplete
- [ ] Export tasks to CSV / JSON
- [ ] Alchemy backend sync (REST API integration with the FastAPI server)
- [ ] Widget for quick task creation from home screen
- [ ] Wear OS companion for task status glances
