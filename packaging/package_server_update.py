"""Package only audited server update files; no keys, runtime data or catalogs."""
import hashlib,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files={"pd_chat_bridge.py":root/"server/pd_chat_bridge.py","pd_cli_proxy.py":root/"server/pd_cli_proxy.py","update_bridge.py":root/"update_bridge.py","SERVER_UPGRADE.md":root/"SERVER_UPGRADE.md","FULL_CLI_USAGE.md":root/"FULL_CLI_USAGE.md","LICENSE":root/"LICENSE"}
for name,path in files.items():
 if not path.is_file():raise FileNotFoundError(path)
 if name.endswith(".py"):compile(path.read_text(encoding="utf-8"),str(path),"exec")
out=root/"build/pd-chat-bridge-server-full-cli-0.2.3.zip"
if out.exists():raise FileExistsError("Server update artifact already exists; do not overwrite")
out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
 for name,path in files.items():archive.write(path,name)
with zipfile.ZipFile(out) as archive:
 assert archive.testzip() is None
 assert set(archive.namelist())==set(files)
report={"path":str(out.resolve()),"size":out.stat().st_size,"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"files":list(files),"uploaded":False}
out.with_suffix(".json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2))
