// Configuration constants

pub const APP_NAME: &str = "日本語 Sensei";
pub const APP_VERSION: &str = "1.0.0";

pub const WHISPER_MODEL_SIZE: &str = "medium";
pub const WHISPER_LANGUAGE: &str = "ja";
pub const GROQ_MODEL: &str = "llama-3.3-70b-versatile";

pub const SAMPLE_RATE: i32 = 16000;
pub const CHANNELS: i32 = 1;
pub const MIN_RECORD_SECONDS: f32 = 0.4;
pub const SILENCE_RMS_FLOOR: f32 = 0.001;

pub const JLPT_LEVELS: &[&str] = &[
    "A0.1",
    "A0.2",
    "A0.3",
    "Beginner",
    "Elementary",
    "N5",
    "N4",
    "N3",
    "N2",
    "N1",
    "Any Level",
];

pub const TTS_VOICES: &[(&str, &str)] = &[
    ("Nanami 👩 (Female)", "ja-JP-NanamiNeural"),
    ("Keita 👨 (Male)", "ja-JP-KeitaNeural"),
];

pub const TTS_RATES: &[(&str, &str)] = &[
    ("Very Slow", "-50%"),
    ("Slow", "-25%"),
    ("Normal", "+0%"),
    ("Fast", "+20%"),
    ("Very Fast", "+50%"),
];

// SRS (Spaced Repetition System) intervals in days
pub const SRS_INTERVALS: &[i32] = &[1, 3, 7, 14, 30];
