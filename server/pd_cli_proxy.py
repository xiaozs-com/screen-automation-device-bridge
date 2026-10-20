"""Only helper CLI uses the chat connection; file and stdin transport are optional."""
import base64,json,os,sys,uuid
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError
MAX_FILES=128
MAX_BYTES=4*1024*1024
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args):return None

def relative(value):
 if not isinstance(value,str) or not value or any(char in value for char in ('\\',':','\0')) or any(part in ('','.','..') for part in value.split('/')):raise ValueError('invalid transfer path')
 return value

def upload(path,index,prefix=''):
 path=Path(path).expanduser()
 if path.is_symlink():raise ValueError('upload cannot be a symlink')
 path=path.resolve(strict=True)
 sources=sorted(path.rglob('*')) if path.is_dir() else [path]
 files=[];size=0
 for source in sources:
  if source.is_symlink():raise ValueError('upload cannot contain symlinks')
  if source.is_dir():continue
  if not source.is_file() or source.stat().st_size>MAX_BYTES:raise ValueError('upload exceeds 4 MiB')
  data=source.read_bytes();size+=len(data)
  if len(files)>=MAX_FILES or size>MAX_BYTES:raise ValueError('upload exceeds 128 files or 4 MiB')
  files.append({'path':relative(source.relative_to(path).as_posix() if path.is_dir() else path.name),'data':base64.b64encode(data).decode()})
 value={'arg_index':index,'name':relative(path.name),'kind':'directory' if path.is_dir() else 'file','files':files}
 if prefix:value['prefix']=prefix
 return value

def prepare(arguments,stdin=None,workspace=None):
 base=Path(workspace).resolve() if workspace is not None else None
 def server_path(value):
  path=Path(value).expanduser()
  return base/path if base is not None and not path.is_absolute() else path
 def upload_source(path,index,prefix=''):
  path=server_path(path)
  if base is not None and not path.resolve().is_relative_to(base):
   raise ValueError('shared tool uploads must stay inside the expert workspace')
  return upload(path,index,prefix)
 args=list(arguments);uploads=[];downloads=[]
 while args and args[0].startswith('--pd-'):
  option=args.pop(0)
  if option not in ('--pd-upload','--pd-download') or not args:raise ValueError('invalid transfer option')
  value=args.pop(0)
  if option=='--pd-download':downloads.append(value)
  else:
   index,path=value.split('=',1);uploads.append(upload_source(path,int(index)))
 if not args or args[0] not in ('cli','browser'):raise ValueError('invalid CLI args')
 explicit={item['arg_index'] for item in uploads}
 if args[:3] in (['cli','workflow','install'],['cli','workflow','inspect']) and len(args)>3 and 3 not in explicit and server_path(args[3]).exists():
  uploads.append(upload_source(args[3],3));explicit.add(3)
 for index,arg in enumerate(args[1:],1):
  option,separator,value=arg.partition('=')
  if option.endswith('-file') and not option.startswith(('--output','--save')):
   target=index if separator else index+1
   source=value if separator else (args[target] if target<len(args) else '')
   if target not in explicit and source and server_path(source).is_file():
    uploads.append(upload_source(source,target,option+'=' if separator else ''));explicit.add(target)
 if any(item['arg_index']<1 or item['arg_index']>=len(args) for item in uploads):raise ValueError('invalid upload argument index')
 files=[file for item in uploads for file in item['files']]
 if len(files)>MAX_FILES or sum(len(base64.b64decode(file['data'])) for file in files)>MAX_BYTES:raise ValueError('upload exceeds 128 files or 4 MiB')
 if len(downloads)>MAX_FILES:raise ValueError('too many downloads')
 input={}
 if stdin is not None:
  if len(stdin.encode())>1024*1024:raise ValueError('stdin exceeds 1 MiB')
  input['stdin']=stdin
 if uploads:input['uploads']=uploads
 if downloads:input['downloads']=downloads
 return args,input or None

def save_files(files, base=None):
 if not isinstance(files,list) or len(files)>MAX_FILES:raise ValueError('invalid returned files')
 root=(Path(base) if base is not None else Path.cwd()/'.octop/pd-chat-bridge')/'files'/uuid.uuid4().hex
 saved=[];size=0;count=0
 for index,item in enumerate(files):
  name=relative(item['name'])
  if '/' in name or item['kind'] not in ('file','directory'):raise ValueError('invalid returned name')
  target=root/str(index)/name
  if item['kind']=='directory':target.mkdir(parents=True)
  contents=item['files']
  if not isinstance(contents,list) or (item['kind']=='file' and len(contents)!=1):raise ValueError('invalid returned contents')
  for file in contents:
   path=relative(file['path']);count+=1
   data=base64.b64decode(file['data'],validate=True);size+=len(data)
   if count>MAX_FILES or size>MAX_BYTES:raise ValueError('returned files exceed transfer limit')
   destination=target/path if item['kind']=='directory' else target
   destination.parent.mkdir(parents=True,exist_ok=True)
   with destination.open('xb') as output:output.write(data)
   destination.chmod(0o600)
  saved.append({'source':item['source'],'path':str(target.resolve()),'kind':item['kind']})
 return saved

