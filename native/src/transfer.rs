use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

const MAX_BYTES: usize = 4 * 1024 * 1024;
const MAX_FILES: usize = 128;

pub struct Transfer {
    pub args: Vec<String>,
    pub stdin: Option<String>,
    downloads: Vec<PathBuf>,
    scratch: Option<PathBuf>,
    persistent: bool,
    uploaded: Vec<Value>,
}

fn relative(value: &str) -> Result<PathBuf, String> {
    if value.is_empty()
        || value.contains(['\\', ':', '\0'])
        || value
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err("传输文件相对路径无效".into());
    }
    Ok(PathBuf::from(value))
}

fn default_data_dir() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        std::env::var_os("HOME").map(|home| macos_data_dir(std::path::Path::new(&home)))
    }
    #[cfg(not(target_os = "macos"))]
    {
        std::env::var_os("APPDATA")
            .map(|path| PathBuf::from(path).join("com.octop.pet"))
            .or_else(|| Some(std::env::temp_dir()))
    }
}
#[cfg(any(target_os = "macos", test))]
fn macos_data_dir(home: &Path) -> PathBuf {
    home.join("Library/Application Support/com.octop.pet")
}

impl Transfer {
    pub fn prepare(args: &[String], input: Option<&Value>) -> Result<Self, String> {
        let mut transfer = Self {
            args: args.to_vec(),
            stdin: None,
            downloads: Vec::new(),
            scratch: None,
            persistent: false,
            uploaded: Vec::new(),
        };
        let Some(input) = input.filter(|value| !value.is_null()) else {
            return Ok(transfer);
        };
        if !input.is_object() {
            return Err("CLI 输入格式无效".into());
        }
        if let Some(value) = input.get("stdin") {
            let text = value.as_str().ok_or("标准输入必须是 UTF-8 文字")?;
            if text.len() > 1024 * 1024 {
                return Err("标准输入超过 1 MiB".into());
            }
            transfer.stdin = Some(text.to_owned());
        }
        if let Some(downloads) = input.get("downloads") {
            let paths = downloads.as_array().ok_or("取回文件列表无效")?;
            if paths.len() > MAX_FILES {
                return Err("取回文件数量过多".into());
            }
            for value in paths {
                let value = value.as_str().ok_or("取回文件路径无效")?;
                if value.is_empty() || value.len() > 4096 || value.contains('\0') {
                    return Err("取回文件路径无效".into());
                }
                let path = PathBuf::from(value);
                if !path.is_absolute() {
                    return Err("取回文件请使用本机绝对路径".into());
                }
                transfer.downloads.push(path);
            }
        }
        if let Some(uploads) = input.get("uploads") {
            let uploads = uploads.as_array().ok_or("上传文件列表无效")?;
            if uploads.len() > MAX_FILES {
                return Err("上传文件数量过多".into());
            }
            if !uploads.is_empty() {
                let nonce = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map_err(|_| "时间无效")?
                    .as_nanos();
                let base = std::env::var_os("OCTOPPET_DATA_DIR")
                    .map(PathBuf::from)
                    .or_else(default_data_dir)
                    .ok_or("无法确定传输用户目录；请设置 OCTOPPET_DATA_DIR 绝对路径")?;
                if !base.is_absolute() {
                    return Err("传输用户目录必须是绝对路径".into());
                }
                let root = base.join("bridge-transfers");
                fs::create_dir_all(&root).map_err(|_| "传输用户目录创建失败")?;
                let path = root.join(format!("paldee-cli-{}-{nonce}", std::process::id()));
                fs::create_dir(&path).map_err(|_| "传输临时目录创建失败")?;
                transfer.scratch = Some(path);
            }
            let mut bytes = 0;
            let mut count = 0;
            let mut indexes = std::collections::HashSet::new();
            for (number, upload) in uploads.iter().enumerate() {
                let index = upload["arg_index"].as_u64().ok_or("上传参数位置无效")? as usize;
                if index == 0 || index >= args.len() || !indexes.insert(index) {
                    return Err("上传参数位置无效或重复".into());
                }
                let name = upload["name"].as_str().ok_or("上传文件名称无效")?;
                let name_path = relative(name)?;
                if name_path.components().count() != 1 {
                    return Err("上传名称必须是单个文件名".into());
                }
                let kind = upload["kind"].as_str().ok_or("上传类型无效")?;
                let files = upload["files"].as_array().ok_or("上传内容无效")?;
                if !matches!(kind, "file" | "directory") || (kind == "file" && files.len() != 1) {
                    return Err("上传类型或内容无效".into());
                }
                let folder = transfer
                    .scratch
                    .as_ref()
                    .ok_or("传输目录缺失")?
                    .join(number.to_string());
                fs::create_dir(&folder).map_err(|_| "传输目录创建失败")?;
                let destination = folder.join(name_path);
                if kind == "directory" {
                    fs::create_dir(&destination).map_err(|_| "传输目录创建失败")?;
                }
                for file in files {
                    count += 1;
                    if count > MAX_FILES {
                        return Err("一次传输最多 128 个文件".into());
                    }
                    let path = relative(file["path"].as_str().ok_or("上传文件路径无效")?)?;
                    let data = file["data"].as_str().ok_or("上传文件内容无效")?;
                    if data.len() > 6 * 1024 * 1024 {
                        return Err("一次文件传输超过 4 MiB".into());
                    }
                    let data = STANDARD.decode(data).map_err(|_| "上传文件编码无效")?;
                    bytes += data.len();
                    if bytes > MAX_BYTES {
                        return Err("一次文件传输超过 4 MiB".into());
                    }
                    let target = if kind == "file" {
                        destination.clone()
                    } else {
                        destination.join(path)
                    };
                    if let Some(parent) = target.parent() {
                        fs::create_dir_all(parent).map_err(|_| "传输目录创建失败")?;
                    }
                    use std::io::Write;
                    let mut output = fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(&target)
                        .map_err(|_| "传输文件写入失败或路径重复")?;
                    output.write_all(&data).map_err(|_| "传输文件写入失败")?;
                }
                let prefix = upload.get("prefix").and_then(Value::as_str).unwrap_or("");
                if !prefix.is_empty()
                    && (!prefix.starts_with("--")
                        || !prefix.ends_with('=')
                        || !args[index].starts_with(prefix))
                {
                    return Err("上传参数前缀无效".into());
                }
                transfer.args[index] = format!("{prefix}{}", destination.display());
                transfer
                    .uploaded
                    .push(json!({"arg_index":index,"path":destination.to_string_lossy()}));
            }
        }
        Ok(transfer)
    }

