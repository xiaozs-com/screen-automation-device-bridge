from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from test_update_bridge import BASE

class SharedInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.bundle=self.root/'bundle';self.bundle.mkdir()
        source=Path(__file__).resolve().parents[1]
        if not (source/'install_server.py').is_file():source=Path(__file__).parent
        for name in ('install_server.py','update_bridge.py'):
            shutil.copy2(source/name,self.bundle/name)
        for name in ('pd_chat_bridge.py','pd_cli_proxy.py'):
            module=source/'server'/name if (source/'server'/name).is_file() else source/name
            shutil.copy2(module,self.bundle/name)
        (self.bundle/'packaging').mkdir()
        shutil.copy2(source/'packaging/patch_octop.py',self.bundle/'packaging/patch_octop.py')
        self.octop_root=self.root/'octop-root'
        self.package=self.octop_root/'src/octop'
        self.ws=self.package/'api/routers/chat/ws.py';self.ws.parent.mkdir(parents=True)
        self.ws.write_text(BASE,encoding='utf-8')
        self.manager=self.package/'infra/agents/manager.py';self.manager.parent.mkdir(parents=True)
        self.manager.write_text('def build():\n        merged_tools: list[Any] = []\n        return merged_tools\n')

    def run_installer(self,*extra):
        return subprocess.run([sys.executable,'-B',str(self.bundle/'install_server.py'),
            '--octop-root',str(self.octop_root),*extra],capture_output=True)

    def test_fresh_install_adds_shared_tools_and_backs_up_both_octop_files(self):
        ws_before=self.ws.read_bytes();manager_before=self.manager.read_bytes()
        preview=self.run_installer()
        self.assertEqual(preview.returncode,0,preview.stderr)
        self.assertEqual(self.ws.read_bytes(),ws_before)
        self.assertEqual(self.manager.read_bytes(),manager_before)
        result=self.run_installer('--apply')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('shared=bool',self.ws.read_text())
        self.assertIn('PD_CHAT_BRIDGE_TOOLS_PATCH',self.manager.read_text())
        self.assertEqual(len(list((self.bundle/'install-records').glob('*/manager.py.original'))),1)
        self.assertTrue((self.package.parent/'pd_chat_bridge.py').is_file())
        self.assertTrue((self.package.parent/'pd_cli_proxy.py').is_file())

    def test_incompatible_manager_leaves_installed_files_unchanged(self):
        self.manager.write_text('def changed(): pass\n')
        before=self.ws.read_bytes()
        result=self.run_installer('--apply')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.ws.read_bytes(),before)
        self.assertFalse((self.package.parent/'pd_chat_bridge.py').exists())

    def test_existing_install_is_not_overwritten(self):
        module=self.package.parent/'pd_chat_bridge.py';module.write_text('# existing\n')
        before=self.ws.read_bytes()
        result=self.run_installer('--apply')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(module.read_text(),'# existing\n')
        self.assertEqual(self.ws.read_bytes(),before)

if __name__=='__main__':unittest.main()
