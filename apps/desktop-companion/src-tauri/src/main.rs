use std::{collections::{HashMap, HashSet}, path::{Path, PathBuf}, process::Command, sync::Mutex};
use sha2::{Digest, Sha256};
use notify::{RecommendedWatcher, RecursiveMode, Watcher};
use tauri::Emitter;

struct LocalGrants { folders: Mutex<HashSet<PathBuf>>, proposals: Mutex<HashMap<String, String>>, watchers: Mutex<Vec<RecommendedWatcher>> }
impl Default for LocalGrants { fn default() -> Self { Self { folders: Mutex::new(HashSet::new()), proposals: Mutex::new(HashMap::new()), watchers: Mutex::new(Vec::new()) } } }

fn permitted(state: &LocalGrants, path: &Path) -> Result<PathBuf, String> {
    let canonical = path.canonicalize().map_err(|e| e.to_string())?;
    if state.folders.lock().unwrap().iter().any(|root| canonical.starts_with(root)) { Ok(canonical) } else { Err("Folder access has not been granted".into()) }
}

#[tauri::command]
fn grant_folder(path: String, state: tauri::State<LocalGrants>) -> Result<(), String> {
    let canonical = PathBuf::from(path).canonicalize().map_err(|e| e.to_string())?;
    if !canonical.is_dir() { return Err("Grant target must be a directory".into()); }
    state.folders.lock().unwrap().insert(canonical); Ok(())
}

#[tauri::command]
fn read_file(path: String, state: tauri::State<LocalGrants>) -> Result<String, String> {
    std::fs::read_to_string(permitted(&state, Path::new(&path))?).map_err(|e| e.to_string())
}

#[tauri::command]
fn write_file(path: String, content: String, state: tauri::State<LocalGrants>) -> Result<(), String> {
    let target = PathBuf::from(path); let parent = target.parent().ok_or("File has no parent")?;
    permitted(&state, parent)?; std::fs::write(target, content).map_err(|e| e.to_string())
}

#[tauri::command]
fn propose_terminal(command: String, state: tauri::State<LocalGrants>) -> Result<String, String> {
    if command.trim().is_empty() { return Err("Command is empty".into()); }
    let token = format!("{:x}", Sha256::digest(format!("{}:{:?}", command, std::time::SystemTime::now()).as_bytes()));
    state.proposals.lock().unwrap().insert(token.clone(), command); Ok(token)
}

#[tauri::command]
fn execute_terminal(token: String, state: tauri::State<LocalGrants>) -> Result<String, String> {
    let command = state.proposals.lock().unwrap().remove(&token).ok_or("Approval token is invalid or already used")?;
    #[cfg(target_os = "windows")] let output = Command::new("powershell").args(["-NoProfile", "-Command", &command]).output();
    #[cfg(not(target_os = "windows"))] let output = Command::new("sh").args(["-lc", &command]).output();
    let output = output.map_err(|e| e.to_string())?;
    Ok(format!("{}{}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr)))
}

#[tauri::command]
fn clipboard_write(text: String) -> Result<(), String> { arboard::Clipboard::new().and_then(|mut c| c.set_text(text)).map_err(|e| e.to_string()) }

#[tauri::command]
fn open_browser(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://localhost") || url.starts_with("http://127.0.0.1")) { return Err("Only HTTPS or local URLs are allowed".into()); }
    open::that(url).map_err(|e| e.to_string())
}

#[tauri::command]
fn watch_folder(path: String, app: tauri::AppHandle, state: tauri::State<LocalGrants>) -> Result<(), String> {
    let folder = permitted(&state, Path::new(&path))?;
    let mut watcher = notify::recommended_watcher(move |event: notify::Result<notify::Event>| {
        if let Ok(event) = event { let paths: Vec<String> = event.paths.iter().map(|p| p.display().to_string()).collect(); let _ = app.emit("folder-changed", paths); }
    }).map_err(|e| e.to_string())?;
    watcher.watch(&folder, RecursiveMode::Recursive).map_err(|e| e.to_string())?;
    state.watchers.lock().unwrap().push(watcher); Ok(())
}

fn main() {
    tauri::Builder::default().manage(LocalGrants::default()).invoke_handler(tauri::generate_handler![grant_folder, read_file, write_file, propose_terminal, execute_terminal, clipboard_write, open_browser, watch_folder]).run(tauri::generate_context!()).expect("failed to run Deep-Foundry Companion");
}
