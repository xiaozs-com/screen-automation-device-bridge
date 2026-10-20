import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from pd_chat_bridge import ChatBroker, PROTOCOL, execute_context, bridge_tools

ARGS = ['cli', 'status']

class SharedExpertTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.broker = ChatBroker(timeout=.2)

    async def asyncTearDown(self):
        if self.broker.http:
            await asyncio.to_thread(self.broker.http.shutdown)
            self.broker.http.server_close()
        self.temp.cleanup()

    def bind_user(self, user, thread, connection, label, *, shared=True, screenshot=False):
        async def send(frame):
            result = {'ok':True,'exit_code':0,'stdout':json.dumps({'device':label}),'stderr':''}
            if screenshot:
                result['artifact']={'media_type':'image/png','data':base64.b64encode(b'\x89PNG\r\n\x1a\n'+label.encode()).decode()}
            self.broker.complete(connection, dict(frame, result=result))
        self.broker.bind(user,'shared-expert',thread,connection,send,self.workspace,shared=shared)

    async def execute(self,user,thread,args=None):
        return await asyncio.to_thread(execute_context,self.broker,'shared-expert',self.workspace,
                                       {'user':user,'thread_id':thread},args or ARGS)

    async def test_two_users_same_expert_concurrent_route_to_own_computers(self):
        self.bind_user(1,'thread-a','connection-a','computer-a')
        self.bind_user(2,'thread-b','connection-b','computer-b')
        a,b = await asyncio.gather(self.execute('1','thread-a'), self.execute('2','thread-b'))
        self.assertEqual(json.loads(a['stdout'])['device'],'computer-a')
        self.assertEqual(json.loads(b['stdout'])['device'],'computer-b')
        self.assertFalse((self.workspace/'.pd-chat-caller.json').exists())
        self.assertTrue((self.workspace/'.octop/pd-chat-bridge/shared-mode').exists())

    async def test_user_cannot_select_another_users_thread(self):
        self.bind_user(1,'thread-a','connection-a','computer-a')
        self.bind_user(2,'thread-b','connection-b','computer-b')
        for user,thread in [('1','thread-b'),('2','thread-a'),('3','thread-a')]:
            self.assertFalse((await self.execute(user,thread))['ok'])

    async def test_shared_visitor_does_not_overwrite_owner_credentials(self):
        self.bind_user(1,'owner-thread','owner-connection','owner',shared=False)
        owner_config=(self.workspace/'.pd-chat-caller.json').read_bytes()
        self.bind_user(2,'guest-thread','guest-connection','guest')
        self.assertEqual((self.workspace/'.pd-chat-caller.json').read_bytes(),owner_config)
        self.assertEqual(json.loads((await self.execute(2,'guest-thread'))['stdout'])['device'],'guest')

    async def test_same_user_different_threads_are_separate(self):
        self.bind_user(1,'thread-a','connection-a','device-a')
        self.bind_user(1,'thread-b','connection-b','device-b')
        a,b=await asyncio.gather(self.execute(1,'thread-a'), self.execute(1,'thread-b'))
        self.assertEqual(json.loads(a['stdout'])['device'],'device-a')
        self.assertEqual(json.loads(b['stdout'])['device'],'device-b')

    async def test_missing_context_or_disconnected_does_not_fallback(self):
        self.bind_user(1,'thread-a','connection-a','device-a')
        for context in ({},{'user':1},{'user':True,'thread_id':'thread-a'}):
            result=execute_context(self.broker,'shared-expert',self.workspace,context,ARGS)
            self.assertFalse(result['ok'])
        self.broker.disconnect('connection-a')
        self.assertFalse((await self.execute(1,'thread-a'))['ok'])

    async def test_multiple_devices_for_same_context_are_rejected(self):
        self.bind_user(1,'thread-a','connection-a','device-a')
        self.bind_user(1,'thread-a','connection-b','device-b')
        self.assertFalse((await self.execute(1,'thread-a'))['ok'])

    async def test_old_proxy_cannot_use_owner_default_in_shared_workspace(self):
        self.bind_user(1,'owner-thread','owner-connection','owner',shared=False)
        self.bind_user(2,'guest-thread','guest-connection','guest')
        process=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('pd_cli_proxy.py')),
            *ARGS,cwd=self.workspace,stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await process.communicate()
        self.assertEqual(process.returncode,1)
        self.assertIn('pd_helper_cli',stderr.decode())

    async def test_screenshot_results_are_materialized_under_separate_contexts(self):
        self.bind_user(1,'thread-a','connection-a','device-a',screenshot=True)
        self.bind_user(2,'thread-b','connection-b','device-b',screenshot=True)
        a,b=await asyncio.gather(self.execute(1,'thread-a'),self.execute(2,'thread-b'))
        pa=Path(json.loads(a['stdout'])['path']);pb=Path(json.loads(b['stdout'])['path'])
        self.assertNotEqual(pa.parent,pb.parent)
        self.assertTrue(pa.read_bytes().endswith(b'device-a'))
        self.assertTrue(pb.read_bytes().endswith(b'device-b'))
        self.assertNotIn('artifact',a)

    async def test_foreign_thread_result_cannot_complete_request(self):
        async def send(frame):
            wrong=dict(frame,thread_id='other-thread',result={'ok':True,'exit_code':0,'stdout':'wrong','stderr':''})
            self.assertFalse(self.broker.complete('connection-a',wrong))
            correct=dict(frame,result={'ok':True,'exit_code':0,'stdout':'correct','stderr':''})
            self.assertTrue(self.broker.complete('connection-a',correct))
        self.broker.bind(1,'shared-expert','thread-a','connection-a',send,self.workspace,shared=True)
        self.assertEqual((await self.execute(1,'thread-a'))['stdout'],'correct')

    async def test_shared_workflow_stdin_files_and_exit_code_preserved(self):
        folder=self.workspace/'workflow';folder.mkdir();(folder/'workflow.md').write_text('test')
        async def send(frame):
            self.assertEqual(frame['method'],'helper.cli.io')
            self.assertEqual(frame['input']['stdin'],'input-text')
            self.assertEqual(frame['input']['uploads'][0]['kind'],'directory')
            self.broker.complete('connection-a',dict(frame,result={'ok':True,'exit_code':7,'stdout':'out','stderr':'err'}))
        self.broker.bind(1,'shared-expert','thread-a','connection-a',send,self.workspace,shared=True)
        result=await asyncio.to_thread(execute_context,self.broker,'shared-expert',self.workspace,
            {'user':1,'thread_id':'thread-a'},['cli','workflow','inspect',str(folder)],'input-text')
        self.assertEqual((result['exit_code'],result['stdout'],result['stderr']),(7,'out','err'))

    async def test_relative_workflow_paths_use_expert_workspace_not_process_cwd(self):
        folder=self.workspace/'relative-workflow';folder.mkdir();(folder/'workflow.md').write_text('source')
        async def send(frame):
            self.assertEqual(frame['input']['uploads'][0]['files'][0]['path'],'workflow.md')
            self.broker.complete('connection-a',dict(frame,result={'ok':True,'exit_code':0,'stdout':'{}','stderr':''}))
        self.broker.bind(1,'shared-expert','thread-a','connection-a',send,self.workspace,shared=True)
        result=await self.execute(1,'thread-a',['cli','workflow','inspect','relative-workflow'])
        self.assertTrue(result['ok'])

    async def test_tool_cannot_upload_other_users_server_files(self):
        self.bind_user(1,'thread-a','connection-a','device-a')
        with tempfile.TemporaryDirectory() as outside:
            secret=Path(outside)/'private.txt';secret.write_text('not transmitted')
            result=await self.execute(1,'thread-a',['--pd-upload','3='+str(secret),'cli','workflow','inspect','source'])
            self.assertFalse(result['ok'])
            self.assertIn('workspace',result['error'])

    async def test_private_legacy_proxy_refuses_ambiguous_threads(self):
        self.bind_user(1,'thread-a','connection-a','device-a',shared=False)
        self.bind_user(1,'thread-b','connection-b','device-b',shared=False)
        token=self.broker.context_token(1,'shared-expert','thread-b')
        legacy=await asyncio.to_thread(self.broker.call,token,ARGS)
        self.assertFalse(legacy['ok'])
        self.assertIn('pd_helper_cli',legacy['error'])
        self.assertEqual(json.loads((await self.execute(1,'thread-a'))['stdout'])['device'],'device-a')

if __name__=='__main__':unittest.main()
