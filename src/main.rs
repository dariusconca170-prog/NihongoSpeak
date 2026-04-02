#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use anyhow::Result;
use log::{error, info, warn};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use slint::{SharedString, ModelRc, VecModel, Model, PhysicalPosition};
use std::collections::HashMap;
use std::fs;
use std::io::Cursor;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

slint::include_modules!();

// ════════════════════════════════════════════════════════════════
// GLOBAL STATE
// ════════════════════════════════════════════════════════════════

pub struct AppState {
    pub chat_history: Vec<ChatMessage>,
    pub current_level: String,
    pub japanese_ratio: i32,
    pub is_recording: bool,
    pub is_processing: bool,
    pub tts_enabled: bool,
    pub tts_voice: String,
    pub tts_rate: String,
    pub whisper_device: String,
    pub api_key: String,
    pub last_expected_japanese: String,
    pub sessions: Vec<SessionSummary>,
    pub vocab_words: Vec<VocabWord>,
    pub available_scenarios: Vec<Scenario>,
    pub current_scenario: Option<Scenario>,
    /// Stable ID for the current in-progress session.  Cleared on new chat.
    pub current_session_id: Option<String>,
    /// UTC timestamp of when the current session started.
    pub current_session_started: Option<String>,
    /// VOICEVOX base URL (default: http://localhost:50021)
    pub voicevox_url: String,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            chat_history: Vec::new(),
            current_level: "A0.1".to_string(),
            japanese_ratio: 70,
            is_recording: false,
            is_processing: false,
            tts_enabled: true,
            tts_voice: "Zundamon".to_string(),
            tts_rate: "Normal".to_string(),
            whisper_device: "cpu".to_string(),
            api_key: String::new(),
            last_expected_japanese: String::new(),
            sessions: Vec::new(),
            vocab_words: Vec::new(),
            available_scenarios: vec![
                Scenario {
                    id: "ramen_shop".to_string(),
                    name: "Ramen Shop".to_string(),
                    difficulty: "Beginner".to_string(),
                    icon: "🍜".to_string(),
                    system_prompt: "You are a friendly ramen shop waiter in Tokyo. Speak mostly in Japanese, using simple vocabulary. Help the customer order ramen by asking about broth preference (醤油、塩、味噌、豚骨), toppings, and noodle firmness. Stay in character as a helpful, cheerful waiter.".to_string(),
                    initial_message: "いらっしゃいませ！🍜 ようこそ、麺屋へ！\nご注文はお決まりですか？\n(What would you like to order? We have 醤油、塩、味噌、and 豚骨 broth!)".to_string(),
                },
                Scenario {
                    id: "convenience_store".to_string(),
                    name: "Convenience Store".to_string(),
                    difficulty: "Beginner".to_string(),
                    icon: "🏪".to_string(),
                    system_prompt: "You are a convenience store clerk at a Japanese 7-Eleven. Use polite, simple Japanese. Help the customer find items, handle a purchase, and practice common phrases like 袋はご利用ですか and レシートはご入り用ですか. Stay in character.".to_string(),
                    initial_message: "いらっしゃいませ！🏪 何かお探しですか？\n(Welcome! Are you looking for something in particular?)".to_string(),
                },
                Scenario {
                    id: "train_station".to_string(),
                    name: "Train Station".to_string(),
                    difficulty: "Intermediate".to_string(),
                    icon: "🚉".to_string(),
                    system_prompt: "You are a station attendant at a busy Tokyo train station. Help the user buy tickets, find platforms, and understand train announcements. Use intermediate Japanese with some kanji. Practice vocabulary around 切符、ホーム、乗り換え and directions.".to_string(),
                    initial_message: "こんにちは！🚉 どちらまでいらっしゃいますか？\n(Hello! Where are you heading today?)".to_string(),
                },
                Scenario {
                    id: "job_interview".to_string(),
                    name: "Job Interview".to_string(),
                    difficulty: "Advanced".to_string(),
                    icon: "💼".to_string(),
                    system_prompt: "You are a Japanese HR manager conducting a formal job interview. Use keigo (敬語) and business Japanese throughout. Ask the candidate about their experience, strengths, and reasons for applying. Correct any non-keigo responses gently and model proper business speech.".to_string(),
                    initial_message: "本日はお越しいただきありがとうございます。💼\nどうぞお座りください。自己紹介をお願いできますか？\n(Thank you for coming today. Please take a seat. Could you introduce yourself?)".to_string(),
                },
            ],
            current_scenario: None,
            current_session_id: None,
            current_session_started: None,
            voicevox_url: std::env::var("VOICEVOX_URL")
                .unwrap_or_else(|_| "http://localhost:50021".to_string()),
        }
    }
}

static APP_STATE: Lazy<Arc<RwLock<AppState>>> = Lazy::new(|| Arc::new(RwLock::new(AppState::default())));

/// In-memory cache mapping message content → WAV bytes so replays are instant.
static AUDIO_CACHE: Lazy<Arc<RwLock<HashMap<String, Vec<u8>>>>> =
    Lazy::new(|| Arc::new(RwLock::new(HashMap::new())));

// ════════════════════════════════════════════════════════════════
// DATA STRUCTURES
// ════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
    pub timestamp: i64,
    pub emotion: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionSummary {
    pub id: String,
    pub level: String,
    pub started: String,
    pub message_count: usize,
    pub preview: String,
    pub scenario_title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Scenario {
    pub id: String,
    pub name: String,
    pub difficulty: String,
    pub icon: String,
    pub system_prompt: String,
    pub initial_message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VocabWord {
    pub word: String,
    pub reading: String,
    pub struggles: i32,
    pub next_review: String,
    pub level: i32,
    pub is_due: bool,
}

// ════════════════════════════════════════════════════════════════
// SESSION & PATH MANAGEMENT
// ════════════════════════════════════════════════════════════════

fn get_data_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".nihongo_sensei")
}

fn get_sessions_dir() -> PathBuf {
    get_data_dir().join("sessions")
}

fn get_python_executable() -> PathBuf {
    let mut path = std::env::current_exe().unwrap_or_default();
    path.pop(); // Remove the .exe name to get the folder

    #[cfg(target_os = "windows")]
    {
        path.push("python_runtime");
        path.push("Scripts");
        path.push("python.exe");
    }

    #[cfg(not(target_os = "windows"))]
    {
        path.push("python_runtime");
        path.push("bin");
        path.push("python3");
    }

    path
}

fn ensure_directories() {
    let data_dir = get_data_dir();
    let sessions_dir = get_sessions_dir();
    fs::create_dir_all(&sessions_dir).ok();
    fs::create_dir_all(data_dir.join("scripts")).ok();
    fs::create_dir_all(data_dir.join("vocab")).ok();
}

