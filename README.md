# MindSpace

MindSpace is a Django-based wellness screening and support platform. It provides a guided mental-wellness check-in flow using face video, voice phonation, scenario voice response, multimodal AI analysis, personalized activity recommendations, counselor support, and a supportive chatbot interface.

> **Important:** MindSpace provides wellness risk predictions and supportive tools. It is not a medical diagnosis system and should not replace professional mental-health care.

---

## Features

### User and Account Features

- Email/password signup and login
- Email verification flow
- Profile completion flow
- Google OAuth support through `django-allauth`
- Role-aware dashboard flow
- Sidebar navigation for Dashboard, Wellness Check, Counselor, Activity, and Chat

### Wellness Check Pipeline

MindSpace has a three-activity wellness check pipeline:

1. **Face Video Activity**
   - User records/uploads face video.
   - Backend stores media metadata.
   - Face Feature Extraction API runs in background.
   - Face scoring result is saved.

2. **Voice Phonation Activity**
   - User records 7 Hindi vocal sounds.
   - Audio files are saved separately.
   - Backend combines all 7 sounds into one WAV file.
   - Voice feature extraction, PCA, and scoring run in background.

3. **Scenario Voice Response**
   - User responds to a scenario by voice.
   - Audio is submitted automatically after timer completion.
   - Sarvam STT transcription runs.
   - Text feature extraction and text scoring run.
   - Fusion task starts automatically after text result is saved.

4. **Fusion Prediction**
   - Face + voice + text features are combined.
   - Fusion API generates final prediction.
   - `user_prediction_summaries` stores one latest prediction summary per user.

### Dashboard Features

- Current streak
- Today’s activity progress
- Latest maximum wellness-risk result
- Personalized recommendation preview
- Notification dropdown
- Badge preview
- Reminder and support cards

### Activity Recommendation System

The Activity section recommends wellness activities based on the latest prediction result:

- Normal → Daily balance activities
- Stress → Stress reset activities
- Anxiety → Grounding activities
- Depression → Mood activation activities
- Bipolar → Stability routine activities
- Suicidal tendency → Safety support activities

### Chatbot

MindSpace includes a supportive chat page that connects to an external chatbot API through a Django proxy endpoint. The API key stays hidden in `.env`.

---

## Project Structure

```text
MindSpace/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── mindspace/
│   ├── models.py
│   ├── admin.py
│   ├── middleware.py
│   ├── services/
│   │   ├── activity/
│   │   │   └── recommendations.py
│   │   └── assessments/
│   │       ├── api_clients.py
│   │       ├── fusion_builder.py
│   │       ├── media_processing.py
│   │       ├── result_savers.py
│   │       └── storage.py
│   ├── tasks/
│   │   └── assessments.py
│   └── views/
│       ├── accounts/
│       ├── activity/
│       ├── analysis/
│       ├── assessments/
│       ├── consent/
│       ├── dashboard/
│       ├── governance/
│       ├── pages/
│       ├── profiles/
│       └── security/
├── templates/
│   ├── accounts/
│   ├── activity/
│   │   ├── activity_hub.html
│   │   ├── breathing/
│   │   └── movement/
│   ├── assessments/
│   ├── chat/
│   ├── counselor/
│   ├── dashboard/
│   ├── includes/
│   ├── layouts/
│   └── pages/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│       └── activities/
├── media/
├── logs/
├── requirements.txt
└── manage.py
```

Your project already has a Django app folder, service folders for activity recommendations and assessment processing, task files for background processing, templates, static activity images, and media upload folders.

---

## Core User Flow

```text
Signup/Login
↓
Complete Profile
↓
Accept Consent
↓
Dashboard
↓
Wellness Check
↓
Face Video Activity
↓
Voice Phonation Activity
↓
Scenario Voice Response
↓
Background Text + Fusion Analysis
↓
Activity Complete Page
↓
Dashboard shows latest result + personalized activity
```

---

## Tech Stack

- **Backend:** Django 6.x
- **Language:** Python 3.12+
- **Database:** PostgreSQL
- **Auth:** Django auth + django-allauth
- **Background Tasks:** Django-Q / Django-Q2
- **Queue Broker:** Redis recommended for production
- **Media:** Local media in development, optional GCP Cloud Storage for production
- **Frontend:** Django templates, HTML, CSS, JavaScript
- **External APIs:** Face, voice, PCA, text, fusion, Sarvam STT, and chatbot APIs

