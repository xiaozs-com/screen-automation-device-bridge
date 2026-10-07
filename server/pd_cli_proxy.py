"""Only PD CLI calls use this shim; ordinary server tools do not."""
import base64,json,os,sys,uuid
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args):return None
def main():
 try:
  args=sys.argv[1:]
  if len(args)<2 or args[0] not in ("cli","browser"):raise ValueError()
  cfg=json.loads(Path(os.environ.get("PD_CHAT_CALLER_CONFIG",str(Path.cwd()/".pd-chat-caller.json"))).read_text())
  parsed=urlsplit(cfg["url"])
  if parsed.scheme!="http" or parsed.hostname!="127.0.0.1" or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError()
  request=Request(cfg["url"]+"/cli",data=json.dumps({"args":args}).encode(),headers={"Authorization":"Bearer "+cfg["token"],"Content-Type":"application/json"})
  with build_opener(NoRedirect(),ProxyHandler({})).open(request,timeout=100) as response:raw=response.read(8*1024*1024+1)
  if len(raw)>8*1024*1024:raise ValueError()
  result=json.loads(raw)
  if result.get("ok") is not True:
   print(json.dumps(result,ensure_ascii=False),file=sys.stderr);return 1
  stdout=result["stdout"]
  if result.get("artifact"):
   artifact=result["artifact"]
   if artifact["media_type"]!="image/png":raise ValueError()
   data=base64.b64decode(artifact["data"],validate=True)
   if len(data)>4*1024*1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):raise ValueError()
   folder=Path.cwd()/".octop/pd-chat-bridge/captures";folder.mkdir(parents=True,exist_ok=True)
   path=folder/(uuid.uuid4().hex+".png");path.write_bytes(data);path.chmod(0o600)
   value=json.loads(stdout);value["path"]=str(path.resolve());stdout=json.dumps(value,ensure_ascii=False)+"\n"
  sys.stdout.write(stdout);sys.stderr.write(result["stderr"]);return result["exit_code"]
 except HTTPError as error:
  result={"ok":False,"error":f"服务器桥接拒绝请求（HTTP {error.code}）"}
  try:
   raw=error.read(4097)
   if len(raw)<=4096:
    body=json.loads(raw)
    if isinstance(body,dict) and isinstance(body.get("error"),str):result["error"]=body["error"][:600]
  except (OSError,ValueError):pass
  finally:error.close()
  print(json.dumps(result,ensure_ascii=False),file=sys.stderr);return 1
 except FileNotFoundError:
  print('{"ok":false,"error":"聊天桥接尚未就绪，请从宠物重新发起聊天"}',file=sys.stderr);return 1
 except OSError:
  print('{"ok":false,"error":"无法连接服务器内部桥接，请检查 Octop 服务并重新发起聊天"}',file=sys.stderr);return 1
 except (ValueError,KeyError,TypeError):
  print('{"ok":false,"error":"桥接请求或返回数据格式无效"}',file=sys.stderr);return 1
if __name__=="__main__":sys.exit(main())
