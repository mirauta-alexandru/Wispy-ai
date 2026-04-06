use crossterm::{
    event::{self, Event, KeyCode},
    terminal,
};
use futures_util::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::fs::{self, File};
use std::io::{stdout, Write};
use std::path::PathBuf;
use std::process::{self, Command};
use std::os::unix::fs::PermissionsExt;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const MODEL_URL: &str = "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf";
const MODEL_NAME: &str = "qwen2.5-coder-0.5b.gguf";
const SERVER_ZIP_NAME: &str = "llama-server.zip";

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
const LLAMA_SERVER_URL: &str = "https://github.com/ggml-org/llama.cpp/releases/download/b4900/llama-b4900-bin-macos-arm64.zip";

#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
const LLAMA_SERVER_URL: &str = "https://github.com/ggml-org/llama.cpp/releases/download/b4900/llama-b4900-bin-ubuntu-x64.zip";

#[cfg(all(target_os = "linux", target_arch = "aarch64"))]
const LLAMA_SERVER_URL: &str = "https://github.com/ggml-org/llama.cpp/releases/download/b4900/llama-b4900-bin-ubuntu-arm64.zip";

// ── Settings ───────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone)]
struct Settings {
    auto_start: bool,
    inactivity_timeout_mins: u32, // 0 = never
}

impl Default for Settings {
    fn default() -> Self {
        Settings { auto_start: true, inactivity_timeout_mins: 5 }
    }
}

impl Settings {
    fn path() -> PathBuf {
        let home = env::var("HOME").unwrap_or_default();
        PathBuf::from(home).join(".wispy-ai").join("settings.json")
    }
    fn load() -> Self {
        fs::read_to_string(Self::path())
            .ok()
            .and_then(|d| serde_json::from_str(&d).ok())
            .unwrap_or_default()
    }
    fn save(&self) {
        if let Ok(data) = serde_json::to_string_pretty(self) {
            let _ = fs::write(Self::path(), data);
        }
    }
}

// ── Memory ─────────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone)]
struct MemoryEntry {
    completion: String,
    count: u32,
    last_used: u64,
    cwd: String,
}

#[derive(Serialize, Deserialize)]
struct Memory {
    version: u32,
    entries: HashMap<String, MemoryEntry>,
}

impl Memory {
    fn new() -> Self {
        Memory { version: 1, entries: HashMap::new() }
    }

    fn path() -> PathBuf {
        let home = env::var("HOME").unwrap_or_default();
        PathBuf::from(home).join(".wispy-ai").join("memory.json")
    }

    fn load() -> Self {
        let path = Self::path();
        if let Ok(data) = fs::read_to_string(&path) {
            serde_json::from_str(&data).unwrap_or_else(|_| Self::new())
        } else {
            Self::new()
        }
    }

    fn save(&self) {
        if let Ok(data) = serde_json::to_string_pretty(self) {
            let _ = fs::write(Self::path(), data);
        }
    }

    fn learn(&mut self, input: &str, completion: &str, cwd: &str) {
        // don't save if input looks like a typo of something we already know
        let input_first = input.split_whitespace().next().unwrap_or("");
        let is_typo = self.entries.iter().any(|(k, v)| {
            if k == input { return false; }
            let key_first = k.split_whitespace().next().unwrap_or("");
            let dist = levenshtein(input_first, key_first);
            let threshold = if input_first.len() <= 3 { 1 } else { 2 };
            dist > 0 && dist <= threshold && v.count > 1
        });
        if is_typo { return; }

        let now = now_secs();
        let entry = self.entries.entry(input.to_string()).or_insert(MemoryEntry {
            completion: completion.to_string(),
            count: 0,
            last_used: now,
            cwd: cwd.to_string(),
        });
        entry.completion = completion.to_string();
        entry.count += 1;
        entry.last_used = now;
        entry.cwd = cwd.to_string();
    }