// ════════════════════════════════════════════════════════════════
// VOICEVOX SPEAKER MAPPING
// ════════════════════════════════════════════════════════════════

/// Maps the user-facing voice name stored in `tts_voice` to the
/// VOICEVOX speaker ID used in the `/synthesis` endpoint.
///
/// The default IDs ship with the standard VOICEVOX distribution.
/// Add more entries as needed.
fn voicevox_speaker_id(voice_name: &str) -> i32 {
    match voice_name {
        "Zundamon"        => 3,
        "Zundamon Amaama" => 1,
        "Zundamon Tsuntsun" => 7,
        "Metan"           => 2,   // Shikoku Metan (normal)
        "Metamon"         => 2,   // alias
        "Tsumugi"         => 8,   // Kasukabe Tsumugi
        "Ritsu"           => 9,   // Kurita Ritsu (9 in newer builds)
        "Himari"          => 14,  // Amehare Himari
        "Sora"            => 16,  // Kujirai Sora
        // Legacy edge-tts names → sensible defaults
        "Nanami"          => 3,
        "Keita"           => 13,
        _                 => 3,   // fall back to Zundamon
    }
}

// ════════════════════════════════════════════════════════════════
// VOICEVOX SPEECH SYNTHESIS
// ════════════════════════════════════════════════════════════════

/// Extracts only the Japanese portions of a mixed-language string.
/// Keeps hiragana, katakana, CJK kanji, full-width punctuation,
/// and common Japanese punctuation marks so VOICEVOX receives
/// well-formed sentences instead of isolated character runs.
fn extract_japanese_text_for_tts(text: &str) -> String {
    let mut result = String::new();
    let mut last_was_jp = false;

    for ch in text.chars() {
        let is_jp = matches!(ch,
    '\u{3040}'..='\u{309F}' | // hiragana
    '\u{30A0}'..='\u{30FF}' | // katakana
    '\u{4E00}'..='\u{9FFF}' | // CJK Unified Ideographs
    '\u{3000}'..='\u{303F}' | // CJK symbols & punctuation (。、！？…)
    '\u{FF01}'..='\u{FF60}' | // full-width ASCII variants
    '\u{FF61}'..='\u{FF9F}'   // half-width katakana
);

        if is_jp {
            result.push(ch);
            last_was_jp = true;
        } else if last_was_jp && (ch == ' ' || ch == '\n') {
            // Replace whitespace between Japanese runs with a pause marker
            result.push('、');
            last_was_jp = false;
        } else {
            last_was_jp = false;
        }
    }

    // Trim trailing punctuation-only artifacts
    let trimmed = result.trim_matches(|c: char| c == '、' || c == ' ').to_string();
    trimmed
}

/// Calls the local VOICEVOX engine to synthesise speech and returns
/// raw WAV bytes.  Returns `Err` if VOICEVOX is unreachable or the
/// text is empty / not Japanese.
fn generate_speech(text: &str) -> Result<Vec<u8>> {
    let jp_text = extract_japanese_text_for_tts(text);
    if jp_text.is_empty() {
        anyhow::bail!("No Japanese text to synthesise");
    }

    let (base_url, speaker_id, speed_scale) = {
        let state = APP_STATE.read();
        let url = state.voicevox_url.clone();
        let sid = voicevox_speaker_id(&state.tts_voice);
        let speed = match state.tts_rate.as_str() {
            "Very Slow" => 0.6,
            "Slow"      => 0.8,
            "Normal"    => 1.0,
            "Fast"      => 1.3,
            "Very Fast" => 1.6,
            _           => 1.0,
        };
        (url, sid, speed)
    };

    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;

    // 1. Audio query – obtain prosody JSON
    let query_url = format!(
        "{}/audio_query?text={}&speaker={}",
        base_url,
        urlencoding::encode(&jp_text),
        speaker_id
    );

    let query_resp = client
        .post(&query_url)
        .header("Content-Type", "application/json")
        .send()
        .map_err(|e| anyhow::anyhow!(
            "VOICEVOX unreachable at {} – is it running? ({})", base_url, e
        ))?;

    if !query_resp.status().is_success() {
        let status = query_resp.status();
        let body = query_resp.text().unwrap_or_default();
        anyhow::bail!("VOICEVOX /audio_query failed ({}): {}", status, body);
    }

    let mut query_json: serde_json::Value = query_resp.json()?;

    // Apply speed scaling
    if let Some(obj) = query_json.as_object_mut() {
        obj.insert("speedScale".to_string(), serde_json::json!(speed_scale));
    }

    // 2. Synthesis – obtain WAV bytes
    let synth_url = format!("{}/synthesis?speaker={}", base_url, speaker_id);

    let synth_resp = client
        .post(&synth_url)
        .header("Content-Type", "application/json")
        .json(&query_json)
        .send()?;

    if !synth_resp.status().is_success() {
        let status = synth_resp.status();
        let body = synth_resp.text().unwrap_or_default();
        anyhow::bail!("VOICEVOX /synthesis failed ({}): {}", status, body);
    }

    let wav_bytes = synth_resp.bytes()?.to_vec();
    Ok(wav_bytes)
}

// ════════════════════════════════════════════════════════════════
// AUDIO PLAYBACK (rodio)
// ════════════════════════════════════════════════════════════════

/// Plays raw WAV bytes through the default audio output device.
/// This function blocks until playback finishes, so call it from a
/// background thread.
fn play_audio_buffer(wav_bytes: &[u8]) -> Result<()> {
    let (_stream, stream_handle) = rodio::OutputStream::try_default()
        .map_err(|e| anyhow::anyhow!("No audio output device: {}", e))?;

    let sink = rodio::Sink::try_new(&stream_handle)
        .map_err(|e| anyhow::anyhow!("Failed to create audio sink: {}", e))?;

    let cursor = Cursor::new(wav_bytes.to_vec());
    let source = rodio::Decoder::new(cursor)
        .map_err(|e| anyhow::anyhow!("Failed to decode WAV: {}", e))?;

    sink.append(source);
    sink.sleep_until_end(); // blocks until done

    Ok(())
}

