"""Preview or apply the independently maintained chat bridge patch."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import sys

def main():
    parser=argparse.ArgumentParser(description="先预览，再用 --apply 安装；安装后需手动重启 Octop。")
    locations=parser.add_mutually_exclusive_group(required=True)
    locations.add_argument("--octop-root",type=Path,help="含 src/octop 的 Octop 源码目录")
    locations.add_argument("--installed",action="store_true",help="使用当前 Python 环境中安装的 Octop")
    parser.add_argument("--inspect",action="store_true",help="只输出安装版本和实际路径，不修改文件")
    parser.add_argument("--agent-workspace",type=Path,help="用户私有 Agent 的实际工作目录")
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    bundle=Path(__file__).resolve().parent
    if args.installed:
        spec=importlib.util.find_spec("octop")
        if spec is None or not spec.submodule_search_locations:
            parser.error("此 Python 环境没有安装 Octop；请使用 ~/.octop/venv/bin/python 运行")
        package=Path(next(iter(spec.submodule_search_locations))).resolve()
        module_dir=package.parent
    else:
        module_dir=args.octop_root.resolve()/"src"
        package=module_dir/"octop"
    source=package/"api/routers/chat/ws.py"
    if args.inspect:
        from importlib.metadata import version, PackageNotFoundError
        try: installed_version=version("octop")
        except PackageNotFoundError: installed_version="unknown"
        print("Python: "+sys.executable)
        print("Octop version: "+installed_version)
        print("Octop package: "+str(package))
        print("Chat source: "+str(source))
        print("Chat source exists: "+str(source.is_file()))
        print("只读检查，未修改任何文件。")
        return
    workspace=args.agent_workspace.resolve() if args.agent_workspace else None
    if not source.is_file() or (workspace is not None and not workspace.is_dir()):
        parser.error("请核对 Octop 源码目录和已存在的私有 Agent 工作目录")
    spec=importlib.util.spec_from_file_location("patch_octop",bundle/"packaging/patch_octop.py")
    patcher=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    original=source.read_text(encoding="utf-8")
    try:
        candidate=patcher.patched(original)
    except ValueError as error:
        parser.error(str(error))
    compile(candidate,str(source),"exec")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    review=bundle/"install-records"/stamp
    review.mkdir(parents=True)
    import difflib, hashlib
    (review/"octop-chat-bridge.patch").write_text("".join(difflib.unified_diff(
        original.splitlines(True),candidate.splitlines(True),fromfile="ws.py",tofile="ws.py.patched")),encoding="utf-8")
    (review/"baseline.sha256").write_text(hashlib.sha256(source.read_bytes()).hexdigest()+"\n")
    print("预览补丁："+str(review/"octop-chat-bridge.patch"))
    if not args.apply:
        print("未修改 Octop。检查补丁后，同样参数加 --apply 安装。")
        return
    module=module_dir/"pd_chat_bridge.py"
    proxy=module_dir/"pd_cli_proxy.py"
    if module.exists() or proxy.exists():
        parser.error("已有桥接模块；请先核对旧安装，禁止自动覆盖")
    backup=review/"ws.py.original"
    shutil.copy2(source,backup)
    shutil.copy2(bundle/"pd_chat_bridge.py",module)
    shutil.copy2(bundle/"pd_cli_proxy.py",proxy)
    try:
        source.write_text(candidate,encoding="utf-8")
    except OSError:
        shutil.copy2(backup,source)
        module.unlink()
        proxy.unlink()
        raise
    (review/"rollback.txt").write_text(
        "先停止 Octop，再恢复原文件：\n"+str(backup)+" -> "+str(source)+
        "\n删除本次新增模块：\n"+str(module)+
        "\n删除本次新增代理模块：\n"+str(proxy)+
        "\n然后按原方式重启 Octop。不要删除 Agent 工作目录或其他 Skill。\n",encoding="utf-8")
    print("安装文件完成，备份："+str(backup))
    print("无须指定 Agent；已有或新 Agent 的小助手 Skill 在聊天连接时自动接入 CLI 代理。")
    print("尚未重启 Octop。请按原方式重启，并验证导入、WSS 和私有 Agent。")
    print("请使用与 Octop 服务相同的运行用户和 Python 环境。更新 Octop 后需重新检查补丁兼容性。")

if __name__=="__main__":
    main()
