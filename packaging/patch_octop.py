"""Generate a reviewable patch; never overwrite installed Octop source."""
import argparse
import hashlib
from pathlib import Path
import difflib

def _updater():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "update_bridge.py"
    spec = importlib.util.spec_from_file_location("pd_bridge_updater", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patched(source):
    if "PD_CHAT_BRIDGE_PATCH" in source:
        raise ValueError("Source already patched")
    return _updater().chat_candidate(source)


def patched_manager(source):
    return _updater().manager_candidate(source)


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