    fn cleanup_typos(&mut self) -> usize {
        let keys: Vec<String> = self.entries.keys().cloned().collect();
        let mut to_remove = Vec::new();

        for key in &keys {
            let key_first = key.split_whitespace().next().unwrap_or("");
            let key_count = self.entries[key].count;
            let is_typo = keys.iter().any(|other| {
                if other == key { return false; }
                let other_first = other.split_whitespace().next().unwrap_or("");
                let dist = levenshtein(key_first, other_first);
                let threshold = if key_first.len() <= 3 { 1 } else { 2 };
                dist > 0 && dist <= threshold && self.entries[other].count > key_count
            });
            if is_typo {
                to_remove.push(key.clone());
            }
        }

        let n = to_remove.len();
        for key in to_remove {
            self.entries.remove(&key);
        }
        n
    }

    fn get_exact(&self, input: &str) -> Option<&MemoryEntry> {
        self.entries.get(input)
    }

    fn get_fuzzy_match(&self, input: &str, cwd: &str) -> Option<(String, String)> {
        if input.len() < 3 { return None; }
        let now = now_secs();

        let typed_words: Vec<&str> = input.split_whitespace().collect();
        let typed_first = typed_words.first().copied().unwrap_or("");

        let best = self.entries.iter()
            .filter(|(_, v)| v.count >= 2)
            .filter_map(|(k, v)| {
                let key_words: Vec<&str> = k.split_whitespace().collect();
                let key_first = key_words.first().copied().unwrap_or("");

                let dist = levenshtein(typed_first, key_first);
                let threshold = if typed_first.len() <= 3 { 1 } else { 2 };
                if dist == 0 || dist > threshold { return None; }

                if typed_words.len() > 1 {
                    let typed_rest = typed_words[1..].join(" ");
                    let key_rest   = key_words[1..].join(" ");
                    if !key_rest.starts_with(&typed_rest) { return None; }
                }

                let days_ago  = (now.saturating_sub(v.last_used)) as f64 / 86400.0;
                let recency   = 1.0 / (1.0 + days_ago);
                let cwd_bonus = if v.cwd == cwd { 2.0 } else { 1.0 };
                let score     = v.count as f64 * cwd_bonus * recency / (dist as f64 + 1.0);

                Some((score, k, v))
            })
            .max_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

        best.map(|(_, k, v)| {
            let ghost      = v.completion.clone();
            let correction = format!("{}{}", k, v.completion);
            (ghost, correction)
        })
    }

    // find best memory entry that starts with what the user typed
    // e.g. buffer="gi", key="git sta", completion="tus" → returns "t status"
    fn get_prefix_expansion(&self, input: &str, cwd: &str) -> Option<String> {
        if input.is_empty() {
            return None;
        }
        let now = now_secs();
        let best = self.entries.iter()
            .filter(|(k, v)| k.starts_with(input) && k.as_str() != input && v.count >= 2)
            .map(|(k, v)| {
                let days_ago = (now.saturating_sub(v.last_used)) as f64 / 86400.0;
                let recency  = 1.0 / (1.0 + days_ago);
                let cwd_bonus = if v.cwd == cwd { 2.0 } else { 1.0 };
                let score = v.count as f64 * cwd_bonus * recency;
                (score, k, v)
            })
            .max_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

        best.map(|(_, k, v)| format!("{}{}", &k[input.len()..], v.completion))
    }

    fn get_related(&self, input: &str, cwd: &str, limit: usize) -> Vec<(&String, &MemoryEntry)> {
        let first_word = input.split_whitespace().next().unwrap_or("");
        let now = now_secs();

        let mut scored: Vec<(f64, &String, &MemoryEntry)> = self.entries.iter()
            .filter(|(k, _)| {
                k.as_str() != input &&
                k.split_whitespace().next().unwrap_or("") == first_word
            })
            .map(|(k, v)| {
                let days_ago = (now.saturating_sub(v.last_used)) as f64 / 86400.0;
                let recency  = 1.0 / (1.0 + days_ago);
                let cwd_bonus = if v.cwd == cwd { 2.0 } else { 1.0 };
                let score = v.count as f64 * cwd_bonus * recency;
                (score, k, v)
            })
            .collect();

        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        scored.into_iter().take(limit).map(|(_, k, v)| (k, v)).collect()
    }
}

fn stopped_flag_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".wispy-ai").join(".stopped")
}

fn last_used_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".wispy-ai").join(".last_used")
}

fn watchdog_pid_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".wispy-ai").join(".watchdog.pid")
}

fn model_config_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".wispy-ai").join("model")
}