/// High-level helper: generate (or retrieve from cache) and play speech
/// for the given text.  Designed to run on a background thread.
fn speak_text(text: &str, app: &slint::Weak<MainWindow>) {
    // Check cache first
    {
        let cache = AUDIO_CACHE.read();
        if let Some(cached_wav) = cache.get(text) {
            info!("Playing cached audio ({} bytes)", cached_wav.len());
            set_status(app, "🔊 Speaking...");
            if let Err(e) = play_audio_buffer(cached_wav) {
                error!("Playback error: {}", e);
                set_status(app, &format!("❌ Playback: {}", e));
                return;
            }
            set_status(app, "✅ Ready");
            return;
        }
    }

    // Generate fresh audio
    set_status(app, "🔊 Generating speech...");
    match generate_speech(text) {
        Ok(wav_bytes) => {
            // Cache for replay
            {
                let mut cache = AUDIO_CACHE.write();
                // Cap cache at ~50 entries to avoid unbounded memory growth
                if cache.len() > 50 {
                    // Evict oldest by just clearing – simple but effective
                    cache.clear();
                }
                cache.insert(text.to_string(), wav_bytes.clone());
            }

            set_status(app, "🔊 Speaking...");
            if let Err(e) = play_audio_buffer(&wav_bytes) {
                error!("Playback error: {}", e);
                set_status(app, &format!("❌ Playback: {}", e));
                return;
            }
            set_status(app, "✅ Ready");
        }
        Err(e) => {
            warn!("VOICEVOX synthesis failed, falling back to edge-tts: {}", e);
            // Fallback to edge-tts via Python
            handle_play_audio_edge_tts(app, text.to_string());
        }
    }
}

// ════════════════════════════════════════════════════════════════
// API CLIENT
// ════════════════════════════════════════════════════════════════

fn send_to_groq(messages: Vec<ChatMessage>, api_key: &str) -> Result<(String, String)> {
    let client = reqwest::blocking::Client::new();

    let mut chat_messages: Vec<serde_json::Value> = messages
        .iter()
        .take(20)
        .map(|m| {
            serde_json::json!({
                "role": m.role,
                "content": m.content
            })
        })
        .collect();

    let emotion_rule = r#"

[EMOTION RULE]: Always start your response with one of the following
emotion tags, in this order of priority: [NORMAL], [EXCITED], [CHILL], [SURPRISED].
Example: '[EXCITED] すごい！'
"#;

    let base_system = include_str!("../resources/system_prompt.txt");
    let scenario_prompt = {
        let state = APP_STATE.read();
        state.current_scenario.as_ref().map(|s| s.system_prompt.clone())
    };
    let active_system = scenario_prompt.as_deref().unwrap_or(base_system);
    let system_content = format!("{}{}", active_system, emotion_rule);

    chat_messages.insert(0, serde_json::json!({
        "role": "system",
        "content": system_content
    }));

    let response = client
        .post("https://api.groq.com/openai/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({
            "model": "llama-3.3-70b-versatile",
            "messages": chat_messages,
            "temperature": 0.8
        }))
        .send()?;

    let data: serde_json::Value = response.json()?;

    let raw_reply = data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("すみません、エラーが発生しました。");

    let emotion = if raw_reply.contains("[EXCITED]") {
        "EXCITED"
    } else if raw_reply.contains("[CHILL]") {
        "CHILL"
    } else if raw_reply.contains("[SURPRISED]") {
        "SURPRISED"
    } else {
        "NORMAL"
    };

    let clean_reply = raw_reply
        .replace("[NORMAL]", "")
        .replace("[EXCITED]", "")
        .replace("[CHILL]", "")
        .replace("[SURPRISED]", "")
        .trim()
        .to_string();

    Ok((clean_reply, emotion.to_string()))
}

fn translate_text(text: &str, api_key: &str) -> Result<String> {
    let client = reqwest::blocking::Client::new();

    let system_prompt = "You are a precise Japanese-to-English translator. Translate the following text into clear, natural English. Output ONLY the English translation — no labels, no original text, no commentary.";

    let response = client
        .post("https://api.groq.com/openai/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&serde_json::json!({
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.2
        }))
        .send()?;

    let data: serde_json::Value = response.json()?;

    let translation = data["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or("(translation unavailable)");

    Ok(translation.to_string())
}

// ════════════════════════════════════════════════════════════════
// UI HELPER FUNCTIONS
// ════════════════════════════════════════════════════════════════

fn add_message_to_ui(app: &slint::Weak<MainWindow>, msg: &ChatMessage) {
    let role = msg.role.clone();
    let content = msg.content.clone();
    let app = app.clone();

    slint::invoke_from_event_loop(move || {
        if let Some(window) = app.upgrade() {
            let current_messages: Vec<MessageData> = window.get_messages().iter().collect();
            let mut new_messages = current_messages;
            new_messages.push(MessageData {
                role: SharedString::from(&role),
                content: SharedString::from(&content),
            });
            let model = ModelRc::new(VecModel::from(new_messages));
            window.set_messages(model);
        }
    }).ok();
}

fn clear_messages_ui(window: &MainWindow) {
    let empty: Vec<MessageData> = Vec::new();
    let model = ModelRc::new(VecModel::from(empty));
    window.set_messages(model);
}

fn set_status(app: &slint::Weak<MainWindow>, text: &str) {
    let text = SharedString::from(text);
    let app = app.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = app.upgrade() {
            window.set_status_text(text);
        }
    }).ok();
}


// ════════════════════════════════════════════════════════════════
// LEGACY EDGE-TTS FALLBACK
// ════════════════════════════════════════════════════════════════

/// Fallback TTS using edge-tts via Python when VOICEVOX is unavailable.
fn handle_play_audio_edge_tts(app: &slint::Weak<MainWindow>, text: String) {
    info!("Falling back to edge-tts for: {}", &text[..text.len().min(60)]);

    set_status(app, "🔊 Speaking (edge-tts)...");

    let (voice, rate) = {
        let state = APP_STATE.read();
        let v = match state.tts_voice.as_str() {
            "Nanami" | "Zundamon" | "Metan" | "Metamon" | "Tsumugi" => "Nanami",
            "Keita" | "Ritsu" => "Keita",
            other => other,
        };
        (v.to_string(), state.tts_rate.clone())
    };

    let escaped_text = text.replace('\\', "\\\\").replace('"', "\\\"").replace('\n', " ");
    let script = format!(
        r#"
import asyncio
import edge_tts
import os
import tempfile

async def main():
    rate_map = {{
        "Very Slow": "-50%",
        "Slow": "-25%",
        "Normal": "+0%",
        "Fast": "+20%",
        "Very Fast": "+50%"
    }}

    voice_map = {{
        "Nanami": "ja-JP-NanamiNeural",
        "Keita": "ja-JP-KeitaNeural"
    }}

    communicate = edge_tts.Communicate(
        "{text}",
        voice_map.get("{voice}", "ja-JP-NanamiNeural"),
        rate=rate_map.get("{rate}", "+0%")
    )

    output_file = os.path.join(tempfile.gettempdir(), "sensei_tts.mp3")
    await communicate.save(output_file)

    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except ImportError:
        import subprocess
        import sys
        if sys.platform == 'win32':
            subprocess.run(['powershell', '-c', f'(New-Object Media.SoundPlayer "{{}}")'.format(output_file) + '.PlaySync()'], capture_output=True)
        elif sys.platform == 'darwin':
            subprocess.run(['afplay', output_file], capture_output=True)
        else:
            subprocess.run(['aplay', output_file], capture_output=True)

    try:
        os.remove(output_file)
    except:
        pass

asyncio.run(main())
"#,
        text = escaped_text,
        voice = voice,
        rate = rate
    );

    let _ = Command::new(get_python_executable())
        .args(&["-c", &script])
        .output();

    set_status(app, "✅ Ready");
}


