import hashlib
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feature_cache import DigestIndex  # noqa: E402


def main():
    tmp = tempfile.mkdtemp()
    try:
        a = os.path.join(tmp, "a.wav")
        b = os.path.join(tmp, "b.wav")
        open(a, "wb").write(b"AUDIO-one")
        open(b, "wb").write(b"AUDIO-two")
        sc = os.path.join(tmp, "digests.json")

        # 1. digest correctness + no flush until dirty
        idx = DigestIndex(sc)
        da, db = idx.digest(a), idx.digest(b)
        assert da == hashlib.sha256(b"AUDIO-one").hexdigest()
        assert not os.path.exists(sc)
        idx.flush()
        assert os.path.exists(sc)

        # 2. memo hit: second instance must not rehash (no dirty flag)
        idx2 = DigestIndex(sc)
        assert idx2.digest(a) == da
        assert not idx2._dirty, "memo hit must not rehash"

        # 3. content change detected even with fudged mtime
        open(a, "wb").write(b"AUDIO-one-EDITED")
        os.utime(a, ns=(1000, 1000))
        idx3 = DigestIndex(sc)
        d3 = idx3.digest(a)
        assert d3 != da
        assert d3 == hashlib.sha256(b"AUDIO-one-EDITED").hexdigest()

        # 4. missing file -> None (dropped by verify logic)
        gone = os.path.join(tmp, "gone.wav")
        assert idx3.digest(gone) is None

        # 5. npz verify-and-drop roundtrip (mirrors load_aligned logic)
        paths = [a, b, gone]
        digests = [d3, db, "deadbeef"]
        zpath = os.path.join(tmp, "c.npz")
        np.savez(zpath, F=np.arange(6, dtype=np.float32).reshape(3, 2),
                 paths=np.array(paths, dtype=object),
                 digests=np.array(digests, dtype=object))
        z = np.load(zpath, allow_pickle=True)
        ver = DigestIndex(os.path.join(tmp, "d2.json"))
        have = {str(p): i for i, (p, d)
                in enumerate(zip(z["paths"], z["digests"]))
                if ver.digest(str(p)) == str(d)}
        assert have == {a: 0, b: 1}, f"unexpected have: {have}"

        # 6. legacy cache (no digests key) is treated as fully stale
        np.savez(os.path.join(tmp, "legacy.npz"),
                 F=np.zeros((1, 2), dtype=np.float32),
                 paths=np.array([a], dtype=object))
        lz = np.load(os.path.join(tmp, "legacy.npz"), allow_pickle=True)
        assert "digests" not in lz
        print("ALL 6 TEST GROUPS PASS")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