def materialize_result(result, base=None):
 result=dict(result)
 stdout=result['stdout']
 if result.get('artifact'):
  artifact=result['artifact']
  if artifact['media_type']!='image/png':raise ValueError('invalid screenshot type')
  data=base64.b64decode(artifact['data'],validate=True)
  if len(data)>MAX_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('invalid screenshot')
  folder=(Path(base) if base is not None else Path.cwd()/'.octop/pd-chat-bridge')/'captures';folder.mkdir(parents=True,exist_ok=True)
  path=folder/(uuid.uuid4().hex+'.png');path.write_bytes(data);path.chmod(0o600)
  value=json.loads(stdout);value['path']=str(path.resolve());stdout=json.dumps(value,ensure_ascii=False)+'\n'
 metadata={}
 if result.get('files'):metadata['bridge_files']=save_files(result['files'],base)
 if result.get('uploaded_files'):metadata['bridge_uploaded_files']=result['uploaded_files']
 if metadata:
  try:
   value=json.loads(stdout)
   if not isinstance(value,dict):raise ValueError()
   value.update(metadata);stdout=json.dumps(value,ensure_ascii=False)+'\n'
  except ValueError:result['stderr']+=json.dumps(metadata,ensure_ascii=False)+'\n'
 result['stdout']=stdout
 result.pop('artifact',None)
 result.pop('files',None)
 return result

def main():
 try:
  stdin=None
  if not sys.stdin.isatty():
   stdin=sys.stdin.read(1024*1024+1)
  args,input=prepare(sys.argv[1:],stdin if stdin else None)
  if (Path.cwd()/'.octop/pd-chat-bridge/shared-mode').exists():
   raise ValueError('共享专家请使用 pd_helper_cli 工具，不使用工作区默认桥接凭据')
  cfg=json.loads(Path(os.environ.get('PD_CHAT_CALLER_CONFIG',str(Path.cwd()/'.pd-chat-caller.json'))).read_text())
  parsed=urlsplit(cfg['url'])
  if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('invalid local broker URL')
  value={'args':args}
  if input is not None:value['input']=input
  payload=json.dumps(value,ensure_ascii=False).encode()
  if len(payload)>8*1024*1024:raise ValueError('request exceeds 8 MiB')
  request=Request(cfg['url']+'/cli',data=payload,headers={'Authorization':'Bearer '+cfg['token'],'Content-Type':'application/json'})
  with build_opener(NoRedirect(),ProxyHandler({})).open(request,timeout=100) as response:raw=response.read(16*1024*1024+1)
  if len(raw)>16*1024*1024:raise ValueError('response exceeds 16 MiB')
  result=json.loads(raw)
  if result.get('ok') is not True:
   print(json.dumps(result,ensure_ascii=False),file=sys.stderr);return 1
  result=materialize_result(result)
  stdout=result['stdout']
  if args[:2] in (["cli","describe"],["cli","capabilities"]):
   try:
    value=json.loads(stdout)
    if isinstance(value,dict):
     value["chat_bridge"]={"cli_scope":"all helper CLI subcommands, including future commands","stdin":"UTF-8 piped input is forwarded","automatic_upload":"workflow install/inspect sources and input *-file arguments","upload_option":"pd-helper --pd-upload INDEX=SERVER_PATH cli ... (index counts cli as 0)","download_option":"pd-helper --pd-download LOCAL_WINDOWS_PATH cli ...; read bridge_files[].path on server","file_batch_limit_bytes":MAX_BYTES,"file_batch_limit_count":MAX_FILES}
     stdout=json.dumps(value,ensure_ascii=False)+'\n'
   except ValueError:pass
  sys.stdout.write(stdout);sys.stderr.write(result['stderr']);return result['exit_code']
 except HTTPError as error:
  result={'ok':False,'error':f'服务器桥接拒绝请求（HTTP {error.code}）'}
  try:
   raw=error.read(4097)
   if len(raw)<=4096:
    body=json.loads(raw)
    if isinstance(body,dict) and isinstance(body.get('error'),str):result['error']=body['error'][:600]
  except (OSError,ValueError):pass
  finally:error.close()
  print(json.dumps(result,ensure_ascii=False),file=sys.stderr);return 1
 except FileNotFoundError:
  print('{"ok":false,"error":"文件或桥接配置不存在，请检查路径并从宠物重新发起聊天"}',file=sys.stderr);return 1
 except OSError:
  print('{"ok":false,"error":"文件读取或桥接连接失败，请检查本机状态与路径"}',file=sys.stderr);return 1
 except (ValueError,KeyError,TypeError) as error:
  print(json.dumps({'ok':False,'error':'桥接参数或文件传输格式无效：'+str(error)[:300]},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
