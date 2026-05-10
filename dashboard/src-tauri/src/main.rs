#![cfg_attr(
  all(not(debug_assertions), target_os = "windows"),
  windows_subsystem = "windows"
)]

use tauri::api::process::{Command, CommandEvent};
use tauri::Manager;

fn main() {
  tauri::Builder::default()
    .setup(|app| {
      let window = app.get_window("main").unwrap();
      
      // Start the Python sidecar (FastAPI daemon)
      // The sidecar binary name must match the one in tauri.conf.json
      let (mut rx, _child) = Command::new_sidecar("selfheal-daemon")
        .expect("failed to setup sidecar")
        .spawn()
        .expect("failed to spawn sidecar");

      tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
          if let CommandEvent::Stdout(line) = event {
            window
              .emit("daemon-log", line)
              .expect("failed to emit event");
          }
        }
      });

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
