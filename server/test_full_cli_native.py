"""Opt-in actual Windows/macOS bridge + installed helper CLI acceptance; no business workflows run."""
import asyncio,json,os,sys,tempfile,unittest,base64,shutil
from pathlib import Path
from unittest.mock import patch
from pd_chat_bridge import ChatBroker

BRIDGE=os.environ.get("PD_TEST_BRIDGE_EXE")
HELPER=os.environ.get("SCREEN_AUTOMATION_HELPER_EXE")

@unittest.skipUnless(BRIDGE and HELPER,"requires explicit native bridge and installed helper")
class FullCliNativeTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix="paldee-full-cli-")
  self.root=Path(self.temp.name);self.server=self.root/"server";self.server.mkdir()
  self.desktop=self.root/"desktop";self.desktop.mkdir()
  self.environment=dict(os.environ,SCREEN_AUTOMATION_HOME=str(self.desktop/"helper-data"),OCTOPPET_DATA_DIR=str(self.desktop/"pet-data"),USERPROFILE=str(self.desktop/"user"),APPDATA=str(self.desktop/"AppData"),LOCALAPPDATA=str(self.desktop/"Local"))
  self.environment.pop("PYTHONUTF8",None);self.environment.pop("PYTHONIOENCODING",None)
  self.server_environment=dict(self.environment,PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
  self.server_environment.pop("PD_CHAT_CALLER_CONFIG",None)
  self.broker=ChatBroker(timeout=80)
  self.frames=[];self.tasks=set()
  async def execute(frame):
   payload={"args":frame["args"]}
   if "input" in frame:payload["input"]=frame["input"]
   try:
    proc=await asyncio.create_subprocess_exec(BRIDGE,"--request-json",stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=self.environment)
    output,error=await proc.communicate(json.dumps(payload,ensure_ascii=False).encode())
    result=json.loads(output)
   except Exception as error:result={"ok":False,"error":str(error)}
   self.broker.complete("one",dict(frame,result=result))
  async def send(frame):
   self.frames.append(frame)
   task=asyncio.create_task(execute(frame));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
  self.broker.bind("user","agent","thread","one",send,self.server)
 async def asyncTearDown(self):
  if self.tasks:await asyncio.gather(*self.tasks)
  await asyncio.to_thread(self.broker.http.shutdown);self.broker.http.server_close()
  self.temp.cleanup()
 async def call(self,args,stdin=None,expected=0):
  proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name("pd_cli_proxy.py")),*args,cwd=self.server,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=self.server_environment)
  output,error=await proc.communicate(stdin.encode() if stdin is not None else None)
  self.assertEqual(proc.returncode,expected,(output.decode(),error.decode()))
  return json.loads(output)
 async def test_workflow_inspect_install_show_validate_and_source_download(self):
  package=self.server/"中文 流程包";package.mkdir()
  manifest={"schema_version":1,"id":"pd-bridge-acceptance","name":"桥接无操作验收","description":"只检查和安装，不运行屏幕操作","version":"0.1.0","target":{"os":"macos" if sys.platform == "darwin" else "windows","surface":"desktop","coordinate_space":"window-client"},"permissions":[],"runner":{"type":"python-sdk","entry":"workflow.py","sdk":"1.x"},"config":{},"outputs":{"format":"markdown-table","columns":[{"key":"result","label":"结果"}]}}
  manifest["permissions"]=["filesystem.write"]
  manifest["presentation"]={"summary":"检查桥接文件传输，不执行屏幕操作","steps":[{"title":"核对测试输入","observe":"只读取测试文件","success":"内容一致","failure":"停止"}]}
  (package/"workflow.json").write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8")
  source="def run(ctx):\n    return []\n"
  (package/"workflow.py").write_text(source,encoding="utf-8")
  sdk=await self.call(["cli","workflow","schema","sdk"])
  self.assertEqual(sdk["schema"],"screen-automation-workflow-sdk@1")
  inspected=await self.call(["cli","workflow","inspect",str(package)])
  self.assertEqual(self.frames[-1]["method"],"helper.cli.io")
  self.assertTrue(inspected.get("ok",True),inspected)
  installed=await self.call(["cli","workflow","install",str(package)])
  self.assertTrue(installed.get("ok",True),installed)
  shown=await self.call(["cli","workflow","show","pd-bridge-acceptance"])
  self.assertEqual(shown["id"],manifest["id"])
  validated=await self.call(["cli","workflow","validate","pd-bridge-acceptance"])
  self.assertTrue(validated.get("ok",True),validated)
  local_folder=shown["_meta"]["package_dir"]
  returned=await self.call(["--pd-download",local_folder,"cli","workflow","show","pd-bridge-acceptance"])
  copied=Path(returned["bridge_files"][0]["path"])
  self.assertEqual((copied/"workflow.py").read_text(encoding="utf-8"),source)
  self.assertTrue(copied.is_relative_to(self.server))
  self.assertEqual(json.loads((copied/"workflow.json").read_text())["id"],manifest["id"])
 async def test_real_memory_cli_receives_stdin(self):
  payload=json.dumps({"title":"桥接中文标准输入","content":"原文完整往返，不运行屏幕操作。"},ensure_ascii=False)
  result=await self.call(["cli","screen-memory","write"],stdin=payload)
  self.assertEqual(self.frames[-1]["input"]["stdin"],payload)
  self.assertTrue(result.get("ok",True),result)
  self.assertEqual(result["memory"]["title"],"桥接中文标准输入")
  read=await self.call(["cli","screen-memory","read","--id",result["memory"]["id"]])
  self.assertEqual(read["memory"]["content"],"原文完整往返，不运行屏幕操作。")

if __name__=="__main__":unittest.main()