    pub fn keep_uploads(&mut self) -> Vec<Value> {
        self.persistent = true;
        self.uploaded.clone()
    }

    pub fn collect(&self) -> Result<Vec<Value>, String> {
        let mut result = Vec::new();
        let mut bytes = 0;
        let mut count = 0;
        for path in &self.downloads {
            let metadata = fs::symlink_metadata(path).map_err(|_| "本机取回文件不存在或不可读")?;
            if metadata.file_type().is_symlink() {
                return Err("取回文件不能是符号链接".into());
            }
            let name = path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("files");
            let mut files = Vec::new();
            if metadata.is_dir() {
                collect_directory(path, path, &mut files, &mut bytes, &mut count, 0)?;
            } else {
                files.push(collect_file(path, name, &mut bytes, &mut count)?);
            }
            result.push(json!({"source":path.to_string_lossy(),"name":name,"kind":if metadata.is_dir(){"directory"}else{"file"},"files":files}));
        }
        Ok(result)
    }
}

fn collect_file(
    path: &Path,
    name: &str,
    bytes: &mut usize,
    count: &mut usize,
) -> Result<Value, String> {
    *count += 1;
    let metadata = fs::symlink_metadata(path).map_err(|_| "本机取回文件不可读")?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err("取回内容不是普通文件".into());
    }
    if *count > MAX_FILES
        || metadata.len() > MAX_BYTES as u64
        || *bytes + metadata.len() as usize > MAX_BYTES
    {
        return Err("一次取回最多 128 个文件、4 MiB".into());
    }
    let data = fs::read(path).map_err(|_| "本机取回文件不可读")?;
    *bytes += data.len();
    if *bytes > MAX_BYTES {
        return Err("取回文件超过 4 MiB".into());
    }
    Ok(json!({"path":name,"data":STANDARD.encode(data)}))
}

