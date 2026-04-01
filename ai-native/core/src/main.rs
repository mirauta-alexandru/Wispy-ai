use futures_util::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::fs::{self, File};
use std::io::Write;
use std::path::PathBuf;
use std::process::{self, Command};
use std::os::unix::fs::PermissionsExt;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const MODEL_URL: &str = "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf";
const MODEL_NAME: &str = "qwen2.5-coder-0.5b.gguf";
const LLAMA_SERVER_URL: &str = "https://github.com/ggerganov/llama.cpp/releases/download/b4900/llama-b4900-bin-macos-arm64.zip";
const SERVER_ZIP_NAME: &str = "llama-server.zip";

// ---------------------------------------------------------------------------
// Sistemul de memorie
// ---------------------------------------------------------------------------

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
        // Nu salvam daca inputul e un typo al unei comenzi existente cu count mai mare
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

    // Sterge intrarile care sunt typo-uri ale unor comenzi cu count mai mare
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

    // Fuzzy match pentru typo-uri.
    // Returneaza (ghost_text, full_corrected_command) sau None.
    // Ex: buffer="gti sta", key="git sta", completion="tus"
    //     → ghost="tus", correction="git status"
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

                // Distanta Levenshtein pe primul cuvant
                let dist = levenshtein(typed_first, key_first);
                let threshold = if typed_first.len() <= 3 { 1 } else { 2 };
                if dist == 0 || dist > threshold { return None; }

                // Restul cuvintelor trebuie sa se potriveasca (prefix)
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

    // Cauta cea mai buna intrare din memorie care incepe cu ce a tastat userul.
    // Returneaza (sufixul_cheii + completarea) ca un string gata de afisat.
    // Ex: buffer="gi", cheie="git sta", completion="tus" → "t status"
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

    // Cele mai relevante intrari cu acelasi prim cuvant, sortate dupa scor
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

fn watchdog_already_running() -> bool {
    let pid_path = watchdog_pid_path();
    if let Ok(pid_str) = fs::read_to_string(&pid_path) {
        let pid = pid_str.trim().to_string();
        // Verificam daca procesul cu acel PID exista inca
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

// Damerau-Levenshtein: conteaza si transpunerile (gti→git = 1, nu 2)
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
            // Transpunere: ab → ba
            if i > 1 && j > 1 && a[i-1] == b[j-2] && a[i-2] == b[j-1] {
                dp[i][j] = dp[i][j].min(dp[i-2][j-2] + 1);
            }
        }
    }
    dp[m][n]
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().collect();

    match args.get(1).map(|s| s.as_str()) {
        Some("--daemon") => {
            let _ = fs::remove_file(stopped_flag_path());
            run_daemon().await;
        }
        Some("--watchdog") => {
            run_watchdog().await;
        }
        Some("--stop") => {
            // Cream flagul de oprit — binaryul nu mai returneaza sugestii
            let flag = stopped_flag_path();
            let _ = fs::write(&flag, "");

            // Oprim llama-server — lsof poate returna mai multe PID-uri
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
                eprintln!("Curatate {} intrari typo din memorie.", removed);
            }
        }
        Some("--learn") => {
            // --learn <input> <completion> <cwd>
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
        Some(input) if !input.starts_with("--") => {
            let cwd    = args.get(2).map(|s| s.as_str()).unwrap_or("");
            let recent = args.get(3).map(|s| s.as_str()).unwrap_or("");
            ask_ai(input, cwd, recent).await;
        }
        _ => {}
    }
}

// ---------------------------------------------------------------------------
// Daemon: descarca modelul + serverul, porneste llama-server
// ---------------------------------------------------------------------------

async fn run_daemon() {
    let client = Client::new();

    if let Err(e) = download_file(&client, MODEL_URL, MODEL_NAME, "Model AI (0.5B)", "models").await {
        eprintln!("Eroare model: {}", e);
        process::exit(1);
    }

    if let Err(e) = download_server(&client).await {
        eprintln!("Eroare motor AI: {}", e);
        process::exit(1);
    }

    start_ai_server();

    // Pornim watchdog-ul daca nu e deja unul activ
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
    println!("Descarc {}...", desc);
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
            print!("\rProgres: {:.1}%", percent);
            std::io::stdout().flush()?;
        }
    }
    println!("\n{} descarcat!", desc);
    Ok(())
}

async fn download_server(client: &Client) -> Result<(), Box<dyn std::error::Error>> {
    let home = env::var("HOME").unwrap();
    let dir = PathBuf::from(home).join(".ai-autocomplete").join("bin");
    let server_path = dir.join("build").join("bin").join("llama-server");
    if server_path.exists() {
        return Ok(());
    }
    download_file(client, LLAMA_SERVER_URL, SERVER_ZIP_NAME, "Motor AI Llama", "bin").await?;
    println!("Extrag motorul AI...");
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
        Err("Eroare la dezarhivarea llama-server".into())
    }
}

fn start_ai_server() {
    let home = env::var("HOME").unwrap();
    let base_dir = PathBuf::from(&home).join(".ai-autocomplete");
    let server_path = base_dir.join("bin").join("build").join("bin").join("llama-server");

    // Fallback la modelul 1.5B daca 0.5B nu e inca descarcat
    let model_05 = base_dir.join("models").join(MODEL_NAME);
    let model_15 = base_dir.join("models").join("qwen2.5-coder-1.5b.gguf");
    let model_path = if model_05.exists() {
        model_05
    } else if model_15.exists() {
        model_15
    } else {
        eprintln!("Niciun model gasit!");
        return;
    };

    // Daca serverul e deja pornit, iesim
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
        .expect("Eroare la pornirea motorului AI");
}

