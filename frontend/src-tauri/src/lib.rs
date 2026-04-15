use std::sync::Mutex;
use std::time::Duration;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, WindowEvent,
};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_store::Builder::new().build())
        .setup(|app| {
            // ── Sidecar launch ──────────────────────────────────────
            let already_running = std::net::TcpStream::connect_timeout(
                &"127.0.0.1:9721".parse().unwrap(),
                Duration::from_secs(1),
            )
            .is_ok();

            if !already_running {
                let sidecar_cmd = app
                    .shell()
                    .sidecar("neo-server")
                    .expect("failed to create sidecar command")
                    .args(["--host", "127.0.0.1", "--port", "9721"]);

                let (mut rx, child) = sidecar_cmd
                    .spawn()
                    .expect("failed to spawn neo-server sidecar");

                app.manage(Mutex::new(Some(child)));

                // Log sidecar output in background
                tauri::async_runtime::spawn(async move {
                    use tauri_plugin_shell::process::CommandEvent;
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(line) => {
                                let s = String::from_utf8_lossy(&line);
                                println!("[neo-server] {}", s);
                            }
                            CommandEvent::Stderr(line) => {
                                let s = String::from_utf8_lossy(&line);
                                eprintln!("[neo-server] {}", s);
                            }
                            CommandEvent::Terminated(payload) => {
                                eprintln!(
                                    "[neo-server] terminated with code: {:?}",
                                    payload.code
                                );
                                break;
                            }
                            _ => {}
                        }
                    }
                });
            } else {
                app.manage(Mutex::new(None::<CommandChild>));
                println!("[neo] Backend already running on port 9721");
            }

            // ── System tray ─────────────────────────────────────────
            let show_item = MenuItem::with_id(app, "show", "Open Neo", true, None::<&str>)?;
            let command_item =
                MenuItem::with_id(app, "command", "New Command", true, None::<&str>)?;
            let pause_item = MenuItem::with_id(
                app,
                "pause_automations",
                "Pause Automations",
                true,
                None::<&str>,
            )?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

            let menu =
                Menu::with_items(app, &[&show_item, &command_item, &pause_item, &quit_item])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .tooltip("Neo — Personal Intelligence Agent")
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "command" => {
                        if let Some(window) = app.get_webview_window("floating-bar") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "pause_automations" => {
                        let _ = app.emit("tray-pause-automations", ());
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Close button on main window → hide to tray instead of quitting
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Neo")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                // Kill sidecar on app exit
                let state = app_handle.state::<Mutex<Option<CommandChild>>>();
                if let Ok(mut guard) = state.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        println!("[neo] Sidecar process stopped");
                    }
                }
            }
        });
}