// ════════════════════════════════════════════════════════════════
// SLINT MAIN
// ════════════════════════════════════════════════════════════════

fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("日本語 Sensei starting...");
    ensure_directories();

    // Restore vocab progress from previous sessions
    load_vocabulary_from_disk();

    // Load API key from environment or config file
    let api_key = std::env::var("GROQ_API_KEY")
        .ok()
        .or_else(|| load_config_string("api_key"))
        .unwrap_or_default();

    {
        let mut state = APP_STATE.write();
        state.api_key = api_key.clone();

        // Load VOICEVOX URL from config if set
        if let Some(url) = load_config_string("voicevox_url") {
            state.voicevox_url = url;
        }
        // Load preferred voice from config if set
        if let Some(voice) = load_config_string("tts_voice") {
            state.tts_voice = voice;
        }
    }

    // Probe VOICEVOX availability at startup
    {
        let url = APP_STATE.read().voicevox_url.clone();
        match reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(3))
            .build()
            .and_then(|c| c.get(&format!("{}/version", url)).send())
        {
            Ok(resp) if resp.status().is_success() => {
                let ver = resp.text().unwrap_or_default();
                info!("VOICEVOX engine detected: v{}", ver.trim().trim_matches('"'));
            }
            _ => {
                warn!(
                    "VOICEVOX not reachable at {} – TTS will fall back to edge-tts",
                    url
                );
            }
        }
    }

    let app = MainWindow::new().expect("Failed to create main window");

    // ── Center window on screen ──
    app.show().expect("Failed to show main window");
    {
        let window = app.window();
        let scale_factor = window.scale_factor();
        let window_size = window.size();
        let win_width = window_size.width as f32 / scale_factor;
        let win_height = window_size.height as f32 / scale_factor;

        #[cfg(any(target_os = "windows", target_os = "macos", target_os = "linux"))]
        {
            let screen_width = 1920.0_f32;
            let screen_height = 1080.0_f32;
            let x = ((screen_width - win_width) / 2.0 * scale_factor) as i32;
            let y = ((screen_height - win_height) / 2.0 * scale_factor) as i32;
            window.set_position(slint::WindowPosition::Physical(PhysicalPosition::new(x, y)));
        }
    }

    // Set up callbacks
    let app_weak = app.as_weak();

    // ── Send message ──
    {
        let app_handle = app_weak.clone();
        app.on_send_message(move |text| {
            let app = app_handle.clone();
            let text = text.to_string();
            std::thread::spawn(move || {
                handle_send_message(&app, text);
            });
        });
    }

    // ── Start recording ──
    {
        let app_handle = app_weak.clone();
        app.on_start_recording(move || {
            let app = app_handle.clone();
            std::thread::spawn(move || {
                handle_start_recording(&app);
            });
        });
    }

    // ── Stop recording ──
    {
        let app_handle = app_weak.clone();
        app.on_stop_recording(move || {
            let app = app_handle.clone();
            std::thread::spawn(move || {
                handle_stop_recording(&app);
            });
        });
    }

    // ── Play audio (speaker icon on chat bubble) ──
    {
        let app_handle = app_weak.clone();
        app.on_play_audio(move |text| {
            let app = app_handle.clone();
            let text = text.to_string();
            std::thread::spawn(move || {
                handle_play_audio(&app, text);
            });
        });
    }

    // ── Translate ──
    {
        let app_handle = app_weak.clone();
        app.on_translate(move |text| {
            let app = app_handle.clone();
            let text = text.to_string();
            std::thread::spawn(move || {
                handle_translate(&app, text);
            });
        });
    }

    // ── Clear chat ──
    {
        let app_handle = app_weak.clone();
        app.on_clear_chat(move || {
            let app = app_handle.clone();
            clear_chat(&app);
        });
    }

    // ── Save API key ──
    {
        let app_handle = app_weak.clone();
        app.on_save_api_key(move |key| {
            let app = app_handle.clone();
            save_api_key(&app, key.to_string());
        });
    }

    // ── Change level ──
    {
        let app_handle = app_weak.clone();
        app.on_change_level(move |level| {
            let app = app_handle.clone();
            change_level(&app, level.to_string());
        });
    }

    // ── Change ratio ──
    {
        app.on_change_ratio(move |ratio| {
            let mut state = APP_STATE.write();
            state.japanese_ratio = ratio as i32;
        });
    }

    // ── Toggle TTS ──
    {
        let app_handle = app_weak.clone();
        app.on_toggle_tts(move || {
            let mut state = APP_STATE.write();
            state.tts_enabled = !state.tts_enabled;
            let enabled = state.tts_enabled;
            let app = app_handle.clone();
            slint::invoke_from_event_loop(move || {
                if let Some(window) = app.upgrade() {
                    window.set_tts_enabled(enabled);
                }
            }).ok();
        });
    }

    // ── Load sessions (history sidebar) ──
    {
        let app_handle = app_weak.clone();
        app.on_load_sessions(move || {
            let app = app_handle.clone();
            std::thread::spawn(move || {
                load_sessions_handler(&app);
            });
        });
    }

    // ── Load session (scenario selection) ──
    {
        let app_handle = app_weak.clone();
        app.on_load_session(move |scenario_id| {
            let app = app_handle.clone();
            let id = scenario_id.to_string();

            let scenario = {
                let state = APP_STATE.read();
                state.available_scenarios.iter().find(|s| s.id == id).cloned()
            };

            if let Some(scenario) = scenario {
                let greeting = scenario.initial_message.clone();

                {
                    let mut state = APP_STATE.write();
                    state.current_scenario        = Some(scenario);
                    state.chat_history.clear();
                    state.current_session_id      = None;
                    state.current_session_started = None;
                }

                let greeting_msg = ChatMessage {
                    role: "assistant".to_string(),
                    content: greeting.clone(),
                    timestamp: current_timestamp(),
                    emotion: Some("NORMAL".to_string()),
                };

                // Speak the scenario greeting automatically if TTS is enabled
                let tts_enabled = APP_STATE.read().tts_enabled;
                let app_for_tts = app.clone();
                let greeting_for_tts = greeting.clone();

                slint::invoke_from_event_loop(move || {
                    if let Some(window) = app.upgrade() {
                        clear_messages_ui(&window);
                        let greeting_data = vec![MessageData {
                            role: SharedString::from(&greeting_msg.role),
                            content: SharedString::from(&greeting_msg.content),
                        }];
                        let model = ModelRc::new(VecModel::from(greeting_data));
                        window.set_messages(model);
                        window.set_current_tab(0);
                    }
                }).ok();

                if tts_enabled {
                    std::thread::spawn(move || {
                        speak_text(&greeting_for_tts, &app_for_tts);
                    });
                }
            } else {
                // Fall back to file-based session loading for non-scenario ids
                load_session_handler(&app, id);
            }
        });
    }

    // ── Delete session ──
    {
        let app_handle = app_weak.clone();
        app.on_delete_session(move |session_id| {
            let app = app_handle.clone();
            delete_session_handler(&app, session_id.to_string());
        });
    }

    // ── Refresh vocab ──
    {
        let app_handle = app_weak.clone();
        app.on_refresh_vocab(move || {
            let app = app_handle.clone();
            refresh_vocab_handler(&app);
        });
    }

    // ── Mark word as struggle ──
    {
        let app_handle = app_weak.clone();
        app.on_mark_word_struggle(move |word: SharedString| {
            let app = app_handle.clone();
            let word = word.to_string();
            std::thread::spawn(move || {
                on_mark_word_struggle(&app, word);
            });
        });
    }

    // Welcome message
    let welcome = ChatMessage {
        role: "assistant".to_string(),
        content: "やっほー！👋 日本語 Sensei へようこそ！\n\n70/30メソッドであなたの日本語練習をサポートするよ：\n 📖 70% — 日本のストーリーやコンテキストを提供\n ✍️ 30% — あなたが答えるタスク！\n\n始め方：\n • 上からマイクとレベルを選んでね\n • 🗣 音声入力を日本語に設定してね\n • 🎤 を押して話すか、下に書いてね\n • 初心者 → A0.1 试试吧！\n\n一緒に日本語を勉強しましょう！ 🌸".to_string(),
        timestamp: current_timestamp(),
        emotion: Some("NORMAL".to_string()),
    };

    add_message_to_ui(&app_weak, &welcome);

    // Populate the history sidebar with saved sessions before entering the event loop.
    {
        let app_handle = app_weak.clone();
        std::thread::spawn(move || {
            load_sessions_handler(&app_handle);
        });
    }

    app.run().expect("Failed to run application");
}