fn active_model_name() -> String {
    fs::read_to_string(model_config_path())
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| MODEL_NAME.to_string())
}

fn wispy_models_dir() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".wispy-ai").join("models")
}

fn legacy_models_dir() -> PathBuf {
    let home = env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".ai-autocomplete").join("models")
}

fn list_models() {
    let active = active_model_name();
    let dirs = [wispy_models_dir(), legacy_models_dir()];
    let mut found = false;

    for dir in &dirs {
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.ends_with(".gguf") {
                    let marker = if name == active { " <- active" } else { "" };
                    println!("  {}{}", name, marker);
                    found = true;
                }
            }
        }
    }

    if !found {
        println!("No .gguf models found.");
        println!("Place a GGUF file in ~/.wispy-ai/models/ then run: wispy model set <name.gguf>");
    }
}

fn import_history(memory: &mut Memory) -> usize {
    let home = env::var("HOME").unwrap_or_default();
    let hist_path = PathBuf::from(&home).join(".zsh_history");

    let content = match fs::read_to_string(&hist_path) {
        Ok(c) => c,
        Err(_) => { eprintln!("~/.zsh_history not found"); return 0; }
    };

    let mut count = 0;
    for line in content.lines() {
        // zsh history has two formats:
        // plain:     "git status"
        // extended:  ": 1620000000:0;git status"
        let cmd = if line.starts_with(": ") && line.contains(';') {
            line.splitn(2, ';').nth(1).unwrap_or("").trim()
        } else {
            line.trim()
        };

        if cmd.len() < 3 || cmd.starts_with('#') {
            continue;
        }

        let words: Vec<&str> = cmd.split_whitespace().collect();
        if words.is_empty() { continue; }

        // learn multiple prefixes from each command
        // "git status --short" → ("git", " status --short") and ("git status", " --short")
        for i in 1..words.len() {
            let input      = words[..i].join(" ");
            let completion = format!(" {}", words[i..].join(" "));
            memory.learn(&input, &completion, "");
        }

        count += 1;
    }
    count
}

fn watchdog_already_running() -> bool {
    let pid_path = watchdog_pid_path();
    if let Ok(pid_str) = fs::read_to_string(&pid_path) {
        let pid = pid_str.trim().to_string();
        Command::new("kill")
            .args(["-0", &pid])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    } else {
        false
    }
}

fn now_secs() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
}

