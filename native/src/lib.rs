use serde_json::{json, Value};
use std::{
    io::Read,
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub fn validate_args(args: &[String]) -> bool {
    if args.len() < 2
        || args.len() > 128
        || !matches!(args[0].as_str(), "cli" | "browser")
        || args.iter().any(|a| a.len() > 4096 || a.contains('\0'))
    {
        return false;
    }
    if args[0] == "browser" {
        return true;
    }
    match args[1].as_str() {
        "status" | "describe" | "capabilities" | "health" => args.len() == 2,
        "access" => args.len() == 3 && args[2] == "list",
        "window" | "screen" | "mouse" | "keyboard" | "ocr" | "browser" => args.len() >= 3,
        _ => false,
    }
}
fn helper_args(args: &[String]) -> Vec<String> {
    if args.first().map(String::as_str) == Some("browser") {
        std::iter::once("cli".to_string())
            .chain(args.iter().cloned())
            .collect()
    } else {
        args.to_vec()
    }
}
fn cli_path() -> Result<PathBuf, String> {
    let mut paths = Vec::new();
    if let Some(p) = std::env::var_os("SCREEN_AUTOMATION_HELPER_EXE") {
        paths.push(PathBuf::from(p));
    }
    if let Some(p) = std::env::var_os("LOCALAPPDATA") {
        paths.push(
            PathBuf::from(p)
                .join("Programs/Xiaozs/ScreenAutomationHelper/ScreenAutomationHelper.exe"),
        );
    }
    paths
        .into_iter()
        .find(|p| p.is_absolute() && p.is_file())
        .ok_or("未找到已安装的小助手".into())
}
pub fn execute_cli(args: &[String]) -> Result<Value, String> {
    if !validate_args(args) {
        return Err("CLI 操作超出已启用范围".into());
    }
    let mut cmd = Command::new(cli_path()?);
    cmd.args(helper_args(args))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let mut child = cmd.spawn().map_err(|_| "小助手启动失败")?;
    let stdout = child.stdout.take().ok_or("输出不可用")?;
    let stderr = child.stderr.take().ok_or("输出不可用")?;
    let read = |stream: Box<dyn Read + Send>| {
        std::thread::spawn(move || {
            let mut bytes = Vec::new();
            stream
                .take(1024 * 1024 + 1)
                .read_to_end(&mut bytes)
                .map(|_| bytes)
        })
    };
    let out = read(Box::new(stdout));
    let err = read(Box::new(stderr));
    let deadline = Instant::now() + Duration::from_secs(60);
    let status = loop {
        match child.try_wait() {
            Ok(Some(s)) => break s,
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(25)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("小助手调用超时".into());
            }
        }
    };
    let out = out
        .join()
        .map_err(|_| "输出读取失败")?
        .map_err(|_| "输出读取失败")?;
    let err = err
        .join()
        .map_err(|_| "输出读取失败")?
        .map_err(|_| "输出读取失败")?;
    if out.len() > 1024 * 1024 || err.len() > 1024 * 1024 {
        return Err("CLI 输出过大".into());
    }
    let stdout = String::from_utf8(out).map_err(|_| "输出编码无效")?;
    let mut result = json!({"ok":true,"exit_code":status.code().unwrap_or(1),"stdout":stdout,"stderr":String::from_utf8_lossy(&err)});
    if args.get(1).map(String::as_str) == Some("screen")
        && args.get(2).map(String::as_str) == Some("capture")
    {
        if let Ok(value) = serde_json::from_str::<Value>(&stdout) {
            if value.get("ok") == Some(&Value::Bool(true)) {
                let path = value
                    .get("path")
                    .and_then(Value::as_str)
                    .ok_or("截图路径缺失")?;
                if std::fs::metadata(path).map_err(|_| "截图读取失败")?.len() > 4 * 1024 * 1024
                {
                    return Err("截图过大".into());
                }
                let data = std::fs::read(path).map_err(|_| "截图读取失败")?;
                if !data.starts_with(b"\x89PNG\r\n\x1a\n") {
                    return Err("截图格式无效".into());
                }
                use base64::Engine;
                result["artifact"] = json!({"media_type":"image/png","data":base64::engine::general_purpose::STANDARD.encode(data)});
            }
        }
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_pd_cli_families_are_allowed() {
        for args in [
            vec!["cli", "status"],
            vec!["cli", "browser", "status"],
            vec!["browser", "status"],
            vec!["browser", "open", "chrome", "--url", "https://example.test"],
            vec!["cli", "browser", "navigate", "https://example.test"],
            vec!["cli", "window", "list-visible"],
            vec!["cli", "mouse", "click", "--x", "10"],
        ] {
            assert!(validate_args(
                &args.into_iter().map(String::from).collect::<Vec<_>>()
            ));
        }
        for args in [
            vec!["powershell", "run"],
            vec!["cli", "workflow", "run"],
            vec!["cli", "access", "activate"],
            vec!["cli", "bad\0arg"],
        ] {
            assert!(!validate_args(
                &args.into_iter().map(String::from).collect::<Vec<_>>()
            ));
        }
    }
    #[test]
    fn browser_shorthand_uses_the_desktop_cli_entry_once() {
        let args: Vec<String> = ["browser", "status"]
            .into_iter()
            .map(String::from)
            .collect();
        let expected: Vec<String> = ["cli", "browser", "status"]
            .into_iter()
            .map(String::from)
            .collect();
        assert_eq!(helper_args(&args), expected);
        assert_eq!(helper_args(&expected), expected);
    }
    #[test]
    fn shell_metacharacters_stay_single_cli_arguments() {
        assert!(validate_args(
            &["cli", "keyboard", "type", "a; echo injected"]
                .into_iter()
                .map(String::from)
                .collect::<Vec<_>>()
        ));
    }
}
