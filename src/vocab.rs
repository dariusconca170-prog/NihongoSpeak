// Vocabulary tracker module

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VocabEntry {
    pub word: String,
    pub reading: String,
    pub meaning: String,
    pub level: i32,
    pub struggles: i32,
    pub last_seen: String,
    pub next_review: String,
    pub added: String,
}

// SRS intervals: day 1, 3, 7, 14, 30
pub const SRS_INTERVALS: &[i32] = &[1, 3, 7, 14, 30];