// Damerau-Levenshtein — counts transpositions so "gti" → "git" is distance 1
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let (m, n) = (a.len(), b.len());
    if m == 0 { return n; }
    if n == 0 { return m; }

    let mut dp = vec![vec![0usize; n + 1]; m + 1];
    for i in 0..=m { dp[i][0] = i; }
    for j in 0..=n { dp[0][j] = j; }

    for i in 1..=m {
        for j in 1..=n {
            let cost = if a[i-1] == b[j-1] { 0 } else { 1 };
            dp[i][j] = (dp[i-1][j] + 1)
                .min(dp[i][j-1] + 1)
                .min(dp[i-1][j-1] + cost);
            if i > 1 && j > 1 && a[i-1] == b[j-2] && a[i-2] == b[j-1] {
                dp[i][j] = dp[i][j].min(dp[i-2][j-2] + 1);
            }
        }
    }
    dp[m][n]
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().collect();

    match args.get(1).map(|s| s.as_str()) {
        Some("--settings") => {
            run_settings_tui();
        }
        Some("--auto-start-check") => {
            let s = Settings::load();
            process::exit(if s.auto_start { 0 } else { 1 });
        }
        Some("--daemon") => {
            let _ = fs::remove_file(stopped_flag_path());
            run_daemon().await;
        }
        Some("--watchdog") => {
            run_watchdog().await;
        }
        Some("--stop") => {
            let flag = stopped_flag_path();
            let _ = fs::write(&flag, "");

            // lsof may return multiple PIDs, kill each one
            if let Ok(out) = Command::new("lsof").args(["-ti", ":11435"]).output() {
                let pids = String::from_utf8_lossy(&out.stdout);
                for pid in pids.split_whitespace() {
                    Command::new("kill").args(["-9", pid]).status().ok();
                }
            }
            println!("Wispy stopped.");
        }
        Some("--status") => {
            let running = std::net::TcpStream::connect_timeout(
                &"127.0.0.1:11435".parse().unwrap(),
                std::time::Duration::from_millis(300),
            ).is_ok();
            println!("{}", if running { "running" } else { "stopped" });
        }
        Some("--cleanup") => {
            let mut memory = Memory::load();
            let removed = memory.cleanup_typos();
            memory.save();
            if removed > 0 {
                eprintln!("Removed {} typo entries from memory.", removed);
            }
        }
        Some("--learn") => {
            if args.len() >= 4 {
                let mut memory = Memory::load();
                memory.learn(
                    &args[2],
                    &args[3],
                    args.get(4).map(|s| s.as_str()).unwrap_or(""),
                );
                memory.save();
            }
        }
        Some("--model-list") => {
            println!("Available models:");
            list_models();
        }
        Some("--model-current") => {
            println!("{}", active_model_name());
        }
        Some("--model-set") => {
            if let Some(name) = args.get(2) {
                let found = wispy_models_dir().join(name).exists()
                    || legacy_models_dir().join(name).exists();
                if !found {
                    eprintln!("Model '{}' not found. Run: wispy model list", name);
                    process::exit(1);
                }
                let _ = fs::write(model_config_path(), name);
                println!("Active model: {}", name);
                println!("Restart wispy: wispy stop && wispy start");
            } else {
                eprintln!("Usage: wispy model set <name.gguf>");
            }
        }
        Some("--memory-stats") => {
            let memory = Memory::load();
            let total = memory.entries.len();
            println!("Commands in memory: {}", total);

            if total == 0 { return; }

            let mut sorted: Vec<_> = memory.entries.iter().collect();
            sorted.sort_by(|a, b| b.1.count.cmp(&a.1.count));

            println!("\nTop 10 most used:");
            for (i, (key, entry)) in sorted.iter().take(10).enumerate() {
                println!("  {}. {}{} (x{})", i + 1, key, entry.completion, entry.count);
            }
        }
        Some("--memory-clear") => {
            let empty = Memory::new();
            empty.save();
            println!("Memory cleared.");
        }
        Some("--memory-forget") => {
            if let Some(cmd) = args.get(2) {
                let mut memory = Memory::load();
                if memory.entries.remove(cmd.as_str()).is_some() {
                    memory.save();
                    println!("Removed from memory: {}", cmd);
                } else {
                    println!("Not found in memory: {}", cmd);
                }
            } else {
                eprintln!("Usage: wispy memory forget <command>");
            }
        }
        // memory-only lookup, no AI — used by fish right-prompt for instant suggestions
        Some("--fast") => {
            if stopped_flag_path().exists() { return; }
            let input = match args.get(2) { Some(s) => s.as_str(), None => return };
            let cwd   = args.get(3).map(|s| s.as_str()).unwrap_or("");
            let memory = Memory::load();
            if let Some(entry) = memory.get_exact(input) {
                if entry.count >= 3 { print!("{}", entry.completion); return; }
            }
            if let Some(exp) = memory.get_prefix_expansion(input, cwd) {
                print!("{}", exp);
            }
        }
        Some("--import-history") => {
            let mut memory = Memory::load();
            let n = import_history(&mut memory);
            memory.save();
            println!("Imported {} commands from ~/.zsh_history.", n);
        }
        Some(input) if !input.starts_with("--") => {
            let cwd    = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let recent = args.get(3).map(|s| s.as_str()).unwrap_or("");
            ask_ai(input, cwd, recent).await;
        }
        _ => {}
    }
}

async fn run_daemon() {
    let client = Client::new();

    if let Err(e) = download_file(&client, MODEL_URL, MODEL_NAME, "AI model (0.5B)", "models").await {
        eprintln!("Model download failed: {}", e);
        process::exit(1);
    }

    if let Err(e) = download_server(&client).await {
        eprintln!("Engine download failed: {}", e);
        process::exit(1);
    }

    start_ai_server();

    if !watchdog_already_running() {
        if let Ok(current_exe) = env::current_exe() {
            Command::new(&current_exe)
                .arg("--watchdog")
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn()
                .ok();
        }
    }
}

