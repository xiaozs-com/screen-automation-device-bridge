"""Update bridge modules and restore compatible Octop chat wiring after upgrades.

Standalone: place beside pd_chat_bridge.py and pd_cli_proxy.py.
Preview by default; stop Octop before using --apply.
"""
import argparse
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile

MARKER = "PD_CHAT_BRIDGE_PATCH"
CHANGES = [('from octop.infra.gateway.ws import WS_CHANNEL_ID\n',
  'from octop.infra.gateway.ws import WS_CHANNEL_ID\n'
  '# PD_CHAT_BRIDGE_PATCH: independently installed adapter; ordinary chat still works without it.\n'
  'try:\n'
  '    from pd_chat_bridge import broker as pd_chat_broker\n'
  'except ImportError:\n'
  '    pd_chat_broker = None\n'),
 ('            if msg_type == "ping":\n',
  '            if msg_type == "pd_cli_result":\n'
  '                if pd_chat_broker is not None:\n'
  '                    pd_chat_broker.complete(connection_id, payload)\n'
  '                continue\n'
  '            if msg_type == "ping":\n'),
 ('            inbound = build_dashboard_inbound(\n',
  '            if pd_chat_broker is not None and payload.get("pd_bridge") == {\n'
  '                "protocol": "pd-chat-cli@2", "operations": ["helper.cli"]\n'
  '            }:\n'
  '                registry = server.app_runtime.agent_registry\n'
  '                row = registry.get_row(agent_id)\n'
  '                if row is not None and row.user_id == user.id:\n'
  '                    pd_chat_broker.bind(user.id, agent_id, prepared.thread_id,\n'
  '                        connection_id, send_frame, registry.resolve_workspace_dir(agent_id))\n'
  '            inbound = build_dashboard_inbound(\n'),
 ('        hub.unregister(connection_id)\n',
  '        if pd_chat_broker is not None:\n'
  '            pd_chat_broker.disconnect(connection_id)\n'
  '        hub.unregister(connection_id)\n')]


def chat_changes(source):
    calls = [node for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "build_dashboard_inbound"]
    prepared = [keyword.value for call in calls for keyword in call.keywords
                if keyword.arg == "prepared"]
    if len(prepared) != 1 or not isinstance(prepared[0], ast.Name):
        raise ValueError("无法确认 Octop 实际会话变量，请人工核对；未修改")
    name = prepared[0].id
    changes = [(old, new.replace("prepared.thread_id", name + ".thread_id"))
               for old, new in CHANGES]
    return [(old, new.replace(
        "if row is not None and row.user_id == user.id:", "if row is not None:"
    ).replace(
        "connection_id, send_frame, registry.resolve_workspace_dir(agent_id))",
        "connection_id, send_frame, registry.resolve_workspace_dir(agent_id),\n"
        "                        shared=bool(getattr(row, 'is_shared', False)) or row.user_id != user.id)"
    )) for old, new in changes]


def chat_candidate(source):
    changes = chat_changes(source)
    if MARKER in source:
        if all(source.count(new) == 1 for _, new in changes):
            compile(source, "ws.py", "exec")
            return source
        calls = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "build_dashboard_inbound"]
        prepared_name = next(keyword.value.id for call in calls for keyword in call.keywords
                             if keyword.arg == "prepared")
        versions = [CHANGES, [(old, new.replace("prepared.thread_id", prepared_name + ".thread_id"))
                             for old, new in CHANGES]]
        legacy = next((version for version in versions
                       if all(source.count(new) == 1 for _, new in version)), None)
        if legacy is None:
            raise ValueError("现有桥接接线不完整或内容不同，请人工核对；未修改")
        candidate = source
        for (_, before), (_, corrected) in zip(legacy, changes):
            if before != corrected:
                candidate = candidate.replace(before, corrected, 1)
        compile(candidate, "ws.py", "exec")
        return candidate
    if any(fragment in source for fragment in ("pd_chat_broker", "pd_cli_result", "pd-chat-cli@2")):
        raise ValueError("发现无标记的桥接残留，请人工核对；未修改")
    candidate = source
    for index, (old, new) in enumerate(changes, 1):
        expected = 2 if index == 2 else 1
        if candidate.count(old) != expected:
            raise ValueError(f"Octop 第 {index} 处接线位置不兼容，请人工核对；未修改")
        candidate = candidate.replace(old, new, 1)
    compile(candidate, "ws.py", "exec")
    return candidate


MANAGER_ANCHOR = "        merged_tools: list[Any] = []\n"
MANAGER_BLOCK = MANAGER_ANCHOR + """        # PD_CHAT_BRIDGE_TOOLS_PATCH: authenticated per-user/thread device routing.
        try:
            from pd_chat_bridge import bridge_tools as pd_bridge_tools
        except ImportError:
            pass
        else:
            merged_tools.extend(pd_bridge_tools(row.agent_id, workspace_dir))
"""