// ════════════════════════════════════════════════════════════════
// MESSAGE HANDLERS
// ════════════════════════════════════════════════════════════════

/// Called when the user taps "Struggle" / "Repeat" on a vocab card.
/// Increments the struggle count and pushes the next-review date forward
/// using a simple SRS interval: interval = 1 day * (struggles + 1).
fn on_mark_word_struggle(app: &slint::Weak<MainWindow>, word: String) {
    let updated_snapshot = {
        let mut state = APP_STATE.write();

        if let Some(entry) = state.vocab_words.iter_mut().find(|w| w.word == word) {
            entry.struggles += 1;

            let interval_days = entry.struggles as i64; // linear back-off
            let next = chrono::Local::now()
                .checked_add_signed(chrono::Duration::days(interval_days))
                .unwrap_or_else(chrono::Local::now);
            entry.next_review = next.format("%Y-%m-%d").to_string();

            let today = chrono::Local::now().format("%Y-%m-%d").to_string();
            entry.is_due = entry.next_review.as_str() <= today.as_str();
        }

        state.vocab_words.clone()
    };

    sync_vocabulary(&updated_snapshot);

    let app_clone = app.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = app_clone.upgrade() {
            let vocab_data: Vec<VocabData> = updated_snapshot.iter().map(|w| VocabData {
                word: SharedString::from(&w.word),
                reading: SharedString::from(&w.reading),
                struggles: w.struggles,
                next_review: SharedString::from(&w.next_review),
                level: w.level,
                is_due: w.is_due,
            }).collect();
            window.set_vocab(ModelRc::new(VecModel::from(vocab_data)));
        }
    }).ok();
}

fn handle_send_message(app: &slint::Weak<MainWindow>, text: String) {
    if text.trim().is_empty() {
        return;
    }

    let api_key = {
        let state = APP_STATE.read();
        state.api_key.clone()
    };

    if api_key.is_empty() {
        set_status(app, "❌ Please set API key in settings");
        return;
    }

    // Add user message
    let user_msg = ChatMessage {
        role: "user".to_string(),
        content: text.clone(),
        timestamp: current_timestamp(),
        emotion: None,
    };

    add_message_to_ui(app, &user_msg);
    set_status(app, "💭 Sensei is thinking ...");

    // Get chat history
    let messages = {
        let mut state = APP_STATE.write();
        state.chat_history.push(user_msg.clone());
        state.chat_history.clone()
    };

    // Send to Groq
    match send_to_groq(messages, &api_key) {
        Ok((reply, emotion)) => {
            let assistant_msg = ChatMessage {
                role: "assistant".to_string(),
                content: reply.clone(),
                timestamp: current_timestamp(),
                emotion: Some(emotion),
            };

            // Update last expected Japanese for pronunciation scoring
            {
                let mut state = APP_STATE.write();
                state.last_expected_japanese = extract_japanese_words(&reply);
            }

            // Save to history
            {
                let mut state = APP_STATE.write();
                state.chat_history.push(assistant_msg.clone());
            }

            // Extract new vocab words from the reply and persist them
            integrate_vocab_from_reply(&reply);

            // Refresh vocab tab in the UI
            {
                let app_clone = app.clone();
                let vocab_snapshot = {
                    let state = APP_STATE.read();
                    state.vocab_words.clone()
                };
                slint::invoke_from_event_loop(move || {
                    if let Some(window) = app_clone.upgrade() {
                        let vocab_data: Vec<VocabData> = vocab_snapshot.iter().map(|w| VocabData {
                            word: SharedString::from(&w.word),
                            reading: SharedString::from(&w.reading),
                            struggles: w.struggles,
                            next_review: SharedString::from(&w.next_review),
                            level: w.level,
                            is_due: w.is_due,
                        }).collect();
                        window.set_vocab(ModelRc::new(VecModel::from(vocab_data)));
                    }
                }).ok();
            }

            // Save session
            save_current_session();

            add_message_to_ui(app, &assistant_msg);

            // TTS – speak the assistant reply using VOICEVOX (with edge-tts fallback)
            let tts_enabled = {
                let state = APP_STATE.read();
                state.tts_enabled
            };

            if tts_enabled {
                let app_for_tts = app.clone();
                let reply_for_tts = reply.clone();
                // speak_text already runs blocking I/O, and we're already
                // on a background thread, so call directly.
                speak_text(&reply_for_tts, &app_for_tts);
            }

            set_status(app, "✅ Ready");
        }
        Err(e) => {
            error!("Groq API error: {}", e);
            set_status(app, &format!("❌ Error: {}", e));
        }
    }
}