async fn download_file(
    client: &Client,
    url: &str,
    file_name: &str,
    desc: &str,
    folder: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let home = env::var("HOME").unwrap();
    let dir = PathBuf::from(home).join(".ai-autocomplete").join(folder);
    fs::create_dir_all(&dir)?;
    let path = dir.join(file_name);
    if path.exists() {
        return Ok(());
    }
    println!("Downloading {}...", desc);
    let res = client.get(url).send().await?;
    let total_size = res.content_length().unwrap_or(0);
    let mut file = File::create(&path)?;
    let mut downloaded: u64 = 0;
    let mut stream = res.bytes_stream();
    while let Some(item) = stream.next().await {
        let chunk = item?;
        file.write_all(&chunk)?;
        downloaded += chunk.len() as u64;
        if total_size > 0 {
            let percent = (downloaded as f64 / total_size as f64) * 100.0;
            print!("\r{:.1}%", percent);
            std::io::stdout().flush()?;
        }
    }
    println!("\n{} done.", desc);
    Ok(())
}

async fn download_server(client: &Client) -> Result<(), Box<dyn std::error::Error>> {
    let home = env::var("HOME").unwrap();
    let dir = PathBuf::from(home).join(".ai-autocomplete").join("bin");
    let server_path = dir.join("build").join("bin").join("llama-server");
    if server_path.exists() {
        return Ok(());
    }
    download_file(client, LLAMA_SERVER_URL, SERVER_ZIP_NAME, "llama.cpp engine", "bin").await?;
    println!("Extracting engine...");
    let zip_path = dir.join(SERVER_ZIP_NAME);
    let status = Command::new("unzip")
        .args(["-o", zip_path.to_str().unwrap(), "-d", dir.to_str().unwrap()])
        .status()?;
    if status.success() {
        let mut perms = fs::metadata(&server_path)?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&server_path, perms)?;
        let _ = fs::remove_file(zip_path);
        Ok(())
    } else {
        Err("Failed to extract llama-server".into())
    }
}

fn start_ai_server() {
    let home = env::var("HOME").unwrap();
    let base_dir = PathBuf::from(&home).join(".ai-autocomplete");
    let server_path = base_dir.join("bin").join("build").join("bin").join("llama-server");

    let active = active_model_name();
    let candidates = [
        wispy_models_dir().join(&active),
        legacy_models_dir().join(&active),
        legacy_models_dir().join(MODEL_NAME),
    ];
    let model_path = match candidates.iter().find(|p| p.exists()) {
        Some(p) => p.clone(),
        None => {
            eprintln!("No model found. Run: wispy model list");
            return;
        }
    };

    if reqwest::blocking::Client::new()
        .get("http://127.0.0.1:11435/health")
        .send()
        .is_ok()
    {
        return;
    }

    let log_file = File::create(base_dir.join("server.log")).unwrap();
    Command::new(&server_path)
        .args([
            "-m", model_path.to_str().unwrap(),
            "--port", "11435",
            "-c", "2048",
            "--parallel", "1",
        ])
        .stdout(std::process::Stdio::from(log_file.try_clone().unwrap()))
        .stderr(std::process::Stdio::from(log_file))
        .spawn()
        .expect("Failed to start llama-server");
}

async fn run_watchdog() {
    let timeout_mins = Settings::load().inactivity_timeout_mins;
    let inactivity_limit: u64 = if timeout_mins == 0 { u64::MAX } else { timeout_mins as u64 * 60 };
    const CHECK_INTERVAL: u64 = 30;

    let pid = std::process::id();
    let _ = fs::write(watchdog_pid_path(), pid.to_string());

    loop {
        tokio::time::sleep(Duration::from_secs(CHECK_INTERVAL)).await;

        if std::net::TcpStream::connect_timeout(
            &"127.0.0.1:11435".parse().unwrap(),
            Duration::from_millis(200),
        ).is_err() {
            break;
        }

        let inactive_secs = fs::metadata(last_used_path())
            .and_then(|m| m.modified())
            .map(|t| t.elapsed().unwrap_or_default().as_secs())
            .unwrap_or(inactivity_limit.saturating_add(1));

        if inactive_secs > inactivity_limit {
            // stop without setting the .stopped flag so it auto-restarts on next keystroke
            let out = Command::new("lsof").args(["-ti", ":11435"]).output();
            if let Ok(out) = out {
                let pid_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !pid_str.is_empty() {
                    Command::new("kill").arg(&pid_str).status().ok();
                }
            }
            break;
        }
    }

    let _ = fs::remove_file(watchdog_pid_path());
}

