#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let execution = if args == ["--request-json"] {
        use std::io::Read;
        let mut bytes = Vec::new();
        std::io::stdin()
            .take(8 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "桥接输入不可读".to_string())
            .and_then(|_| {
                if bytes.len() > 8 * 1024 * 1024 {
                    return Err("桥接输入超过 8 MiB".into());
                }
                let value: serde_json::Value =
                    serde_json::from_slice(&bytes).map_err(|_| "桥接输入 JSON 无效")?;
                let args = value["args"]
                    .as_array()
                    .ok_or("CLI 参数无效")?
                    .iter()
                    .map(|arg| {
                        arg.as_str()
                            .map(String::from)
                            .ok_or("CLI 参数无效".to_string())
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                pd_device_bridge::execute_request(&args, value.get("input"))
            })
    } else {
        pd_device_bridge::execute_cli(&args)
    };
    let result = execution.unwrap_or_else(|error| serde_json::json!({"ok":false,"error":error}));
    println!("{result}");
    if result.get("ok") != Some(&serde_json::Value::Bool(true)) {
        std::process::exit(1);
    }
}
