"""Update only independent bridge modules; leave Octop ws.py and ports unchanged."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
from pathlib import Path
import shutil
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--apply",action="store_true")
 args=parser.parse_args()
 spec=importlib.util.find_spec("octop")
 if spec is None or not spec.submodule_search_locations:parser.error("请使用 Octop 的 venv/bin/python 执行")
 package=Path(next(iter(spec.submodule_search_locations))).resolve()
 ws=package/"api/routers/chat/ws.py"
 if not ws.is_file() or "PD_CHAT_BRIDGE_PATCH" not in ws.read_text(encoding="utf-8"):
  parser.error("未检测到已安装桥接，请先核对原安装")
 bundle=Path(__file__).resolve().parent
 pairs=[(bundle/name,package.parent/name) for name in ("pd_chat_bridge.py","pd_cli_proxy.py")]
 for source,target in pairs:
  if not source.is_file() or not target.is_file():parser.error("桥接模块缺失，请先核对安装")
  compile(source.read_text(encoding="utf-8"),str(source),"exec")
  print(str(target)+" -> SHA256 "+hashlib.sha256(source.read_bytes()).hexdigest())
 if not args.apply:
  print("仅预览，未修改。停止 Octop 后添加 --apply 更新。");return
 record=bundle/"install-records"/("modules-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
 record.mkdir(parents=True)
 for source,target in pairs:shutil.copy2(target,record/target.name)
 try:
  for source,target in pairs:shutil.copy2(source,target)
 except OSError:
  for source,target in pairs:shutil.copy2(record/target.name,target)
  raise
 (record/"rollback.txt").write_text("\n".join(str(record/target.name)+" -> "+str(target) for source,target in pairs)+"\n恢复前停止 Octop，恢复后按原方式启动。\n",encoding="utf-8")
 print("两个桥接模块已更新，备份："+str(record))
 print("未改 ws.py、端口和服务配置；请按原方式重启 Octop，再从宠物发起新聊天。")
if __name__=="__main__":main()