fn list_model_files() -> Vec<String> {
    let mut models = Vec::new();
    for dir in &[wispy_models_dir(), legacy_models_dir()] {
        if let Ok(entries) = fs::read_dir(dir) {
            for e in entries.flatten() {
                let name = e.file_name().to_string_lossy().to_string();
                if name.ends_with(".gguf") && !models.contains(&name) {
                    models.push(name);
                }
            }
        }
    }
    models.sort();
    models
}

fn render_settings(
    settings: &Settings,
    models: &[String],
    model: &str,
    cursor_row: usize,
    timeout_opts: &[u32],
    timeout_labels: &[&str],
) -> String {
    let n_models = models.len();
    let row_auto = n_models;
    let row_time = n_models + 1;
    let row_save = n_models + 2;
    let row_quit = n_models + 3;

    let dim   = |s: &str| format!("\x1b[2m{}\x1b[0m", s);
    let bold  = |s: &str| format!("\x1b[1m{}\x1b[0m", s);
    let green = |s: &str| format!("\x1b[32m{}\x1b[0m", s);
    let rev   = |s: &str| format!("\x1b[7m {} \x1b[0m", s);
    let hi    = |s: &str, active: bool| -> String {
        if active { rev(s) } else { s.to_string() }
    };

    let mut out = String::new();
    out.push_str(&format!("\r\n  {}\r\n", bold("Wispy Settings")));
    out.push_str(&format!("  {}\r\n\r\n", dim("─────────────────────────────────────")));

    // Model
    out.push_str(&format!("  {}\r\n", bold("MODEL")));
    if models.is_empty() {
        out.push_str(&format!("  {}\r\n", dim("No models found in ~/.wispy-ai/models/")));
    }
    for (i, m) in models.iter().enumerate() {
        let active  = m == model;
        let bullet  = if active { green("●") } else { dim("○") };
        let label   = if active { format!("{}  {}", m, dim("← active")) } else { m.clone() };
        out.push_str(&format!("  {} {}\r\n", bullet, hi(&label, cursor_row == i)));
    }
    out.push_str("\r\n");

    // Auto-start
    out.push_str(&format!("  {}\r\n", bold("AUTO-START")));
    let opts_auto = [("On shell load", true), ("Manual  (wispy start / wispy stop)", false)];
    for (i, (label, val)) in opts_auto.iter().enumerate() {
        let sel    = settings.auto_start == *val;
        let bullet = if sel { green("●") } else { dim("○") };
        out.push_str(&format!("  {} {}\r\n", bullet, hi(label, cursor_row == row_auto + i)));
    }
    out.push_str("\r\n");

    // Timeout
    out.push_str(&format!("  {}\r\n  ", bold("INACTIVITY TIMEOUT")));
    for (i, (&val, label)) in timeout_opts.iter().zip(timeout_labels.iter()).enumerate() {
        let sel    = settings.inactivity_timeout_mins == val;
        let bullet = if sel { green("●") } else { dim("○") };
        out.push_str(&format!("{} {}  ", bullet, hi(label, cursor_row == row_time + i)));
    }
    out.push_str("\r\n\r\n");

    // Actions
    out.push_str(&format!("  {}\r\n", dim("─────────────────────────────────────")));
    out.push_str(&format!("  {}    {}\r\n\r\n",
        green(&hi("Save & exit", cursor_row == row_save)),
        dim(&hi("Quit", cursor_row == row_quit)),
    ));
    out.push_str(&format!("  {}\r\n",
        dim("↑↓ navigate · Enter/Space select · S save · Q quit")));

    out
}