---

## Setup Guide

### 1. Clone the project

```bash
git clone <your-repo-url>
cd MS
```

### 2. Create virtual environment

Using Conda:

```bash
conda create -n mindspace python=3.12
conda activate mindspace
```

Or using venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env`

Create `.env` in the project root.

---

## Environment Variables

```env
# Django
SECRET_KEY=change-this-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Database
DB_NAME=mds
DB_USER=mds_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Site
SITE_BASE_URL=http://127.0.0.1:8000
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=your_email@gmail.com

# Assessment APIs
FACE_EXTRACT_URL=http://88.222.12.15:5100/extract/video
FACE_SCORE_URL=http://127.0.0.1:8011
VOICE_FEATURE_URL=http://127.0.0.1:8013
VOICE_SCORE_URL=http://127.0.0.1:9100
TEXT_PARAMETER_URL=http://127.0.0.1:8025
TEXT_SCORE_URL=http://127.0.0.1:9000
FUSION_API_URL=http://127.0.0.1:8000

# API Keys
VOICE_FEATURE_EXTRACT_API_KEY=
VOICE_FEATURE_TO_MH=
SARVAM_API_KEY=

# Chatbot API
CHATBOT_API_URL=http://127.0.0.1:7000/chat
CHATBOT_API_KEY=

# Storage
USE_GCP_STORAGE=False
GS_BUCKET_NAME=
GOOGLE_APPLICATION_CREDENTIALS=
```

---

## Database Setup

### Create PostgreSQL database

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE mds;
CREATE USER mds_user WITH PASSWORD 'your_password';
ALTER ROLE mds_user SET client_encoding TO 'utf8';
ALTER ROLE mds_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE mds_user SET timezone TO 'Asia/Kolkata';
GRANT ALL PRIVILEGES ON DATABASE mds TO mds_user;
\q
```

### Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Create superuser

```bash
python manage.py createsuperuser
```

---

## Running the Project

Start Django:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Admin:

```text
http://127.0.0.1:8000/admin/
```

---

## Background Tasks

MindSpace uses background tasks for heavy API calls.

Run qcluster in a second terminal:

```bash
python manage.py qcluster
```

Recommended task split:

```text
process_face_video_task(screening_session_id, video_session_id)
process_combined_voice_phonation_task(screening_session_id)
process_scenario_voice_task(screening_session_id, scenario_session_id, media_id)
process_fusion_task(screening_session_id)
```

---

## Assessment Pipeline

### Face Pipeline

```text
Face video upload
↓
MediaAsset
↓
VideoSession
↓
Face Feature Extract API
↓
FaceFeatureVector
↓
Face Score API
↓
FacialAnalysisResult
↓
ModalityResult(face)
```

### Voice Pipeline

```text
7 separate phonation sounds
↓
PhonationAttempt rows
↓
Combined WAV file
↓
AudioExtractionResult
↓
PhonationFeature
↓
PCA Pipeline Result
↓
Voice Score API
↓
VoiceAnalysisResult
↓
ModalityResult(voice)
```

### Scenario/Text Pipeline

```text
Scenario audio upload
↓
ScenarioSession
↓
Sarvam STT
↓
Transcript
↓
Text Parameter API
↓
TextParameterResult
↓
Text Score API
↓
TextAnalysisResult
↓
ModalityResult(text)
↓
Auto-start Fusion task
```

### Fusion Pipeline

```text
ModalityResult(face)
ModalityResult(voice)
ModalityResult(text)
↓
Build fusion payload
↓
Fusion API
↓
FusionPrediction
↓
UserPredictionSummary
↓
PlatformScreeningSession marked completed
```

---

## Personalized Activity System

Activity recommendations live in:

```text
mindspace/services/activity/recommendations.py
```

Activity templates:

```text
templates/activity/
├── activity_hub.html
├── breathing/
│   ├── breath_box.html
│   ├── breath_478.html
│   ├── breath_extended_exhale.html
│   ├── breath_paced_recovery.html
│   ├── breath_resonance.html
│   └── breath_triangle.html
└── movement/
    ├── grounding_flow.html
    ├── neck_release.html
    ├── shoulder_unlock.html
    ├── spine_wakeup.html
    └── stillness_stretch.html
```

