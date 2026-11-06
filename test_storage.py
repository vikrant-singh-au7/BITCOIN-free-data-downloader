import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import runtime


class StorageTests(unittest.TestCase):
    def test_selected_folder_is_persisted_and_passed_to_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'preferences'/'settings.json'
            folder = Path(directory)/'selected'/'archive'
            with patch.object(runtime,'CONFIG',config),patch.object(runtime,'ROOT',runtime.ROOT), \
                 patch.dict(os.environ,{},clear=False):
                chosen,_ = runtime.select_folder(folder)
                self.assertEqual(chosen,folder.resolve())
                self.assertEqual(runtime.saved_folder(),folder.resolve())
                self.assertEqual(json.loads(config.read_text())['data_dir'],str(folder.resolve()))
                args = runtime.command('supervisor')
                self.assertEqual(args[args.index('--data-dir')+1],str(folder.resolve()))

    def test_low_space_is_rejected_without_saving_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'settings.json'
            with patch.object(runtime,'CONFIG',config), \
                 patch.object(runtime.shutil,'disk_usage',return_value=SimpleNamespace(free=1024**3)):
                with self.assertRaisesRegex(ValueError,'less than 2 GiB'):
                    runtime.select_folder(Path(directory)/'archive')
                self.assertFalse(config.exists())

    def test_invalid_path_does_not_replace_saved_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'settings.json'
            config.write_text(json.dumps({'data_dir':str(Path(directory).resolve())}))
            file = Path(directory)/'ordinary-file'
            file.write_text('not a directory')
            with patch.object(runtime,'CONFIG',config):
                with self.assertRaises(OSError):
                    runtime.select_folder(file/'archive')
                self.assertEqual(runtime.saved_folder(),Path(directory).resolve())

    def test_fresh_launch_requires_folder_choice(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime,'CONFIG',Path(directory)/'missing.json'), \
             patch.dict(os.environ,{},clear=True):
            self.assertTrue(runtime.needs_folder_selection())
            self.assertFalse(runtime.CONFIG.exists())

    def test_explicit_recovery_path_does_not_prompt_again(self):
        with patch.dict(os.environ,{'BTC_OPTIONS_HOME':str(Path.home())}):
            self.assertFalse(runtime.needs_folder_selection())

    def test_corrupt_preferences_request_a_new_choice(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True):
            config = Path(directory)/'settings.json'
            config.write_text('broken json')
            with patch.object(runtime,'CONFIG',config):
                self.assertTrue(runtime.needs_folder_selection())


if __name__ == '__main__':
    unittest.main()