def manager_candidate(source):
    if "PD_CHAT_BRIDGE_TOOLS_PATCH" in source:
        if source.count(MANAGER_BLOCK) != 1:
            raise ValueError("现有桥接工具注册不完整或内容不同；未修改")
        return source
    if source.count(MANAGER_ANCHOR) != 1:
        raise ValueError("Octop 专家工具注册位置不兼容；未修改")
    result = source.replace(MANAGER_ANCHOR, MANAGER_BLOCK, 1)
    compile(result, "manager.py", "exec")
    return result


def build_plan(package, bundle):
    ws = package / "api/routers/chat/ws.py"
    before = ws.read_bytes()
    source = before.decode("utf-8").replace("\r\n", "\n")
    candidate = chat_candidate(source)
    plan = []
    for name in ("pd_chat_bridge.py", "pd_cli_proxy.py"):
        target = package.parent / name
        if not target.is_file():
            raise ValueError(f"缺少已安装模块 {target}；本脚本用于更新已有桥接")
        data = (bundle / name).read_bytes()
        compile(data, name, "exec")
        required = "bridge_tools" if name == "pd_chat_bridge.py" else "materialize_result"
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == required
                   for node in ast.parse(data).body):
            raise ValueError("当前包缺少共享工具实现，请上传完整新版更新包，不要只替换更新脚本")
        plan.append((target, target.read_bytes(), data))
    if candidate != source:
        plan.append((ws, before, candidate.encode("utf-8")))
    manager = package / "infra/agents/manager.py"
    manager_before = manager.read_bytes()
    manager_source = manager_before.decode("utf-8").replace("\r\n", "\n")
    manager_after = manager_candidate(manager_source)
    if manager_source != manager_after:
        plan.append((manager, manager_before, manager_after.encode("utf-8")))
    return plan, source, candidate


def atomic_write(target, data):
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def apply_plan(plan, record, source, candidate):
    # Recheck all inputs before writing or creating a backup record.
    for target, before, _ in plan:
        if target.read_bytes() != before:
            raise ValueError(f"文件在检查后变化，请重新预览：{target}")
    record.mkdir(parents=True, exist_ok=False)
    for target, _, _ in plan:
        shutil.copy2(target, record / target.name)
    (record / "rollback.txt").write_text(
        "先停止 Octop，按以下对应关系复制备份，再按原方式启动：\n" +
        "\n".join(f"{record / target.name} -> {target}" for target, _, _ in plan) + "\n",
        encoding="utf-8",
    )
    (record / "octop-chat-bridge.patch").write_text(
        "".join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True),
                                    fromfile="ws.py", tofile="ws.py.patched")),
        encoding="utf-8",
    )
    for target, before, data in plan:
        if target.name == "manager.py":
            (record / "manager-bridge.patch").write_text(
                "".join(difflib.unified_diff(before.decode("utf-8").splitlines(True),
                    data.decode("utf-8").splitlines(True), fromfile="manager.py", tofile="manager.py.patched")),
                encoding="utf-8")
    changed = []
    try:
        for target, before, data in plan:
            if data != before:
                atomic_write(target, data)
                changed.append(target)
    except Exception:
        failures = []
        for target in reversed(changed):
            try:
                atomic_write(target, (record / target.name).read_bytes())
            except Exception as error:
                failures.append(f"{target}: {error}")
        if failures:
            raise RuntimeError(f"自动恢复未全部成功，保持服务停止，按 {record / 'rollback.txt'} 恢复：" + "; ".join(failures))
        raise


def main():
    parser = argparse.ArgumentParser(description="预览或更新桥接模块，并恢复升级后丢失的兼容聊天接线")
    parser.add_argument("--apply", action="store_true", help="停止 Octop 后执行实际更新")
    args = parser.parse_args()
    spec = importlib.util.find_spec("octop")
    if spec is None or not spec.submodule_search_locations:
        parser.error("请使用 Octop 的 venv/bin/python 执行")
    package = Path(next(iter(spec.submodule_search_locations))).resolve()
    bundle = Path(__file__).resolve().parent
    try:
        plan, source, candidate = build_plan(package, bundle)
        print("Octop 聊天文件：", package / "api/routers/chat/ws.py")
        print("共享专家：将检查/注册 pd_helper_cli，按当前用户及线程选择设备")
        print("聊天接线：" + ("已存在并通过检查" if source == candidate else "将恢复或修正四处接线"))
        for target, before, data in plan:
            action = "内容相同" if before == data else "将更新"
            print(f"{target}: {action}，SHA256 {hashlib.sha256(data).hexdigest()}")
        if not args.apply:
            print("检查通过，仅预览，未修改任何文件。停止 Octop 后添加 --apply 更新。")
            return
        record = bundle / "install-records" / ("bridge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        apply_plan(plan, record, source, candidate)
    except (OSError, ValueError, SyntaxError, RuntimeError) as error:
        parser.exit(1, f"更新未完成：{error}\n如已产生备份，请查看 install-records 中的 rollback.txt。\n")
    print("桥接更新完成，备份：", record)
    print("请按原方式启动 Octop，再从宠物发起新聊天验证实际调用。")


if __name__ == "__main__":
    main()