fn handle_start_recording(app: &slint::Weak<MainWindow>) {
    info!("Starting recording...");

    {
        let app = app.clone();
        slint::invoke_from_event_loop(move || {
            if let Some(window) = app.upgrade() {
                window.set_is_recording(true);
                window.set_status_text(SharedString::from("🔴 Recording..."));
            }
        }).ok();
    }

    // Start audio recording using Python script via bundled executable
    let result = Command::new(get_python_executable())
        .args(&["-c", include_str!("../scripts/record_audio.py")])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();

    match result {
        Ok(_) => {
            let mut state = APP_STATE.write();
            state.is_recording = true;
        }
        Err(e) => {
            error!("Failed to start recording: {}", e);
            set_status(app, &format!("❌ Mic error: {}", e));
        }
    }
}

fn handle_stop_recording(app: &slint::Weak<MainWindow>) {
    info!("Stopping recording...");

    {
        let app = app.clone();
        slint::invoke_from_event_loop(move || {
            if let Some(window) = app.upgrade() {
                window.set_is_recording(false);
                window.set_status_text(SharedString::from("⏳ Processing..."));
            }
        }).ok();
    }

    // Stop recording and get audio file via bundled executable
    let audio_result = Command::new(get_python_executable())
        .args(&["-c", include_str!("../scripts/stop_recording.py")])
        .output();

    match audio_result {
        Ok(output) => {
            let audio_path = String::from_utf8_lossy(&output.stdout).trim().to_string();

            if audio_path.is_empty() || audio_path == "None" {
                set_status(app, "⚠ Too short or silent");
                return;
            }

            // Transcribe with Whisper
            let (text, _lang) = match transcribe_audio(&audio_path) {
                Ok(t) => t,
                Err(e) => {
                    error!("Transcription failed: {}", e);
                    set_status(app, &format!("❌ Transcription: {}", e));
                    return;
                }
            };

            if text.is_empty() {
                set_status(app, "⚠ Couldn't recognize speech");
                return;
            }

            // Show user what was transcribed then process
            let user_msg = ChatMessage {
                role: "user".to_string(),
                content: text.clone(),
                timestamp: current_timestamp(),
                emotion: None,
            };
            add_message_to_ui(app, &user_msg);

            // Process with AI
            handle_send_message(app, text);
        }
        Err(e) => {
            error!("Failed to stop recording: {}", e);
            set_status(app, &format!("❌ Audio error: {}", e));
        }
    }
}

fn transcribe_audio(audio_path: &str) -> Result<(String, String)> {
    // Use faster-whisper via Python with bundled executable
    let script = format!(
        r#"
import sys
import json
from faster_whisper import WhisperModel

model_size = "medium"
model = WhisperModel(model_size, device="auto", compute_type="default")

segments, info = model.transcribe(r"{audio_path}", language="ja")
text = "".join(s.text for s in segments)

result = {{"text": text.strip(), "language": info.language}}
print(json.dumps(result))
"#,
        audio_path = audio_path
    );

    let output = Command::new(get_python_executable())
        .args(&["-c", &script])
        .output()?;

    let data: serde_json::Value = serde_json::from_slice(&output.stdout)?;

    Ok((
        data["text"].as_str().unwrap_or("").to_string(),
        data["language"].as_str().unwrap_or("ja").to_string(),
    ))
}

/// Unified play-audio handler invoked from the speaker icon on chat bubbles.
/// Uses VOICEVOX with automatic edge-tts fallback.
fn handle_play_audio(app: &slint::Weak<MainWindow>, text: String) {
    info!("Play audio requested for: {}...", &text[..text.len().min(60)]);
    speak_text(&text, app);
}

fn handle_translate(app: &slint::Weak<MainWindow>, text: String) {
    let api_key = {
        let state = APP_STATE.read();
        state.api_key.clone()
    };

    if api_key.is_empty() {
        return;
    }

    match translate_text(&text, &api_key) {
        Ok(translation) => {
            // Show translation as a system message in chat
            let translation_msg = ChatMessage {
                role: "assistant".to_string(),
                content: format!("📝 Translation:\n「{}」\n→ {}", text, translation),
                timestamp: current_timestamp(),
                emotion: Some("NORMAL".to_string()),
            };
            add_message_to_ui(app, &translation_msg);
        }
        Err(e) => {
            error!("Translation failed: {}", e);
            set_status(app, &format!("❌ Translation failed: {}", e));
        }
    }
}

fn clear_chat(app: &slint::Weak<MainWindow>) {
    {
        let mut state = APP_STATE.write();
        state.chat_history.clear();
        state.current_session_id      = None;
        state.current_session_started = None;
        state.current_scenario        = None;
    }

    // Clear the audio cache when starting a fresh conversation
    {
        let mut cache = AUDIO_CACHE.write();
        cache.clear();
    }

    let app_clone = app.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = app_clone.upgrade() {
            clear_messages_ui(&window);
            window.set_status_text(SharedString::from("🌸 Chat cleared! Let's start fresh."));
        }
    }).ok();

    let welcome = ChatMessage {
        role: "assistant".to_string(),
        content: "🌸 Chat cleared! Let's start fresh.\n新しい会話を始めましょう！ What shall we talk about?".to_string(),
        timestamp: current_timestamp(),
        emotion: Some("NORMAL".to_string()),
    };

    add_message_to_ui(app, &welcome);
}

fn save_api_key(app: &slint::Weak<MainWindow>, key: String) {
    {
        let mut state = APP_STATE.write();
        state.api_key = key.clone();
    }

    // Save to config file
    let config_path = get_data_dir().join("config.json");
    let config = serde_json::json!({
        "api_key": key
    });

    if let Err(e) = fs::write(&config_path, config.to_string()) {
        error!("Failed to save config: {}", e);
    }

    set_status(app, "✅ Settings saved");
}

fn change_level(app: &slint::Weak<MainWindow>, level: String) {
    {
        let mut state = APP_STATE.write();
        state.current_level = level.clone();
    }

    let message = format!("📚 Level → **{}**\nI'll adapt my teaching to this level. 続けましょう！", level);

    let msg = ChatMessage {
        role: "assistant".to_string(),
        content: message,
        timestamp: current_timestamp(),
        emotion: Some("NORMAL".to_string()),
    };

    add_message_to_ui(app, &msg);
}

