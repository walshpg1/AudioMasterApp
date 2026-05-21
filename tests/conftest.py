import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import soundfile as sf
import pytest


@pytest.fixture
def test_wav(tmp_path):
    path = tmp_path / "test_source.wav"
    sr = 44100
    rng = np.random.default_rng(42)
    data = rng.uniform(-0.5, 0.5, (sr * 3, 2))
    sf.write(str(path), data, sr, subtype="PCM_24")
    return str(path)


@pytest.fixture
def silent_wav(tmp_path):
    path = tmp_path / "silent.wav"
    sr = 44100
    data = np.zeros((sr * 2, 2))
    sf.write(str(path), data, sr, subtype="PCM_24")
    return str(path)