fn collect_directory(
    root: &Path,
    directory: &Path,
    files: &mut Vec<Value>,
    bytes: &mut usize,
    count: &mut usize,
    depth: usize,
) -> Result<(), String> {
    if depth > 32 {
        return Err("取回目录层级过深".into());
    }
    for entry in fs::read_dir(directory).map_err(|_| "本机取回目录不可读")? {
        let entry = entry.map_err(|_| "本机取回目录不可读")?;
        let path = entry.path();
        let kind = entry.file_type().map_err(|_| "本机取回文件不可读")?;
        if kind.is_symlink() {
            return Err("取回目录不能包含符号链接".into());
        }
        if kind.is_dir() {
            collect_directory(root, &path, files, bytes, count, depth + 1)?;
        } else {
            let name = path
                .strip_prefix(root)
                .map_err(|_| "取回路径无效")?
                .to_string_lossy()
                .replace('\\', "/");
            files.push(collect_file(&path, &name, bytes, count)?);
        }
    }
    Ok(())
}

impl Drop for Transfer {
    fn drop(&mut self) {
        if let Some(path) = &self.scratch {
            if !self.persistent
                && path
                    .parent()
                    .and_then(Path::file_name)
                    .is_some_and(|name| name == "bridge-transfers")
                && path
                    .file_name()
                    .is_some_and(|name| name.to_string_lossy().starts_with("paldee-cli-"))
            {
                let _ = fs::remove_dir_all(path);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn macos_transfers_use_persistent_application_support() {
        assert_eq!(
            macos_data_dir(Path::new("/Users/test user")),
            PathBuf::from("/Users/test user/Library/Application Support/com.octop.pet")
        );
    }
    #[test]
    fn upload_rewrites_argument_and_cleans_owned_scratch() {
        let input = json!({"stdin":"你好", "uploads":[{"arg_index":3,"name":"测试 流程","kind":"directory","files":[{"path":"flow.py","data":STANDARD.encode(b"source")}]}]});
        let args = ["cli", "workflow", "inspect", "remote/path"].map(String::from);
        let transfer = Transfer::prepare(&args, Some(&input)).unwrap();
        let path = PathBuf::from(&transfer.args[3]);
        assert_eq!(fs::read(path.join("flow.py")).unwrap(), b"source");
        assert_eq!(transfer.stdin.as_deref(), Some("你好"));
        drop(transfer);
        assert!(!path.exists());
    }
    #[test]
    fn traversal_and_duplicate_positions_are_rejected() {
        for name in ["../escape", "C:/escape", "/absolute", "a\\b", ""] {
            assert!(relative(name).is_err());
        }
        let input = json!({"uploads":[{"arg_index":0,"name":"x","kind":"file","files":[]}]});
        assert!(Transfer::prepare(&["cli".into()], Some(&input)).is_err());
    }
    #[test]
    fn collection_reads_actual_content() {
        let args = ["cli", "workflow", "inspect", "remote/path"].map(String::from);
        let input = json!({"uploads":[{"arg_index":3,"name":"x","kind":"file","files":[{"path":"x","data":STANDARD.encode(b"actual source")}]}]});
        let mut transfer = Transfer::prepare(&args, Some(&input)).unwrap();
        transfer.downloads.push(PathBuf::from(&transfer.args[3]));
        let files = transfer.collect().unwrap();
        assert_eq!(
            STANDARD
                .decode(files[0]["files"][0]["data"].as_str().unwrap())
                .unwrap(),
            b"actual source"
        );
    }
}