Activity images:

```text
static/images/activities/
├── grounding_flow/
├── neck_release/
├── shoulder_unlock/
├── spine_wakeup/
└── stillness_stretch/
```

The Activity page reads `user_prediction_summaries` and recommends matching tools based on the latest prediction label.

---

## Chatbot Integration

Chat template:

```text
templates/chat/chat.html
```

Example URLs:

```python
path("chat/", chat_views.chat_page_view, name="chat_page")
path("chat/api/send/", chat_views.chat_api_proxy_view, name="chat_api_send")
```

The browser sends messages to Django:

```text
/chat/api/send/
```

Django sends them to the external chatbot API configured in `.env`:

```env
CHATBOT_API_URL=http://127.0.0.1:7000/chat
CHATBOT_API_KEY=your_key
```

Recommended chatbot API response:

```json
{
  "reply": "I understand. Let's slow down and take one step at a time."
}
```

---

## Static and Media Files

### Static files

Static files store CSS, JS, images, SVG activities, avatars, and UI images.

```text
static/
├── css/
├── js/
└── images/
```

### Media files

Media files store uploaded user activity files.

```text
media/activity_uploads/
├── face-video/
├── voice-phonation/
├── voice-phonation-combined/
└── scenario-voice-response/
```

Do not commit `media/` files to Git.

---

## Useful Commands

### Run checks

```bash
python manage.py check
```

### Create migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Run server

```bash
python manage.py runserver
```

### Run background worker

```bash
python manage.py qcluster
```

### Open database shell

```bash
python manage.py dbshell
```

### Clear sessions

```bash
python manage.py clearsessions
```

### Collect static for production

```bash
python manage.py collectstatic
```

### Reset only pipeline data

```sql
TRUNCATE TABLE
    user_prediction_summaries,
    modality_results,
    fusion_predictions,
    facial_analysis_results,
    face_feature_vectors,
    video_sessions,
    voice_analysis_results,
    pca_pipeline_results,
    phonation_features,
    audio_extraction_results,
    phonation_attempts,
    phonation_sessions,
    phonation_sounds,
    text_analysis_results,
    text_parameter_results,
    transcripts,
    scenario_sessions,
    audio_scenarios,
    media_assets,
    platform_screening_sessions
RESTART IDENTITY CASCADE;
```

---

## Troubleshooting

### Activity images not showing

Check exact filename and extension.

Wrong:

```text
images/activities/grounding_flow/reach_overhead.png
```

Correct:

```text
images/activities/grounding_flow/reach_overhead.svg
```

Test direct URL:

```text
http://127.0.0.1:8000/static/images/activities/grounding_flow/reach_overhead.svg
```

### qcluster not processing

Run:

```bash
python manage.py qcluster
```

If it fails, check import errors first.

### Fusion fails because text result is missing

Do not call fusion from frontend immediately. Let `process_scenario_voice_task` start `process_fusion_task` after text result is saved.

### Chatbot API failed to parse URL

Check `.env`:

```env
CHATBOT_API_URL=http://your-host:your-port/chat
```

Do not keep placeholder values like:

```text
http://YOUR_API_HOST:YOUR_PORT/chat
```

---

## Production Notes

Before deployment:

- Set `DEBUG=False`
- Use a strong `SECRET_KEY`
- Configure correct `ALLOWED_HOSTS`
- Configure `CSRF_TRUSTED_ORIGINS`
- Use PostgreSQL
- Use Redis broker for Django-Q2
- Use production WSGI/ASGI server
- Use HTTPS
- Move media storage to GCP Cloud Storage or similar
- Do not expose API keys in frontend JavaScript
- Add logging and monitoring
- Add rate limiting for chatbot and upload APIs
- Add file validation for all uploaded media
- Add privacy and retention policies for sensitive user activity files

---

## Safety Disclaimer

MindSpace outputs are wellness risk predictions based on automated analysis. They are not clinical diagnoses. For serious concerns, users should contact a counselor, trusted person, emergency service, or qualified mental-health professional.

---

## Author

MindSpace project by Nakul Pejwar.
