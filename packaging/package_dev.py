"""Build development archives, deliberately not a signed component release."""
from pathlib import Path
import hashlib
import json
import zipfile
root=Path(__file__).resolve().parents[1]
out=root/"build"
out.mkdir(exist_ok=True)
groups={
 "pd-device-bridge-windows-x64-dev.zip":{
  "pd-device-bridge.exe":root/"native/target/release/pd-device-bridge.exe",
  "component.json":root/"component.json",
  "README.md":root/"README.md"},
 "pd-chat-bridge-server-dev.zip":{
  "pd_chat_bridge.py":root/"server/pd_chat_bridge.py",
  "pd_cli_proxy.py":root/"server/pd_cli_proxy.py",
  "install_server.py":root/"install_server.py",
  "update_bridge.py":root/"update_bridge.py",
  "上传安装说明.md":root/"上传安装说明.md",
  "packaging/patch_octop.py":root/"packaging/patch_octop.py",
  "README.md":root/"README.md"}}
for path in (out/"server-patch").glob("*"):
 groups["pd-chat-bridge-server-dev.zip"]["reference-patch/"+path.name]=path
manifest={}
for name,files in groups.items():
 target=out/name
 with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as archive:
  for relative,path in files.items(): archive.write(path,relative)
 with zipfile.ZipFile(target) as archive: assert archive.testzip() is None
 manifest[name]=hashlib.sha256(target.read_bytes()).hexdigest()
(out/"dev-artifacts.sha256.json").write_text(json.dumps(manifest,indent=2)+"\n")
print("Created two verified development archives; not deployed.")
