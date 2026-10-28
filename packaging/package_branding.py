"""Package only the no-build static branding overlay."""
import hashlib
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-name", default="paldee-octop-branding-v1.0.3b1-static.zip")
    args = parser.parse_args()
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith(".zip"):
        parser.error("output-name 必须是 ZIP 文件名，不包含目录")
    branding = ROOT / "branding"
    manifest = json.loads((branding / "assets-manifest.json").read_text(encoding="utf-8"))
    files = [("branding/" + name, branding / name) for name in (
        "apply_branding.py", "assets-manifest.json", "README.md", "DEPLOY.md", "VALIDATION.md")]
    for item in manifest["assets"]:
        if item["file"] not in manifest["deployFiles"]:
            continue
        asset = branding / "assets" / item["file"]
        if hashlib.sha256(asset.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("素材指纹不符：" + item["file"])
        files.append(("branding/assets/" + item["file"], asset))
    out = ROOT / "build" / args.output_name
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, source in files:
            archive.write(source, relative)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        assert not any(name.endswith((".js", ".css", ".ts", ".tsx", ".html")) for name in archive.namelist())
    report = {"file": out.name, "bytes": out.stat().st_size,
              "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
              "compiled": False, "deployed": False,
              "affectedFiles": ["index.html", *manifest["deployFiles"]]}
    out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
