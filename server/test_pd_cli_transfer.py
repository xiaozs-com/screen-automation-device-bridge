import base64,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from pd_cli_proxy import prepare,save_files
from pd_chat_bridge import validate_input

class TransferTests(unittest.TestCase):
 def test_inline_file_and_explicit_upload_preserve_args(self):
  with tempfile.TemporaryDirectory() as temporary:
   path=Path(temporary)/"source.json";path.write_text("中文",encoding="utf-8")
   args,input=prepare(["cli","browser","verify","--action-file="+str(path)],"input")
   self.assertEqual(input["uploads"][0]["prefix"],"--action-file=")
   self.assertEqual(input["stdin"],"input")
   self.assertEqual(base64.b64decode(input["uploads"][0]["files"][0]["data"]).decode(),"中文")
   args,input=prepare(["--pd-upload","3="+str(path),"cli","future-command","read","local"])
   self.assertEqual(args,["cli","future-command","read","local"])
   self.assertEqual(input["uploads"][0]["arg_index"],3)
 def test_parent_traversal_never_writes_outside_server_transfer_root(self):
  with tempfile.TemporaryDirectory() as temporary,patch("pathlib.Path.cwd",return_value=Path(temporary)):
   with self.assertRaises(ValueError):save_files([{"source":"C:/x","name":"x","kind":"directory","files":[{"path":"../../escape","data":""}]}])
   self.assertFalse((Path(temporary)/"escape").exists())
 def test_oversized_stdin_and_unknown_envelope_fields_are_rejected(self):
  for value in [{"stdin":"x"*(1024*1024+1)},{"stdin":123},{"program":"cmd.exe"}]:
   with self.assertRaises(ValueError):validate_input(value)
 def test_windows_path_is_left_local_when_no_server_file_exists(self):
  args,input=prepare(["cli","workflow","inspect",r"C:\workflows\test"])
  self.assertIsNone(input)
  self.assertEqual(args[3],r"C:\workflows\test")

if __name__=="__main__":unittest.main()
