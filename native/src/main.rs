#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = pd_device_bridge::execute_cli(&args)
        .unwrap_or_else(|error| serde_json::json!({"ok":false,"error":error}));
    println!("{result}");
    if result.get("ok") != Some(&serde_json::Value::Bool(true)) {
        std::process::exit(1);
    }
}
