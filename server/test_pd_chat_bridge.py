import asyncio,json,os,sys,tempfile,unittest,base64
from pathlib import Path
from unittest.mock import patch
from pd_chat_bridge import ChatBroker,PROTOCOL,validate_args,provision_cli
ARGS=["cli","window","list-visible"]
def output(stdout="{}",code=0):return {"ok":True,"exit_code":code,"stdout":stdout,"stderr":""}
class BrokerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.broker=ChatBroker(timeout=.1);self.tmp=tempfile.TemporaryDirectory();self.workspace=Path(self.tmp.name)
 async def asyncTearDown(self):
  if self.broker.http:
   await asyncio.to_thread(self.broker.http.shutdown);self.broker.http.server_close()
  self.tmp.cleanup()
 def bind(self,send,cid="one"):
  self.broker.bind("user","agent","thread",cid,send,self.workspace)
  return json.loads((self.workspace/".pd-chat-caller.json").read_text())["token"]
 async def test_normal_chat_does_not_execute_or_send_cli(self):
  send_calls=[]
  async def send(frame):send_calls.append(frame)
  self.bind(send)
  self.assertEqual(send_calls,[])
 async def test_same_connection_and_thread_required(self):
  async def send(frame):
   self.assertEqual(frame["args"],ARGS);self.assertEqual(frame["method"],"helper.cli")
   reply=dict(frame,result=output("original CLI output",7))
   self.assertFalse(self.broker.complete("wrong-device",reply))
   self.assertFalse(self.broker.complete("one",dict(reply,thread_id="other")))
   self.assertTrue(self.broker.complete("one",reply))
   self.assertFalse(self.broker.complete("one",reply))
  token=self.bind(send)
  self.assertEqual(await asyncio.to_thread(self.broker.call,token,ARGS),output("original CLI output",7))
 async def test_disconnect_and_timeout(self):
  async def send(frame):self.broker.disconnect("one")
  token=self.bind(send)
  self.assertFalse((await asyncio.to_thread(self.broker.call,token,ARGS))["ok"])
  async def silent(frame):pass
  self.bind(silent)
  self.assertFalse((await asyncio.to_thread(self.broker.call,token,ARGS))["ok"])
 async def test_multiple_devices_and_invalid_token(self):
  async def send(frame):self.fail("must not pick device")
  token=self.bind(send);self.bind(send,"two")
  self.assertFalse((await asyncio.to_thread(self.broker.call,token,ARGS))["ok"])
  with self.assertRaises(ValueError):await asyncio.to_thread(self.broker.call,"wrong",ARGS)
 async def test_proxy_preserves_args_stdout_stderr_and_exit_code(self):
  async def send(frame):
   self.assertEqual(frame["args"],["cli","keyboard","type","hello; literal argument"])
   self.broker.complete("one",dict(frame,result={"ok":True,"exit_code":5,"stdout":"out","stderr":"err"}))
  self.bind(send)
  script=Path(__file__).with_name("pd_cli_proxy.py")
  env=dict(os.environ);env.pop("PD_CHAT_CALLER_CONFIG",None)
  proc=await asyncio.create_subprocess_exec(sys.executable,str(script),"cli","keyboard","type","hello; literal argument",cwd=self.workspace,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  stdout,stderr=await proc.communicate()
  self.assertEqual((proc.returncode,stdout,stderr),(5,b"out",b"err"))
 async def test_synthetic_capture_returns_server_file_not_client_path(self):
  data=b"\x89PNG\r\n\x1a\n"+b"synthetic-test"
  async def send(frame):
   result=output(json.dumps({"ok":True,"path":"C:/local-only.png"}))
   result["artifact"]={"media_type":"image/png","data":base64.b64encode(data).decode()}
   self.broker.complete("one",dict(frame,result=result))
  self.bind(send)
  proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name("pd_cli_proxy.py")),"cli","screen","capture",cwd=self.workspace,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  stdout,stderr=await proc.communicate()
  self.assertEqual(proc.returncode,0,stderr)
  returned=Path(json.loads(stdout)["path"])
  self.assertTrue(returned.is_relative_to(self.workspace));self.assertEqual(returned.read_bytes(),data)
 async def test_new_skill_resolver_is_patched_once_and_backed_up(self):
  resolver=self.workspace/".octop/skills/screen-automation/scripts/resolve_cli.sh";resolver.parent.mkdir(parents=True)
  original="#!/usr/bin/env bash\nset -euo pipefail\necho original\n";resolver.write_text(original)
  with patch("sys.platform","linux"):
   provision_cli(self.workspace);first=resolver.read_text();provision_cli(self.workspace)
  self.assertEqual(first,resolver.read_text());self.assertIn("PD_CHAT_CLI_RESOLVER_V2",first)
  self.assertEqual(resolver.with_name("resolve_cli.sh.before-pd-bridge").read_text(),original)
 def test_invalid_args_and_system_entry_points_are_rejected(self):
  for args in [["bash","-c","bad"],["powershell","-Command","run"],["cmd","/c","run"],["cli","screen","bad\0"]]:
   with self.assertRaises(ValueError):validate_args(args)
 async def test_browser_proxy_uses_same_connection_and_preserves_helper_error(self):
  async def send(frame):
   self.assertEqual(frame["args"],["browser","status"])
   self.broker.complete("one",dict(frame,result=output('{"ok":false,"error":"浏览器组件未启用"}',2)))
  self.bind(send)
  proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name("pd_cli_proxy.py")),"browser","status",cwd=self.workspace,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  stdout,stderr=await proc.communicate()
  self.assertEqual(proc.returncode,2)
  self.assertEqual(json.loads(stdout)["error"],"浏览器组件未启用")

 async def test_workflow_stdin_and_files_use_same_connection(self):
  contents=b"def run(ctx): pass"
  async def send(frame):
   self.assertEqual(frame["method"],"helper.cli.io")
   self.assertEqual(frame["args"],["cli","workflow","show","test"])
   self.assertEqual(frame["input"]["stdin"],"中文输入")
   result=output("{}")
   result["files"]=[{"source":"C:/test/flow.py","name":"flow.py","kind":"file","files":[{"path":"flow.py","data":base64.b64encode(contents).decode()}]}]
   self.broker.complete("one",dict(frame,result=result))
  self.bind(send)
  proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name("pd_cli_proxy.py")),"--pd-download","C:/test/flow.py","cli","workflow","show","test",cwd=self.workspace,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  stdout,stderr=await proc.communicate("中文输入".encode())
  self.assertEqual(proc.returncode,0,stderr)
  path=Path(json.loads(stdout)["bridge_files"][0]["path"])
  self.assertTrue(path.is_relative_to(self.workspace))
  self.assertEqual(path.read_bytes(),contents)

 def test_future_helper_subcommands_are_not_blocked(self):
  for args in [["cli"],["cli","--help"],["cli","workflow","install","test"],["cli","access","activate"],["cli","future-command"]]:
   self.assertEqual(validate_args(args),args)

 async def test_workflow_directory_is_uploaded_automatically(self):
  folder=self.workspace/"中文 流程";folder.mkdir();(folder/"flow.py").write_text("source",encoding="utf-8")
  async def send(frame):
   self.assertEqual(frame["method"],"helper.cli.io")
   item=frame["input"]["uploads"][0]
   self.assertEqual(item["arg_index"],3)
   self.assertEqual(item["kind"],"directory")
   self.assertEqual(base64.b64decode(item["files"][0]["data"]),b"source")
   self.broker.complete("one",dict(frame,result=output()))
  self.bind(send)
  proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name("pd_cli_proxy.py")),"cli","workflow","inspect",str(folder),cwd=self.workspace,stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  stdout,stderr=await proc.communicate();self.assertEqual(proc.returncode,0,stderr)

if __name__=="__main__":unittest.main()