fn run_settings_tui() {
    let mut settings   = Settings::load();
    let mut model      = active_model_name();
    let models         = list_model_files();
    let timeout_opts   = [5u32, 10, 15, 30, 0];
    let timeout_labels = ["5 min", "10 min", "15 min", "30 min", "Never"];

    let n_models  = models.len();
    let row_auto  = n_models;
    let row_time  = n_models + 1;
    let row_save  = n_models + 2;
    let row_quit  = n_models + 3;
    let max_row   = row_quit;

    let mut cursor_row  = models.iter().position(|m| m == &model).unwrap_or(0);
    let mut lines_drawn = 0usize;

    if terminal::enable_raw_mode().is_err() {
        eprintln!("wispy: terminal does not support interactive mode");
        return;
    }
    // Hide cursor for cleaner look
    print!("\x1b[?25l");
    let _ = stdout().flush();

    'outer: loop {
        // Move cursor up to overwrite previous render
        if lines_drawn > 0 {
            print!("\x1b[{}A\x1b[J", lines_drawn);
        }

        let out = render_settings(
            &settings, &models, &model, cursor_row,
            &timeout_opts, &timeout_labels,
        );
        lines_drawn = out.chars().filter(|&c| c == '\n').count();
        print!("{}", out);
        let _ = stdout().flush();

        match event::read() {
            Ok(Event::Key(key)) => match key.code {
                KeyCode::Up => {
                    if cursor_row > 0 { cursor_row -= 1; }
                }
                KeyCode::Down => {
                    if cursor_row < max_row { cursor_row += 1; }
                }
                KeyCode::Enter | KeyCode::Char(' ') => {
                    if cursor_row < n_models {
                        model = models[cursor_row].clone();
                    } else if cursor_row == row_auto {
                        settings.auto_start = true;
                    } else if cursor_row == row_auto + 1 {
                        settings.auto_start = false;
                    } else if cursor_row >= row_time && cursor_row < row_save {
                        settings.inactivity_timeout_mins = timeout_opts[cursor_row - row_time];
                    } else if cursor_row == row_save {
                        settings.save();
                        let _ = fs::write(model_config_path(), &model);
                        break 'outer;
                    } else if cursor_row == row_quit {
                        break 'outer;
                    }
                }
                KeyCode::Left => {
                    if cursor_row > row_time && cursor_row < row_save {
                        cursor_row -= 1;
                    }
                }
                KeyCode::Right => {
                    if cursor_row >= row_time && cursor_row < row_save - 1 {
                        cursor_row += 1;
                    }
                }
                KeyCode::Char('s') | KeyCode::Char('S') => {
                    settings.save();
                    let _ = fs::write(model_config_path(), &model);
                    break 'outer;
                }
                KeyCode::Char('q') | KeyCode::Char('Q') | KeyCode::Esc => {
                    break 'outer;
                }
                _ => {}
            },
            _ => {}
        }
    }

    // Clear menu, restore cursor
    if lines_drawn > 0 {
        print!("\x1b[{}A\x1b[J", lines_drawn);
    }
    print!("\x1b[?25h");
    let _ = stdout().flush();
    let _ = terminal::disable_raw_mode();
}

fn is_thinking_model(name: &str) -> bool {
    let n = name.to_lowercase();
    n.contains("qwen3") || n.contains("qwen35") || n.contains("qwq")
}

fn build_raw_prompt(system: &str, user: &str, no_think: bool) -> String {
    let think_prefix = if no_think { "<think>\n\n</think>\n\n" } else { "" };
    format!(
        "<|im_start|>system\n{}<|im_end|>\n<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n{}",
        system, user, think_prefix
    )
}

