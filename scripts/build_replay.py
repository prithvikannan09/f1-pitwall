"""Build the 3D race replay file for one or more sessions. Usage: python scripts/build_replay.py SESSION_KEY [...]"""
import sys

from f1analytics.pitwall import replay
from f1analytics.sources.openf1_source import OpenF1Source

src = OpenF1Source(timeout=60, retries=4)
for sk in sys.argv[1:]:
    data = replay.build(src, int(sk))
    p = replay.save(data)
    print(sk, data["location"], "cars", len(data["cars"]), "steps", len(data["cars"][0]["lon"]), "fit", data["fit_rms_m"], "m", "file", p.stat().st_size // 1024, "KB")