fn load_sessions_handler(app: &slint::Weak<MainWindow>) {
    let sessions_dir = get_sessions_dir();
    let mut sessions: Vec<SessionSummary> = Vec::new();

    if let Ok(entries) = fs::read_dir(&sessions_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            // Only process .json files
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            if let Ok(content) = fs::read_to_string(&path) {
                if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
                    let id = data["id"].as_str().unwrap_or("").to_string();
                    if id.is_empty() {
                        continue;
                    }

                    let started = data["started"]
                        .as_str()
                        .unwrap_or("")
                        .replace("T", " ")
                        // Trim the time portion to just the date + HH:MM
                        .chars()
                        .take(16)
                        .collect::<String>();

                    let level = data["level"].as_str().unwrap_or("?").to_string();
                    let scenario_title = data["scenario_title"]
                        .as_str()
                        .unwrap_or("")
                        .to_string();
                    let message_count = data["messages"]
                        .as_array()
                        .map(|a| a.len())
                        .unwrap_or(0);

                    // Build a one-line preview: "Ramen Shop · 12 msgs" or the first user line
                    let preview = if !scenario_title.is_empty() {
                        format!("{} · {} msgs", scenario_title, message_count)
                    } else {
                        data["messages"]
                            .as_array()
                            .and_then(|arr| arr.iter().find(|m| m["role"] == "user"))
                            .and_then(|m| m["content"].as_str())
                            .unwrap_or("(no messages)")
                            .chars()
                            .take(50)
                            .collect::<String>()
                    };

                    sessions.push(SessionSummary {
                        id,
                        level,
                        started,
                        message_count,
                        preview,
                        scenario_title,
                    });
                }
            }
        }
    }

    sessions.sort_by(|a, b| b.started.cmp(&a.started));

    {
        let mut state = APP_STATE.write();
        state.sessions = sessions.clone();
    }

    let app_clone = app.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = app_clone.upgrade() {
            let session_data: Vec<SessionData> = sessions.iter().map(|s| {
                SessionData {
                    id: SharedString::from(&s.id),
                    level: SharedString::from(&s.level),
                    started: SharedString::from(&s.started),
                    message_count: s.message_count as i32,
                    preview: SharedString::from(&s.preview),
                }
            }).collect();
            let model = ModelRc::new(VecModel::from(session_data));
            window.set_sessions(model);
        }
    }).ok();
}

fn load_session_handler(app: &slint::Weak<MainWindow>, session_id: String) {
    let session_path = get_sessions_dir().join(format!("session_{}.json", session_id));

    if let Ok(content) = fs::read_to_string(&session_path) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
            let messages: Vec<ChatMessage> = data["messages"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .map(|m| ChatMessage {
                            role: m["role"].as_str().unwrap_or("user").to_string(),
                            content: m["content"].as_str().unwrap_or("").to_string(),
                            timestamp: current_timestamp(),
                            emotion: Some("NORMAL".to_string()),
                        })
                        .collect()
                })
                .unwrap_or_default();

            let level          = data["level"].as_str().unwrap_or("A0.1").to_string();
            let started_raw    = data["started"].as_str().unwrap_or("").to_string();
            let started_pretty = started_raw.replace("T", " ").chars().take(16).collect::<String>();
            let scenario_title = data["scenario_title"].as_str().unwrap_or("").to_string();

            // Try to match the saved scenario_title back to a known Scenario so the
            // AI context is restored correctly for continued conversation.
            let restored_scenario = if !scenario_title.is_empty() {
                let state = APP_STATE.read();
                state.available_scenarios
                    .iter()
                    .find(|s| s.name == scenario_title)
                    .cloned()
            } else {
                None
            };

            {
                let mut state = APP_STATE.write();
                state.chat_history         = messages.clone();
                state.current_level        = level.clone();
                state.current_scenario     = restored_scenario;
                // Re-use the same stable ID so further saves overwrite this file.
                state.current_session_id      = Some(session_id.clone());
                state.current_session_started = Some(started_raw);
            }

            // Clear audio cache when loading a different session
            {
                let mut cache = AUDIO_CACHE.write();
                cache.clear();
            }

            let app_clone  = app.clone();
            let msg_count  = messages.len();
            slint::invoke_from_event_loop(move || {
                if let Some(window) = app_clone.upgrade() {
                    clear_messages_ui(&window);

                    let label = if !scenario_title.is_empty() {
                        format!("📂 {} — {} (Level: {}, {} messages)", scenario_title, started_pretty, level, msg_count)
                    } else {
                        format!("📂 Restored session from {} (Level: {}, {} messages)", started_pretty, level, msg_count)
                    };

                    let mut all_messages: Vec<MessageData> = vec![MessageData {
                        role: SharedString::from("assistant"),
                        content: SharedString::from(label),
                    }];
                    for m in &messages {
                        all_messages.push(MessageData {
                            role: SharedString::from(&m.role),
                            content: SharedString::from(&m.content),
                        });
                    }
                    let model = ModelRc::new(VecModel::from(all_messages));
                    window.set_messages(model);
                    window.set_status_text(SharedString::from(
                        format!("📂 Session loaded ({} messages)", msg_count)
                    ));
                    window.set_current_tab(0);
                }
            }).ok();
        }
    }
}

fn delete_session_handler(app: &slint::Weak<MainWindow>, session_id: String) {
    let session_path = get_sessions_dir().join(format!("session_{}.json", session_id));
    fs::remove_file(session_path).ok();
    // Refresh the session list
    load_sessions_handler(app);
}

fn refresh_vocab_handler(app: &slint::Weak<MainWindow>) {
    let vocab_path = get_data_dir().join("vocab.json");
    let mut words: Vec<VocabWord> = Vec::new();

    if let Ok(content) = fs::read_to_string(&vocab_path) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(obj) = data.as_object() {
                let today = chrono::Local::now().format("%Y-%m-%d").to_string();
                for (word, entry) in obj {
                    let entry_obj = entry.as_object();
                    let next_review = entry_obj.and_then(|e| e["next_review"].as_str()).unwrap_or("").to_string();
                    let is_due = next_review.as_str() <= today.as_str();

                    words.push(VocabWord {
                        word: word.clone(),
                        reading: entry_obj.and_then(|e| e["reading"].as_str()).unwrap_or("").to_string(),
                        struggles: entry_obj.and_then(|e| e["struggles"].as_i64()).unwrap_or(0) as i32,
                        next_review,
                        level: entry_obj.and_then(|e| e["level"].as_i64()).unwrap_or(0) as i32,
                        is_due,
                    });
                }
            }
        }
    }

    words.sort_by(|a, b| b.struggles.cmp(&a.struggles));

    {
        let mut state = APP_STATE.write();
        state.vocab_words = words.clone();
    }

    let app_clone = app.clone();
    slint::invoke_from_event_loop(move || {
        if let Some(window) = app_clone.upgrade() {
            let vocab_data: Vec<VocabData> = words.iter().map(|w| {
                VocabData {
                    word: SharedString::from(&w.word),
                    reading: SharedString::from(&w.reading),
                    struggles: w.struggles,
                    next_review: SharedString::from(&w.next_review),
                    level: w.level,
                    is_due: w.is_due,
                }
            }).collect();
            let model = ModelRc::new(VecModel::from(vocab_data));
            window.set_vocab(model);
        }
    }).ok();
}