// ---------------------------------------------------------------------------
// Completare cu memorie + context
// ---------------------------------------------------------------------------

async fn run_watchdog() {
    const INACTIVITY_LIMIT: u64 = 5 * 60; // 5 minute
    const CHECK_INTERVAL:   u64 = 30;      // verifica la fiecare 30 secunde

    // Salvam PID-ul nostru
    let pid = std::process::id();
    let _ = fs::write(watchdog_pid_path(), pid.to_string());

    loop {
        tokio::time::sleep(Duration::from_secs(CHECK_INTERVAL)).await;

        // Daca serverul nu mai e pornit, iesim
        if std::net::TcpStream::connect_timeout(
            &"127.0.0.1:11435".parse().unwrap(),
            Duration::from_millis(200),
        ).is_err() {
            break;
        }

        // Calculam inactivitatea din fisierul last_used
        let inactive_secs = fs::metadata(last_used_path())
            .and_then(|m| m.modified())
            .map(|t| t.elapsed().unwrap_or_default().as_secs())
            .unwrap_or(INACTIVITY_LIMIT + 1);

        if inactive_secs > INACTIVITY_LIMIT {
            // Oprim serverul (fara flagul .stopped — se va reporni automat)
            let out = Command::new("lsof")
                .args(["-ti", ":11435"])
                .output();
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

async fn ask_ai(buffer: &str, cwd: &str, recent: &str) {
    // Daca wispy e oprit manual, nu returnam nimic
    if stopped_flag_path().exists() {
        return;
    }

    // Actualizam timestamp-ul de activitate
    let _ = fs::write(last_used_path(), "");

    // Daca serverul a fost oprit de watchdog (inactivitate), il reporniram automat
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
        return; // server-ul porneste, nu avem sugestie pentru acest keystroke
    }

    let memory = Memory::load();

    // Match exact cu incredere mare → raspuns instant, fara AI
    if let Some(entry) = memory.get_exact(buffer) {
        if entry.count >= 3 {
            print!("{}", entry.completion);
            return;
        }
    }

    // Prefix expansion din memorie: "gi" → "t status" (din "git sta → tus")
    if let Some(expansion) = memory.get_prefix_expansion(buffer, cwd) {
        print!("{}", expansion);
        return;
    }

    // Fuzzy match pentru typo-uri: "gti sta" → ghost="tus", correction="git status"
    if let Some((ghost, correction)) = memory.get_fuzzy_match(buffer, cwd) {
        // Doua linii: ghost text pentru display, comanda corecta pentru accept
        print!("{}\n{}", ghost, correction);
        return;
    }

    // Construim contextul din memorie
    let exact_hint = memory.get_exact(buffer);
    let related    = memory.get_related(buffer, cwd, 5);

    let mut examples = String::new();
    if let Some(e) = exact_hint {
        examples.push_str(&format!("- `{}` -> `{}`\n", buffer, e.completion));
    }
    for (input, e) in &related {
        examples.push_str(&format!("- `{}` -> `{}`\n", input, e.completion));
    }

    // System prompt cu toleranta la typo-uri
    let mut system = String::from(
        "You are a terminal autocomplete AI. \
         The user may have made minor typos — silently correct and complete. \
         Output ONLY the raw command text that completes the user's input. \
         Do not explain. Do not use quotes or markdown. Output at most one line."
    );

    // Adaugam patternurile userului ca exemple
    if !examples.is_empty() {
        system.push_str("\n\nUser's command patterns (use as hints):");
        for (input, e) in &related {
            system.push_str(&format!("\n  {} -> {}", input, e.completion));
        }
        if let Some(e) = exact_hint {
            system.push_str(&format!("\n  {} -> {}", buffer, e.completion));
        }
    }

    if !cwd.is_empty()    { system.push_str(&format!("\nCurrent directory: {}", cwd)); }
    if !recent.is_empty() { system.push_str(&format!("\nRecent commands: {}", recent.replace('|', ", "))); }

    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(1500))
        .build()
        .unwrap();

    let body = serde_json::json!({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": format!("Complete: {}", buffer)}
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
        if let Ok(json) = response.json::<serde_json::Value>().await {
            if let Some(content) = json["choices"][0]["message"]["content"].as_str() {
                let cleaned = clean_completion(content, buffer);
                // Modelul poate returna comanda completa sau doar sufixul
                // Daca incepe cu buffer-ul, extragem sufixul
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
    }
}

fn clean_completion(completion: &str, buffer: &str) -> String {
    let mut c = completion.trim().to_string();

    if c.starts_with('`') { c = c.trim_matches('`').to_string(); }
    if c.starts_with('"') && !buffer.ends_with('"') { c = c.trim_matches('"').to_string(); }
    if c.starts_with(' ') && !buffer.ends_with(' ') { c = c.trim_start().to_string(); }

    // AI a repetat toata comanda
    if c.starts_with(buffer) {
        return c[buffer.len()..].to_string();
    }

    // AI a repetat ultimul cuvant
    if let Some(last_word) = buffer.split_whitespace().last() {
        if !buffer.ends_with(' ') {
            if c.starts_with(last_word) {
                return c[last_word.len()..].to_string();
            }
            // Suprapunere partiala (ex: user='dock', AI='cker ps')
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
