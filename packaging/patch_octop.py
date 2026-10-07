"""Generate a reviewable patch; never overwrite installed Octop source."""
import argparse
import hashlib
from pathlib import Path
import difflib

def patched(source):
    if "PD_CHAT_BRIDGE_PATCH" in source:
        raise ValueError("Source already patched")
    changes = [
        ('from octop.infra.gateway.ws import WS_CHANNEL_ID\n',
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
         '        hub.unregister(connection_id)\n'),
    ]
    for old, new in changes:
        expected = 2 if old == '            if msg_type == "ping":\n' else 1
        if source.count(old) != expected:
            raise ValueError("Upstream source differs; re-review before patching")
        source = source.replace(old, new, 1)
    return source

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = args.source.read_text(encoding="utf-8")
    after = patched(before)
    compile(after, str(args.source), "exec")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ws.py.patched").write_text(after, encoding="utf-8")
    patch = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                        fromfile="a/src/octop/api/routers/chat/ws.py",
                        tofile="b/src/octop/api/routers/chat/ws.py"))
    (args.output / "octop-chat-bridge.patch").write_text(patch, encoding="utf-8")
    (args.output / "baseline.sha256").write_text(hashlib.sha256(before.encode()).hexdigest() + "\n")
    print("Generated patch; original source unchanged.")

if __name__ == "__main__":
    main()
