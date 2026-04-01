use anyhow::Result;
use log::{error, info};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use slint::{SharedString, ModelRc, VecModel};
use std::fs;
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
            tts_voice: "Nanami".to_string(),
            tts_rate: "Normal".to_string(),
            whisper_device: "cpu".to_string(),
            api_key: String::new(),
            last_expected_japanese: String::new(),
            sessions: Vec::new(),
            vocab_words: Vec::new(),
        }
    }
}

static APP_STATE: Lazy<Arc<RwLock<AppState>>> = Lazy::new(|| Arc::new(RwLock::new(AppState::default())));

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
// SESSION MANAGEMENT
// ════════════════════════════════════════════════════════════════

fn get_data_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".nihongo_sensei")
}

fn get_sessions_dir() -> PathBuf {
    get_data_dir().join("sessions")
}

fn ensure_directories() {
    let data_dir = get_data_dir();
    let sessions_dir = get_sessions_dir();
    fs::create_dir_all(&sessions_dir).ok();
    fs::create_dir_all(data_dir.join("scripts")).ok();
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
    let system_content = format!("{}{}", base_system, emotion_rule);

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

fn set_status_sync(window: &MainWindow, text: &str) {
    window.set_status_text(SharedString::from(text));
}

// ════════════════════════════════════════════════════════════════
// SLINT MAIN
// ════════════════════════════════════════════════════════════════

fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("日本語 Sensei starting...");
    ensure_directories();

    // Load API key from environment or config file
    let api_key = std::env::var("GROQ_API_KEY")
        .ok()
        .or_else(|| load_config_string("api_key"))
        .unwrap_or_default();

    {
        let mut state = APP_STATE.write();
        state.api_key = api_key.clone();
    }

    let app = MainWindow::new().expect("Failed to create main window");

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

    // ── Play audio ──
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

    // ── Load sessions ──
    {
        let app_handle = app_weak.clone();
        app.on_load_sessions(move || {
            let app = app_handle.clone();
            load_sessions_handler(&app);
        });
    }

    // ── Load session ──
    {
        let app_handle = app_weak.clone();
        app.on_load_session(move |session_id| {
            let app = app_handle.clone();
            load_session_handler(&app, session_id.to_string());
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

    // Welcome message
    let welcome = ChatMessage {
        role: "assistant".to_string(),
        content: "やっほー！👋 日本語 Sensei へようこそ！\n\n70/30メソッドであなたの日本語練習をサポートするよ：\n 📖 70% — 日本のストーリーやコンテキストを提供\n ✍️ 30% — あなたが答えるタスク！\n\n始め方：\n • 上からマイクとレベルを選んでね\n • 🗣 音声入力を日本語に設定してね\n • 🎤 を押して話すか、下に書いてね\n • 初心者 → A0.1 试试吧！\n\n一緒に日本語を勉強しましょう！ 🌸".to_string(),
        timestamp: current_timestamp(),
        emotion: Some("NORMAL".to_string()),
    };

    add_message_to_ui(&app_weak, &welcome);

    app.run().expect("Failed to run application");
}

// ════════════════════════════════════════════════════════════════
// MESSAGE HANDLERS
// ════════════════════════════════════════════════════════════════

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

            // Save session
            save_current_session();

            add_message_to_ui(app, &assistant_msg);

            // TTS if enabled
            let tts_enabled = {
                let state = APP_STATE.read();
                state.tts_enabled
            };

            if tts_enabled {
                set_status(app, "🔊 Speaking...");
                handle_play_audio(app, reply);
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

    // Start audio recording using Python script
    let result = Command::new("python3")
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

    // Stop recording and get audio file
    let audio_result = Command::new("python3")
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
    // Use faster-whisper via Python
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

    let output = Command::new("python3")
        .args(&["-c", &script])
        .output()?;

    let data: serde_json::Value = serde_json::from_slice(&output.stdout)?;

    Ok((
        data["text"].as_str().unwrap_or("").to_string(),
        data["language"].as_str().unwrap_or("ja").to_string(),
    ))
}

fn handle_play_audio(app: &slint::Weak<MainWindow>, text: String) {
    info!("Playing TTS for: {}", text);

    set_status(app, "🔊 Speaking...");

    // Use edge-tts
    let (voice, rate) = {
        let state = APP_STATE.read();
        (state.tts_voice.clone(), state.tts_rate.clone())
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

    let _ = Command::new("python3")
        .args(&["-c", &script])
        .output();

    set_status(app, "✅ Ready");
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
            if let Ok(content) = fs::read_to_string(entry.path()) {
                if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
                    let started = data["started"].as_str().unwrap_or("").replace("T", " ");
                    let level = data["level"].as_str().unwrap_or("?");
                    let messages = data["messages"].as_array().map(|a| a.len()).unwrap_or(0);

                    let preview = data["messages"]
                        .as_array()
                        .and_then(|arr| arr.iter().find(|m| m["role"] == "user"))
                        .and_then(|m| m["content"].as_str())
                        .unwrap_or("")
                        .chars()
                        .take(50)
                        .collect::<String>();

                    sessions.push(SessionSummary {
                        id: data["id"].as_str().unwrap_or("").to_string(),
                        level: level.to_string(),
                        started,
                        message_count: messages,
                        preview,
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

            let level = data["level"].as_str().unwrap_or("A0.1").to_string();
            let started = data["started"].as_str().unwrap_or("").replace("T", " ");

            {
                let mut state = APP_STATE.write();
                state.chat_history = messages.clone();
                state.current_level = level.clone();
            }

            let app_clone = app.clone();
            let msg_count = messages.len();
            slint::invoke_from_event_loop(move || {
                if let Some(window) = app_clone.upgrade() {
                    clear_messages_ui(&window);

                    let header_msg = ChatMessage {
                        role: "assistant".to_string(),
                        content: format!("📂 Restored session from {} (Level: {}, {} messages)", started, level, msg_count),
                        timestamp: current_timestamp(),
                        emotion: Some("NORMAL".to_string()),
                    };

                    // Build all messages at once
                    let mut all_messages: Vec<MessageData> = Vec::new();
                    all_messages.push(MessageData {
                        role: SharedString::from(&header_msg.role),
                        content: SharedString::from(&header_msg.content),
                    });
                    for m in &messages {
                        all_messages.push(MessageData {
                            role: SharedString::from(&m.role),
                            content: SharedString::from(&m.content),
                        });
                    }
                    let model = ModelRc::new(VecModel::from(all_messages));
                    window.set_messages(model);

                    window.set_status_text(SharedString::from(format!("📂 Session loaded ({} messages)", msg_count)));
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
    let state = APP_STATE.read();

    if state.chat_history.is_empty() {
        return;
    }

    let now = chrono::Local::now();
    let session_id = now.format("%Y%m%d_%H%M%S").to_string();

    let session_data = serde_json::json!({
        "id": session_id,
        "level": state.current_level,
        "started": now.to_rfc3339(),
        "updated": now.to_rfc3339(),
        "messages": state.chat_history.iter().map(|m| {
            serde_json::json!({
                "role": m.role,
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

fn load_config_string(key: &str) -> Option<String> {
    let config_path = get_data_dir().join("config.json");

    if let Ok(content) = fs::read_to_string(&config_path) {
        if let Ok(data) = serde_json::from_str::<serde_json::Value>(&content) {
            return data[key].as_str().map(String::from);
        }
    }

    None
}