async fn ask_ai(buffer: &str, cwd: &str, recent: &str) {
    if stopped_flag_path().exists() {
        return;
    }

    let _ = fs::write(last_used_path(), "");

    // if server was stopped by the watchdog, restart it automatically
    let server_up = std::net::TcpStream::connect_timeout(
        &"127.0.0.1:11435".parse().unwrap(),
        Duration::from_millis(200),
    ).is_ok();
    if !server_up {
        if let Ok(current_exe) = env::current_exe() {
            Command::new(&current_exe)
                .arg("--daemon")
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn()
                .ok();
        }
        return;
    }

    let memory = Memory::load();

    // exact match with high confidence → instant reply, no AI needed
    if let Some(entry) = memory.get_exact(buffer) {
        if entry.count >= 3 {
            print!("{}", entry.completion);
            return;
        }
    }

    if let Some(expansion) = memory.get_prefix_expansion(buffer, cwd) {
        print!("{}", expansion);
        return;
    }

    if let Some((ghost, correction)) = memory.get_fuzzy_match(buffer, cwd) {
        // two lines: ghost text for display, corrected command for accept
        print!("{}\n{}", ghost, correction);
        return;
    }

    let exact_hint = memory.get_exact(buffer);
    let related    = memory.get_related(buffer, cwd, 5);

    let mut system = String::from(
        "You are a zsh shell autocomplete. \
         Given a partial command, output the single most likely completed command on one line. \
         Rules:\n\
         - Output the FULL completed command, not just the suffix\n\
         - If the input is already a complete command, repeat it as-is\n\
         - Use short, realistic arguments (flags, filenames, hostnames)\n\
         - No explanation, no markdown, no extra lines"
    );

    if !related.is_empty() || exact_hint.is_some() {
        system.push_str("\n\nThis user's command history (use as hints):");
        for (input, e) in &related {
            system.push_str(&format!("\n  {}{}", input, e.completion));
        }
        if let Some(e) = exact_hint {
            system.push_str(&format!("\n  {}{}", buffer, e.completion));
        }
    }

    if !cwd.is_empty()    { system.push_str(&format!("\nCurrent directory: {}", cwd)); }
    if !recent.is_empty() { system.push_str(&format!("\nRecent commands: {}", recent.replace('|', ", "))); }

    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(1500))
        .build()
        .unwrap();

    let active_model = active_model_name();
    let thinking = is_thinking_model(&active_model);

    let content = if thinking {
        let prompt = build_raw_prompt(&system, buffer, true);
        let body = serde_json::json!({
            "prompt": prompt,
            "n_predict": 30,
            "temperature": 0.0,
            "stop": ["\n", "<|im_end|>"]
        });
        if let Ok(response) = client
            .post("http://127.0.0.1:11435/completion")
            .json(&body)
            .send()
            .await
        {
            response.json::<serde_json::Value>().await
                .ok()
                .and_then(|j| j["content"].as_str().map(|s| s.to_string()))
        } else {
            None
        }
    } else {
        let body = serde_json::json!({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": buffer}
            ],
            "max_tokens": 20,
            "temperature": 0.0,
            "stop": ["\n", "```"]
        });
        if let Ok(response) = client
            .post("http://127.0.0.1:11435/v1/chat/completions")
            .json(&body)
            .send()
            .await
        {
            response.json::<serde_json::Value>().await
                .ok()
                .and_then(|j| j["choices"][0]["message"]["content"].as_str().map(|s| s.to_string()))
        } else {
            None
        }
    };

    if let Some(content) = content {
        let cleaned = clean_completion(&content, buffer);
        let suffix = if cleaned.starts_with(buffer) {
            cleaned[buffer.len()..].to_string()
        } else {
            cleaned
        };
        if !suffix.is_empty() {
            print!("{}", suffix);
        }
    }
}

fn clean_completion(completion: &str, buffer: &str) -> String {
    let mut c = completion.trim().to_string();

    if c.starts_with('`') { c = c.trim_matches('`').to_string(); }
    if c.starts_with('"') && !buffer.ends_with('"') { c = c.trim_matches('"').to_string(); }
    if c.starts_with(' ') && !buffer.ends_with(' ') { c = c.trim_start().to_string(); }

    if c.starts_with(buffer) {
        return c[buffer.len()..].to_string();
    }

    // buffer ends with a space — model returned command without trailing space
    // e.g. buffer="docker run ", model returns "docker run --rm" → we want "--rm"
    let buffer_trimmed = buffer.trim_end();
    if buffer_trimmed != buffer && c.starts_with(buffer_trimmed) {
        return c[buffer_trimmed.len()..].trim_start().to_string();
    }

    if let Some(last_word) = buffer.split_whitespace().last() {
        if !buffer.ends_with(' ') {
            if c.starts_with(last_word) {
                return c[last_word.len()..].to_string();
            }
            for i in (1..=last_word.len()).rev() {
                let suffix = &last_word[last_word.len() - i..];
                if c.starts_with(suffix) {
                    return c[i..].to_string();
                }
            }
        }
    }

    c
}
