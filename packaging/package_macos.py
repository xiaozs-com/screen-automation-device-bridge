"""Package a Mac-built executable; development artifact, not signed publication."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
platform = sys.argv[1] if len(sys.argv) == 2 else ""
targets = {"macos-x64": "x86_64-apple-darwin", "macos-arm64": "aarch64-apple-darwin"}
if platform not in targets:
    raise SystemExit("Usage: python3 packaging/package_macos.py macos-x64|macos-arm64")
binary = root / "native/target" / targets[platform] / "release/pd-device-bridge"
if not binary.is_file():
    raise SystemExit("Build the requested Mac target first")
if binary.read_bytes()[:4] not in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
    raise SystemExit("Expected a 64-bit Mach-O executable")
manifest = json.loads((root / "component.json").read_text())
manifest.update(version="0.2.0", entry="pd-device-bridge", supported_runtime_platforms=[platform])
out = root / "build" / ("pd-device-bridge-" + platform + "-dev.zip")
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    entry = zipfile.ZipInfo("pd-device-bridge")
    entry.create_system = 3
    entry.external_attr = (0o100755 << 16)
    entry.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(entry, binary.read_bytes())
    archive.writestr("component.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    for name in ("README.md", "MACOS_TESTING.md", "FULL_CLI_USAGE.md", "LICENSE"):
        archive.write(root / name, name)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
    assert archive.getinfo("pd-device-bridge").external_attr >> 16 == 0o100755
out.with_suffix(".sha256").write_text(hashlib.sha256(out.read_bytes()).hexdigest() + "  " + out.name + "\n")
print(out)