// ════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ════════════════════════════════════════════════════════════════

fn save_current_session() {
    let mut state = APP_STATE.write();

    if state.chat_history.is_empty() {
        return;
    }

    let now = chrono::Local::now();

    // Allocate a stable ID the first time; reuse it on every subsequent save.
    if state.current_session_id.is_none() {
        state.current_session_id = Some(now.format("%Y%m%d_%H%M%S").to_string());
        state.current_session_started = Some(now.to_rfc3339());
    }

    let session_id = state.current_session_id.clone().unwrap();
    let started    = state.current_session_started.clone().unwrap_or_else(|| now.to_rfc3339());
    let level      = state.current_level.clone();
    let scenario_title = state
        .current_scenario
        .as_ref()
        .map(|s| s.name.clone())
        .unwrap_or_default();

    let session_data = serde_json::json!({
        "id":             session_id.clone(),
        "level":          level,
        "scenario_title": scenario_title,
        "started":        started,
        "updated":        now.to_rfc3339(),
        "messages": state.chat_history.iter().map(|m| {
            serde_json::json!({
                "role":    m.role,
                "content": m.content,
                "time": chrono::DateTime::from_timestamp(m.timestamp, 0)
                    .map(|dt| dt.to_rfc3339())
                    .unwrap_or_default()
            })
        }).collect::<Vec<_>>()
    });

    let session_path = get_sessions_dir().join(format!("session_{}.json", session_id));
    if let Err(e) = fs::write(&session_path, session_data.to_string()) {
        error!("Failed to save session: {}", e);
    }
}

fn current_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn extract_japanese_words(text: &str) -> String {
    let japanese: String = text
        .chars()
        .filter(|c| matches!(c, '\u{3040}'..='\u{9FFF}'))
        .take(100)
        .collect();
    japanese
}

/// Splits Japanese text into discrete words (runs of kanji/kana).
/// Returns deduplicated words of 1–8 characters, skipping pure-hiragana
/// particles that are a single character.
fn segment_japanese_words(text: &str) -> Vec<String> {
    let mut words: Vec<String> = Vec::new();
    let mut current = String::new();

    for ch in text.chars() {
        let is_jp = matches!(ch,
            '\u{3040}'..='\u{309F}' | // hiragana
            '\u{30A0}'..='\u{30FF}' | // katakana
            '\u{4E00}'..='\u{9FFF}'   // kanji (CJK unified)
        );
        if is_jp {
            current.push(ch);
        } else {
            if !current.is_empty() {
                let w = std::mem::take(&mut current);
                if w.chars().count() >= 2 && w.chars().count() <= 8 {
                    words.push(w);
                }
            }
        }
    }
    if current.chars().count() >= 2 && current.chars().count() <= 8 {
        words.push(current);
    }

    words.sort();
    words.dedup();
    words
}

/// Returns the path to vocab.json.
fn get_vocab_path() -> PathBuf {
    get_data_dir().join("vocab.json")
}

/// Serialises the entire vocab_words vector to vocab.json.
fn sync_vocabulary(words: &[VocabWord]) {
    let obj: serde_json::Map<String, serde_json::Value> = words
        .iter()
        .map(|w| {
            let entry = serde_json::json!({
                "reading":     w.reading,
                "struggles":   w.struggles,
                "next_review": w.next_review,
                "level":       w.level,
            });
            (w.word.clone(), entry)
        })
        .collect();

    let json = serde_json::Value::Object(obj);
    if let Err(e) = fs::write(get_vocab_path(), json.to_string()) {
        error!("Failed to sync vocab.json: {}", e);
    }
}

/// Loads vocab.json into AppState on startup.
fn load_vocabulary_from_disk() {
    let vocab_path = get_vocab_path();
    if let Ok(content) = fs::read_to_string(&vocab_path) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
            if let Some(obj) = data.as_object() {
                let today = chrono::Local::now().format("%Y-%m-%d").to_string();
                let mut words: Vec<VocabWord> = obj
                    .iter()
                    .map(|(word, entry)| {
                        let e = entry.as_object();
                        let next_review = e
                            .and_then(|o| o["next_review"].as_str())
                            .unwrap_or("")
                            .to_string();
                        let is_due = next_review.as_str() <= today.as_str();
                        VocabWord {
                            word: word.clone(),
                            reading: e
                                .and_then(|o| o["reading"].as_str())
                                .unwrap_or("")
                                .to_string(),
                            struggles: e
                                .and_then(|o| o["struggles"].as_i64())
                                .unwrap_or(0) as i32,
                            next_review,
                            level: e
                                .and_then(|o| o["level"].as_i64())
                                .unwrap_or(1) as i32,
                            is_due,
                        }
                    })
                    .collect();
                words.sort_by(|a, b| b.struggles.cmp(&a.struggles));
                let mut state = APP_STATE.write();
                state.vocab_words = words;
            }
        }
    }
}

/// Merges words extracted from a Groq reply into AppState and persists them.
fn integrate_vocab_from_reply(reply: &str) {
    let new_words = segment_japanese_words(reply);
    if new_words.is_empty() {
        return;
    }

    let today = chrono::Local::now().format("%Y-%m-%d").to_string();
    let mut changed = false;

    {
        let mut state = APP_STATE.write();
        for word in &new_words {
            let already_exists = state.vocab_words.iter().any(|w| &w.word == word);
            if !already_exists {
                state.vocab_words.push(VocabWord {
                    word: word.clone(),
                    reading: String::new(),
                    struggles: 0,
                    next_review: today.clone(),
                    level: 1,
                    is_due: false,
                });
                changed = true;
            }
        }
        if changed {
            let snapshot = state.vocab_words.clone();
            sync_vocabulary(&snapshot);
        }
    }
}

fn load_config_string(key: &str) -> Option<String> {
    let config_path = get_data_dir().join("config.json");

    if let Ok(content) = fs::read_to_string(&config_path) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
            return data[key].as_str().map(String::from);
        }
    }

    None
}