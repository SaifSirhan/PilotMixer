import unittest
import tempfile
from pathlib import Path
from soundboard_model import SoundPad, SoundboardConfig

class TestSoundboardModel(unittest.TestCase):
    def test_default_banks(self):
        config = SoundboardConfig()
        self.assertEqual(len(config.banks), 1)
        self.assertEqual(len(config.banks[0]), 8)

    def test_save_load_roundtrip(self):
        config = SoundboardConfig()
        config.banks[0][0].filepath = "test.wav"
        config.banks[0][0].hotkey = "<ctrl>+<num_1>"
        config.banks[0][0].volume = 0.5
        
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_config.json"
            config.save(p)
            loaded = SoundboardConfig.load(p)
            
            self.assertEqual(loaded.banks[0][0].filepath, "test.wav")
            self.assertEqual(loaded.banks[0][0].hotkey, "<ctrl>+<num_1>")
            self.assertEqual(loaded.banks[0][0].volume, 0.5)

    def test_clamping(self):
        config = SoundboardConfig()
        config.banks[0][0].volume = 2.0
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_config.json"
            p.write_text('{"banks": [[{"volume": 2.0}]]}')
            loaded = SoundboardConfig.load(p)
            self.assertEqual(loaded.banks[0][0].volume, 1.0)

    def test_volume_assignment_clamps_immediately(self):
        pad = SoundPad(volume=2.0)
        self.assertEqual(pad.volume, 1.0)

        pad.volume = -0.25
        self.assertEqual(pad.volume, 0.0)

        pad.volume = 0.35
        self.assertEqual(pad.volume, 0.35)

    def test_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "corrupt.json"
            p.write_text("{this is not valid json")
            loaded = SoundboardConfig.load(p)
            self.assertEqual(len(loaded.banks), 1)
            self.assertEqual(len(loaded.banks[0]), 8)

    def test_missing_file_fallback(self):
        config = SoundboardConfig.load(Path("does_not_exist_123.json"))
        self.assertEqual(len(config.banks), 1)
        self.assertEqual(len(config.banks[0]), 8)
