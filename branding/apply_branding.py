"""Preview/apply a small, reversible Octop dashboard branding overlay."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
INDEX = "index.html"
MARKER = "<!-- PALDEE_BRANDING_BOOT_V1 -->"


def replace_once(text, old, new):
    if text.count(new) == 1 and old not in text:
        return text
    if text.count(old) != 1:
        raise ValueError(f"上游结构不同，停止：{old[:90]}")
    return text.replace(old, new, 1)


def branded_index(text):
    if MARKER in text:
        return text
    # Derive paths from this installed HTML, preserving root/subpath deployment.
    prefixes = set(re.findall(r'src=["\']([^"\']*)logo_vertical_(?:dark|white)\.svg["\']', text))
    if len(prefixes) != 1:
        raise ValueError("无法确认现有首屏素材路径，停止；未修改")
    prefix = prefixes.pop()
    # Keep the existing JS/CSS bundle URLs and all boot/recovery scripts.
    old = '        <div id="octop-boot-mark" aria-hidden="true">'
    start = text.find(old)
    end = text.find('        <div id="octop-boot-text">', start)
    if start < 0 or end < 0 or text.count(old) != 1:
        raise ValueError("无法识别 Octop 首屏结构，未修改")
    replacement = '''        <!-- PALDEE_BRANDING_BOOT_V1 -->
        <div id="octop-boot-mark" aria-hidden="true">
          <div id="octop-boot-ring"></div>
          <picture>
            <source
              media="(prefers-reduced-motion: reduce)"
              srcset="%BASE_URL%octop-mascot-empty.png"
            />
            <img
              class="paldee-boot-mascot"
              src="%BASE_URL%paldee-boot.webp"
              alt=""
              width="176"
              height="176"
            />
          </picture>
        </div>
'''
    replacement = replacement.replace("%BASE_URL%", prefix)
    text = text[:start] + replacement + text[end:]
    style = '''    <style id="paldee-boot-style">
      #octop-boot-mark {
        width: 176px;
        height: 176px;
      }
      #octop-boot-ring {
        inset: 12px;
        border-color: rgba(13, 148, 136, 0.16);
        border-top-color: #0d9488;
      }
      html[data-theme="dark"] #octop-boot-ring {
        border-color: rgba(45, 212, 191, 0.2);
        border-top-color: #2dd4bf;
      }
      .paldee-boot-mascot {
        position: relative;
        display: block;
        width: 176px;
        height: 176px;
        object-fit: contain;
      }
    </style>
'''
    return replace_once(text, "  </head>", style + "  </head>")


def plan(source):
    manifest = json.loads((HERE / "assets-manifest.json").read_text(encoding="utf-8"))
    changes = []
    target = source / INDEX
    before = target.read_bytes()
    after = branded_index(before.decode("utf-8").replace("\r\n", "\n")).encode("utf-8")
    if before != after:
        changes.append((INDEX, before, after))
    for item in manifest["assets"]:
        if item["file"] not in manifest["deployFiles"]:
            continue
        asset = HERE / "assets" / item["file"]
        data = asset.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"素材指纹不符：{asset}")
        relative = item["file"]
        target = source / relative
        before = target.read_bytes() if target.exists() else None
        if before != data:
            changes.append((relative, before, data))
    return changes


def rollback(source, record):
    record = record.resolve()
    record.relative_to((source / ".paldee-branding-backups").resolve())
    entries = json.loads((record / "record.json").read_text(encoding="utf-8"))
    # Validate the full record before restoring anything.
    for item in entries:
        relative = Path(item["path"])
        target = (source / relative).resolve()
        target.relative_to(source)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != item["afterSha256"]:
            raise ValueError(f"文件在应用后改变，停止回退：{target}")
        if item["existed"]:
            backup = (record / relative).resolve()
            backup.relative_to(record)
            if hashlib.sha256(backup.read_bytes()).hexdigest() != item["beforeSha256"]:
                raise ValueError(f"备份指纹不符：{backup}")
    for item in entries:
        target = source / item["path"]
        if item["existed"]:
            shutil.copy2(record / item["path"], target)
        else:
            target.unlink()
    print("静态文件已回退；请刷新网页缓存。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard", type=Path, required=True, help="服务器实际使用的静态网页目录，内含 index.html")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    source = args.dashboard.resolve()
    if args.rollback:
        rollback(source, args.rollback)
        return
    changes = plan(source)
    for relative, _, _ in changes:
        print(relative)
    print(f"检查通过：{len(changes)} 个文件待更新。")
    if not args.apply or not changes:
        return
    record = source / ".paldee-branding-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record.mkdir(parents=True)
    entries = []
    for relative, before, after in changes:
        if before is not None:
            backup = record / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, backup)
        entries.append({"path": relative, "existed": before is not None,
                        "beforeSha256": hashlib.sha256(before).hexdigest() if before is not None else None,
                        "afterSha256": hashlib.sha256(after).hexdigest()})
    (record / "record.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    written = []
    try:
        for relative, before, after in changes:
            target = source / relative
            current = target.read_bytes() if target.exists() else None
            if current != before:
                raise ValueError(f"文件在预览后改变：{target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            written.append((target, before))
            target.write_bytes(after)
    except Exception:
        for target, before in reversed(written):
            if before is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(before)
        raise
    print(f"静态外观已更新，备份：{record}；请刷新网页缓存。")


if __name__ == "__main__":
    main()
