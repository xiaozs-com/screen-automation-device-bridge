"""Server-local adapter; computer traffic uses the existing chat WebSocket."""
import asyncio
import json
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = "pd-chat-cli@2"

def validate_args(args):
    if not isinstance(args,list) or not 2<=len(args)<=128 or args[0] not in ("cli","browser") or any(not isinstance(a,str) or len(a.encode())>4096 or "\0" in a for a in args):raise ValueError("invalid CLI args")
    if args[0]=="browser":return args
    family=args[1]
    valid=(family in ("status","describe","capabilities","health") and len(args)==2) or (family=="access" and args==["cli","access","list"]) or (family in ("window","screen","mouse","keyboard","ocr","browser") and len(args)>=3)
    if not valid:raise ValueError("unsupported CLI operation")
    return args

def normalize_result(result):
    if not isinstance(result,dict):raise ValueError("invalid result")
    if result.get("ok") is not True:return {"ok":False,"error":str(result.get("error") or "本机小助手调用失败")[:600]}
    if type(result.get("exit_code")) is not int or not 0<=result["exit_code"]<=255:raise ValueError("invalid exit code")
    if any(not isinstance(result.get(k),str) or len(result[k].encode())>1024*1024 for k in ("stdout","stderr")):raise ValueError("invalid output")
    value={k:result[k] for k in ("ok","exit_code","stdout","stderr")}
    artifact=result.get("artifact")
    if artifact is not None:
        if not isinstance(artifact,dict) or artifact.get("media_type")!="image/png" or not isinstance(artifact.get("data"),str) or len(artifact["data"])>6*1024*1024:raise ValueError("invalid artifact")
        value["artifact"]={"media_type":"image/png","data":artifact["data"]}
    return value

class ChatBroker:
    def __init__(self, timeout=90):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.connections = {}
        self.scopes = {}
        self.pending = {}
        self.http = None

    def start(self):
        if self.http is not None:
            return
        broker = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                code, result = 400, {"ok": False, "error": "请求未授权或格式无效"}
                try:
                    self.connection.settimeout(100)
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.path != "/cli" or not 2<=size<=64*1024:
                        raise ValueError()
                    auth = self.headers.get("Authorization", "")
                    if not auth.startswith("Bearer "):
                        raise ValueError()
                    args=validate_args(json.loads(self.rfile.read(size)).get("args"))
                    result = broker.call(auth[7:],args)
                    code = 200
                except ValueError as error:
                    if str(error) == "unsupported CLI operation":
                        result={"ok":False,"error":"小助手命令超出当前桥接支持范围"}
                    elif str(error) == "unauthorized":
                        code=401
                        result={"ok":False,"error":"聊天桥接凭据已失效，请重新发起宠物聊天"}
                except OSError:
                    result={"ok":False,"error":"服务器内部桥接连接异常"}
                data = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def bind(self, user_id, agent_id, thread_id, connection_id, send, workspace, loop=None):
        scope = (user_id, agent_id)
        with self.lock:
            self.start()
            if scope not in self.scopes:
                self.scopes[scope] = secrets.token_urlsafe(32)
            token = self.scopes[scope]
            self.connections[connection_id] = {
                "scope": scope, "thread": thread_id, "send": send,
                "loop": loop or asyncio.get_running_loop()}
            config = {"url": f"http://127.0.0.1:{self.http.server_port}", "token": token}
        provision_cli(Path(workspace))
        path = Path(workspace) / ".pd-chat-caller.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    def call(self, token, args):
        validate_args(args)
        with self.lock:
            scopes = [scope for scope, secret in self.scopes.items()
                      if secrets.compare_digest(secret, token)]
            if len(scopes) != 1:
                raise ValueError("unauthorized")
            sessions = [(cid, c) for cid, c in self.connections.items() if c["scope"] == scopes[0]]
            if len(sessions) != 1:
                return {"ok": False, "error": "聊天未连接或存在多个设备，请保留一个聊天连接"}
            cid, session = sessions[0]
            if sum(p["connection"] == cid for p in self.pending.values()) >= 8:
                return {"ok": False, "error": "查询队列已满"}
            rid = secrets.token_hex(16)
            pending = {"connection": cid, "thread": session["thread"],
                       "event": threading.Event(), "result": None}
            self.pending[rid] = pending
        try:
            sent = asyncio.run_coroutine_threadsafe(session["send"]({
                "type": "pd_cli_request", "protocol": PROTOCOL,
                "id": rid, "thread_id": session["thread"], "method": "helper.cli", "args":args}),
                session["loop"])
            sent.result(timeout=3)
            pending["event"].wait(self.timeout)
            return pending["result"] or {"ok": False, "error": "本机查询超时"}
        except (TimeoutError, RuntimeError, OSError):
            return {"ok": False, "error": "聊天连接不可用"}
        finally:
            with self.lock:
                self.pending.pop(rid, None)

    def complete(self, connection_id, frame):
        if not isinstance(frame, dict) or frame.get("protocol") != PROTOCOL or not isinstance(frame.get("id"), str):
            return False
        with self.lock:
            pending = self.pending.get(frame.get("id"))
            if (not pending or pending["connection"] != connection_id
                    or pending["thread"] != frame.get("thread_id")
                    or pending["event"].is_set()):
                return False
            try:
                pending["result"] = normalize_result(frame.get("result"))
            except ValueError:
                return False
            pending["event"].set()
            return True

    def disconnect(self, connection_id):
        with self.lock:
            self.connections.pop(connection_id, None)
            for pending in self.pending.values():
                if pending["connection"] == connection_id:
                    pending["result"] = {"ok": False, "error": "聊天连接已断开"}
                    pending["event"].set()

broker = ChatBroker()

def provision_cli(workspace):
    """Extend the existing helper resolver only; never execute PD during chat bind."""
    import sys, shutil, shlex
    if sys.platform != "linux": return
    proxy=Path(__file__).with_name("pd_cli_proxy.py")
    if not proxy.is_file(): raise OSError("PD CLI proxy module missing")
    entry=workspace/".octop/pd-chat-bridge/pd-helper"
    entry.parent.mkdir(parents=True,exist_ok=True)
    text="#!"+sys.executable+"\n"+proxy.read_text(encoding="utf-8")
    if not entry.exists() or entry.read_text(encoding="utf-8")!=text:
        entry.write_text(text,encoding="utf-8")
        entry.chmod(0o700)
    prefix="\n# PD_CHAT_CLI_RESOLVER_V2\nif [[ $(uname -s) == Linux ]]; then\n  printf '%s\\n' "+shlex.quote(str(entry))+"\n  exit 0\nfi\n"
    for root in (workspace/".octop/skills",workspace/"skills"):
        if not root.is_dir(): continue
        for skill in root.iterdir():
            if not skill.is_dir() or not skill.name.startswith("screen-automation"): continue
            for resolver in skill.rglob("resolve_cli.sh"):
                original=resolver.read_text(encoding="utf-8")
                if "PD_CHAT_CLI_RESOLVER_V2" in original or not original.startswith("#!/usr/bin/env bash"): continue
                backup=resolver.with_name(resolver.name+".before-pd-bridge")
                if backup.exists():
                    import hashlib
                    backup=resolver.with_name(resolver.name+".before-pd-bridge."+hashlib.sha256(original.encode()).hexdigest()[:12])
                    if backup.exists():continue
                shutil.copy2(resolver,backup)
                first,rest=original.split("\n",1)
                resolver.write_text(first+prefix+rest,encoding="utf-8")
