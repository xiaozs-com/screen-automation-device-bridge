import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pd_chat_bridge
from pd_chat_bridge import ChatBroker, bridge_tools

HAS_FRAMEWORK = importlib.util.find_spec('langchain_core') is not None and importlib.util.find_spec('langgraph') is not None

@unittest.skipUnless(HAS_FRAMEWORK, 'requires LangChain/LangGraph runtime')
class ToolRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.workspace=Path(self.temp.name)
        self.broker=ChatBroker(timeout=.5)
        for user,thread,connection in [('1','thread-a','a'),('2','thread-b','b')]:
            async def send(frame, connection=connection, user=user):
                self.broker.complete(connection,dict(frame,result={'ok':True,'exit_code':0,'stdout':user,'stderr':''}))
            self.broker.bind(user,'shared',thread,connection,send,self.workspace,shared=True)

    async def asyncTearDown(self):
        if self.broker.http:
            await asyncio.to_thread(self.broker.http.shutdown)
            self.broker.http.server_close()
        self.temp.cleanup()

    async def test_real_structured_tool_uses_each_invocation_identity(self):
        with patch.object(pd_chat_bridge,'broker',self.broker):
            tool=bridge_tools('shared',self.workspace)[0]
            self.assertEqual(tool.name,'pd_helper_cli')
            self.assertEqual(set(tool.args),{'args','stdin'})
            a,b=await asyncio.gather(
                tool.ainvoke({'args':['cli','status']}, config={'configurable':{'user':'1','thread_id':'thread-a'}}),
                tool.ainvoke({'args':['cli','status']}, config={'configurable':{'user':'2','thread_id':'thread-b'}}))
            self.assertEqual(json.loads(a)['stdout'],'1')
            self.assertEqual(json.loads(b)['stdout'],'2')

    async def test_model_arguments_cannot_replace_runtime_identity(self):
        with patch.object(pd_chat_bridge,'broker',self.broker):
            tool=bridge_tools('shared',self.workspace)[0]
            with self.assertRaises(ValueError):
                await tool.ainvoke({'args':['cli','status'],'user':'2','thread_id':'thread-b'},
                    config={'configurable':{'user':'1','thread_id':'thread-a'}})
            result=await tool.ainvoke({'args':['cli','status']},
                config={'configurable':{'user':'1','thread_id':'thread-a'}})
            self.assertEqual(json.loads(result)['stdout'],'1')
            missing=await tool.ainvoke({'args':['cli','status']},config={'configurable':{}})
            self.assertFalse(json.loads(missing)['ok'])

if __name__=='__main__':unittest.main()
