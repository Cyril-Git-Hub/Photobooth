import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import Config
from app.core.gif_builder import save_gif


class SaveGifTests(unittest.TestCase):
    def test_explicit_frame_duration_is_applied_to_every_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config.load(base_dir=Path(directory))
            frames = [
                np.full((48, 64, 3), (0, 0, 255), dtype=np.uint8),
                np.full((48, 64, 3), (255, 0, 0), dtype=np.uint8),
            ]
            path = save_gif(
                config, frames, "Dance",
                frame_duration_ms=2000,
                now=datetime(2026, 11, 5, 17, 0, 0),
            )

            with Image.open(path) as gif:
                durations = []
                for index in range(gif.n_frames):
                    gif.seek(index)
                    durations.append(gif.info["duration"])

        self.assertEqual(durations, [2000, 2000])


if __name__ == "__main__":
    unittest.main()
