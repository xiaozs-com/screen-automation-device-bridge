import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

UPDATER = Path(__file__).resolve().parents[1] / 'update_bridge.py'
if not UPDATER.is_file():
    UPDATER = Path(__file__).with_name('update_bridge.py')
spec = importlib.util.spec_from_file_location('bridge_updater', UPDATER)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

# Minimal syntactically valid upstream fixture with both ping branches.
BASE = '''from octop.infra.gateway.ws import WS_CHANNEL_ID
async def chat():
    try:
        while True:
            if msg_type == "ping":
                continue
            inbound = build_dashboard_inbound(
                prepared=prepared)
    finally:
        hub.unregister(connection_id)
async def other():
    while True:
        if ready:
            if msg_type == "ping":
                continue
'''

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / 'site' / 'octop'
        self.ws = self.package / 'api/routers/chat/ws.py'
        self.ws.parent.mkdir(parents=True)
        self.ws.write_text(BASE, encoding='utf-8')
        self.manager = self.package / 'infra/agents/manager.py'
        self.manager.parent.mkdir(parents=True)
        self.manager.write_text("def build():\n        merged_tools: list[Any] = []\n        return merged_tools\n")
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.module_sources = {}
        for name in ('pd_chat_bridge.py', 'pd_cli_proxy.py'):
            required='bridge_tools' if name=='pd_chat_bridge.py' else 'materialize_result'
            self.module_sources[name]='VALUE = 2\ndef '+required+'(): pass\n'
            (self.bundle / name).write_text(self.module_sources[name])
            (self.package.parent / name).write_text('VALUE = 1\n')
        self.record = self.bundle / 'install-records/test'

    def plan(self):
        return updater.build_plan(self.package, self.bundle)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_preview_changes_nothing(self):
        before = self.snapshot()
        plan, source, candidate = self.plan()
        self.assertEqual(len(plan), 4)
        self.assertNotEqual(source, candidate)
        self.assertEqual(before, self.snapshot())

    def test_restores_and_repeat_does_not_duplicate(self):
        plan, source, candidate = self.plan()
        updater.apply_plan(plan, self.record, source, candidate)
        self.assertEqual(self.ws.read_text(), candidate)
        self.assertEqual((self.record / 'ws.py').read_text(), BASE)
        self.assertTrue((self.record / 'rollback.txt').is_file())
        self.assertIn('+', (self.record / 'octop-chat-bridge.patch').read_text())
        plan2, before2, after2 = self.plan()
        self.assertEqual(len(plan2), 2)
        self.assertEqual(before2, after2)
        self.assertEqual(candidate.count(updater.MARKER), 1)

    def test_existing_patch_updates_only_modules(self):
        self.ws.write_text(updater.chat_candidate(BASE))
        before = self.ws.read_bytes()
        plan, source, candidate = self.plan()
        updater.apply_plan(plan, self.record, source, candidate)
        self.assertEqual(self.ws.read_bytes(), before)
        self.assertFalse((self.record / 'ws.py').exists())
        self.assertTrue((self.record / 'manager.py').exists())
        self.assertEqual((self.package.parent / 'pd_cli_proxy.py').read_text(), self.module_sources['pd_cli_proxy.py'])

    def test_upstream_mismatch_no_writes(self):
        self.ws.write_text(BASE.replace('hub.unregister(connection_id)', 'hub.remove(connection_id)'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, '不兼容'):
            self.plan()
        self.assertEqual(before, self.snapshot())

    def test_partial_patch_rejected(self):
        for source in (BASE + '# PD_CHAT_BRIDGE_PATCH\n', BASE + '# pd_chat_broker\n'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    updater.chat_candidate(source)

    def test_syntax_error_no_writes(self):
        (self.bundle / 'pd_cli_proxy.py').write_text('def broken(\n')
        before = self.snapshot()
        with self.assertRaises(SyntaxError):
            self.plan()
        self.assertEqual(before, self.snapshot())

    def test_missing_installed_module_rejected(self):
        (self.package.parent / 'pd_cli_proxy.py').unlink()
        with self.assertRaisesRegex(ValueError, '缺少已安装模块'):
            self.plan()

    def test_changed_target_rejected(self):
        plan, source, candidate = self.plan()
        self.ws.write_text(BASE + '# changed\n')
        with self.assertRaisesRegex(ValueError, '文件在检查后变化'):
            updater.apply_plan(plan, self.record, source, candidate)
        self.assertFalse(self.record.exists())

    def test_failed_write_rolls_back_all_changes(self):
        plan, source, candidate = self.plan()
        before = [(target, target.read_bytes()) for target, _, _ in plan]
        real_write = updater.atomic_write
        def fail_ws(target, data):
            if target == self.ws:
                raise OSError('simulated write failure')
            real_write(target, data)
        with patch.object(updater, 'atomic_write', side_effect=fail_ws):
            with self.assertRaises(OSError):
                updater.apply_plan(plan, self.record, source, candidate)
        for target, data in before:
            self.assertEqual(target.read_bytes(), data)

    def test_rollback_failure_reports_backup(self):
        plan, source, candidate = self.plan()
        calls = 0
        real_write = updater.atomic_write
        def fail_later(target, data):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError('simulated failure')
            real_write(target, data)
        with patch.object(updater, 'atomic_write', side_effect=fail_later):
            with self.assertRaisesRegex(RuntimeError, 'rollback.txt'):
                updater.apply_plan(plan, self.record, source, candidate)
        self.assertEqual((self.record / 'pd_chat_bridge.py').read_text(), 'VALUE = 1\n')

    def test_real_binding_uses_upstream_prepared_variable(self):
        from types import SimpleNamespace
        for name in ("prepared", "prepared_early"):
            source = BASE.replace("prepared=prepared)", "prepared=" + name + ")")
            candidate = updater.chat_candidate(source)
            # Execute exactly the inserted binding block without the old variable
            # in scope. Syntax-only tests cannot detect undefined names.
            block = updater.chat_changes(source)[2][1].split("            inbound =")[0]
            import textwrap
            calls = []
            registry = SimpleNamespace(
                get_row=lambda agent: SimpleNamespace(user_id="user"),
                resolve_workspace_dir=lambda agent: "/workspace/new-agent")
            environment = {
                "pd_chat_broker": SimpleNamespace(bind=lambda *args, **kwargs: calls.append(args)),
                "payload": {"pd_bridge": {"protocol": "pd-chat-cli@2", "operations": ["helper.cli"]}},
                "server": SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry)),
                "agent_id": "new-agent", "user": SimpleNamespace(id="user"),
                "connection_id": "connection", "send_frame": object(),
                name: SimpleNamespace(thread_id="new-thread"),
            }
            exec(textwrap.dedent(block), environment)
            self.assertEqual(calls[0][:4], ("user", "new-agent", "new-thread", "connection"))
            self.assertEqual(updater.chat_candidate(candidate), candidate)

    def test_repairs_known_legacy_patch_after_octop_upgrade(self):
        source = BASE.replace("prepared=prepared)", "prepared=prepared_early)")
        legacy = source
        for old, new in updater.CHANGES:
            legacy = legacy.replace(old, new, 1)
        self.assertIn("prepared.thread_id", legacy)
        repaired = updater.chat_candidate(legacy)
        self.assertIn("prepared_early.thread_id", repaired)
        self.assertNotIn("prepared.thread_id", repaired)
        self.assertEqual(updater.chat_candidate(repaired), repaired)

    def test_incompatible_manager_rejects_before_any_write(self):
        self.manager.write_text('def changed(): pass\n')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'工具注册位置不兼容'):
            self.plan()
        self.assertEqual(before,self.snapshot())

    def test_manager_write_failure_restores_ws_and_both_modules(self):
        plan,source,candidate=self.plan()
        before=[(target,target.read_bytes()) for target,_,_ in plan]
        real_write=updater.atomic_write
        def fail_manager(target,data):
            if target==self.manager:raise OSError('simulated manager failure')
            real_write(target,data)
        with patch.object(updater,'atomic_write',side_effect=fail_manager):
            with self.assertRaises(OSError):
                updater.apply_plan(plan,self.record,source,candidate)
        for target,data in before:self.assertEqual(target.read_bytes(),data)

    def test_shared_guest_binding_uses_current_user_and_marks_shared(self):
        import textwrap
        from types import SimpleNamespace
        block=updater.chat_changes(BASE)[2][1].split('            inbound =')[0]
        calls=[]
        registry=SimpleNamespace(get_row=lambda agent:SimpleNamespace(user_id='owner',is_shared=1),
            resolve_workspace_dir=lambda agent:'/shared-workspace')
        env={'pd_chat_broker':SimpleNamespace(bind=lambda *a,**kw:calls.append((a,kw))),
             'payload':{'pd_bridge':{'protocol':'pd-chat-cli@2','operations':['helper.cli']}},
             'server':SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry)),
             'user':SimpleNamespace(id='guest'),'agent_id':'shared','prepared':SimpleNamespace(thread_id='guest-thread'),
             'connection_id':'guest-connection','send_frame':object()}
        exec(textwrap.dedent(block),env)
        self.assertEqual(calls[0][0][:4],('guest','shared','guest-thread','guest-connection'))
        self.assertTrue(calls[0][1]['shared'])

    def test_only_replacing_updater_with_old_bundle_is_rejected(self):
        (self.bundle/'pd_chat_bridge.py').write_text('# old bridge module\n')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'完整新版更新包'):
            self.plan()
        self.assertEqual(before,self.snapshot())

if __name__ == '__main__':
    unittest.main()
