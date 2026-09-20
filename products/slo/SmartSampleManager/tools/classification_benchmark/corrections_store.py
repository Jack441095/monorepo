#!/usr/bin/env python3
"""
Task 3 -- local correction store for active learning.

When a user rejects or edits a suggestion, that is the most valuable signal SLO
can receive: a by-ear label on a file the model got wrong, from the deployment
distribution rather than a curated sample. This stores those corrections
locally, safely, and in a form that can later be promoted to ground truth.

Design constraints, all of them safety constraints:

  * NO AUDIO IS STORED. Only a path, a content hash and metadata. The store can
    be shared or inspected without moving a single licensed sample.
  * NOTHING IS OVERWRITTEN. Corrections are append-only. A user changing their
    mind writes a new row; the earlier one stays. History is evidence.
  * NOT AUTOMATICALLY TRUSTED. Corrections land as `pending` and become
    ground-truth candidates only through explicit promotion. A user mis-clicking
    must never silently rewrite the dataset.
  * VERSIONED AGAINST THE MODEL. Every row records the taxonomy, policy and
    model version that produced the original prediction, so a correction made
    against an old model is not silently treated as a correction of a new one.

SQLite, because it is in the standard library, is a single file, survives
crashes mid-write, and needs no service.
"""
import os, csv, json, sqlite3, hashlib, time, argparse

SD = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(SD, "slo_corrections.db")
SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS corrections (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  created_utc       TEXT NOT NULL,
  file_path         TEXT NOT NULL,
  content_sha256    TEXT,
  original_action   TEXT NOT NULL,
  original_label    TEXT,
  original_conf     REAL,
  corrected_label   TEXT,
  corrected_subtype TEXT,
  user_note         TEXT,
  taxonomy_version  TEXT,
  policy_version    TEXT,
  model_version     TEXT,
  arm               TEXT,
  status            TEXT NOT NULL DEFAULT 'pending',
  promoted_utc      TEXT
);
CREATE INDEX IF NOT EXISTS ix_corr_path   ON corrections(file_path);
CREATE INDEX IF NOT EXISTS ix_corr_status ON corrections(status);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(db=DB):
    c = sqlite3.connect(db)
    c.executescript(DDL)
    c.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version',?)",
              (str(SCHEMA_VERSION),))
    c.commit()
    return c


def record(conn, *, file_path, original_action, original_label=None,
           original_conf=None, corrected_label=None, corrected_subtype=None,
           user_note=None, taxonomy_version="1.1.0", policy_version="1.0.0",
           model_version="centroid-perchclap-mw-v1", arm="multi-window audio",
           content_sha256=None):
    """Append one correction. Never updates an existing row."""
    conn.execute(
        "INSERT INTO corrections (created_utc,file_path,content_sha256,"
        "original_action,original_label,original_conf,corrected_label,"
        "corrected_subtype,user_note,taxonomy_version,policy_version,"
        "model_version,arm,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
        (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), file_path,
         content_sha256, original_action, original_label, original_conf,
         corrected_label, corrected_subtype, user_note, taxonomy_version,
         policy_version, model_version, arm))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def promote(conn, ids):
    """Explicitly mark corrections as ground-truth candidates. Never automatic."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.executemany("UPDATE corrections SET status='promoted',promoted_utc=? "
                     "WHERE id=? AND status='pending'", [(now, i) for i in ids])
    conn.commit()
    return conn.total_changes


def export_csv(conn, out, status=None):
    q = "SELECT * FROM corrections" + (" WHERE status=?" if status else "")
    cur = conn.execute(q, (status,) if status else ())
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    return len(rows)


def stats(conn):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM corrections GROUP BY status")}


def self_test():
    import tempfile, shutil
    tmp = tempfile.mkdtemp(); db = os.path.join(tmp, "t.db")
    c = connect(db)
    ok = True
    i1 = record(c, file_path="/x/a.wav", original_action="suggest",
                original_label="Snare", original_conf=0.7,
                corrected_label="Rimshot", user_note="it's a rim")
    i2 = record(c, file_path="/x/a.wav", original_action="suggest",
                original_label="Snare", corrected_label="Clap",
                user_note="changed my mind")
    n = c.execute("SELECT COUNT(*) FROM corrections WHERE file_path='/x/a.wav'").fetchone()[0]
    ok &= (n == 2); print(f"  {'PASS' if n==2 else 'FAIL'}  append-only: a changed mind adds a row ({n})")
    st = stats(c); ok &= st.get("pending") == 2
    print(f"  {'PASS' if st.get('pending')==2 else 'FAIL'}  new corrections are 'pending', not trusted")
    promote(c, [i1])
    st = stats(c); good = st.get("promoted") == 1 and st.get("pending") == 1
    ok &= good; print(f"  {'PASS' if good else 'FAIL'}  promotion is explicit and per-row {st}")
    cols = [d[1] for d in c.execute("PRAGMA table_info(corrections)")]
    noaudio = not any("audio" in x or "blob" in x for x in cols)
    ok &= noaudio; print(f"  {'PASS' if noaudio else 'FAIL'}  no audio column exists")
    for f in ("taxonomy_version", "policy_version", "model_version"):
        ok &= f in cols
    print(f"  {'PASS' if all(f in cols for f in ('taxonomy_version','policy_version','model_version')) else 'FAIL'}  every row is version-stamped")
    out = os.path.join(tmp, "e.csv"); k = export_csv(c, out)
    ok &= k == 2; print(f"  {'PASS' if k==2 else 'FAIL'}  exportable to CSV ({k} rows)")
    c.close(); shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--export")
    a = ap.parse_args()
    if a.self_test:
        print("corrections store self-test:")
        raise SystemExit(self_test())
    c = connect()
    if a.export:
        print(f"exported {export_csv(c, a.export)} rows -> {a.export}")
    else:
        print(f"{DB}: {stats(c) or 'empty'}")
