-- Initial Database Schema

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT,
    contact TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    client TEXT,
    project TEXT,
    service TEXT,
    status TEXT,
    deadline TEXT,
    waiting_on TEXT,
    follow_up TEXT,
    next_action TEXT,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    lead TEXT,
    contact TEXT,
    type TEXT,
    service_fit TEXT,
    status TEXT,
    score REAL,
    source TEXT,
    next_action TEXT,
    waiting_on TEXT,
    follow_up TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    campaign TEXT,
    audience TEXT,
    service TEXT,
    platforms TEXT,
    status TEXT,
    source_file TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS followups (
    id TEXT PRIMARY KEY,
    owner TEXT,
    subject TEXT,
    source TEXT,
    status TEXT,
    due TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    date TEXT,
    client TEXT,
    service TEXT,
    hours REAL,
    rate REAL,
    total REAL,
    status TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    type TEXT,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    status TEXT,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS enquiries (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    service TEXT,
    message TEXT,
    deadline TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS suggested_notes (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    source_cluster_queries TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    client TEXT,
    project TEXT,
    service TEXT,
    date TEXT,
    time TEXT,
    duration TEXT,
    location TEXT,
    status TEXT,
    rate REAL,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS expenses (
    id TEXT PRIMARY KEY,
    date TEXT,
    category TEXT,
    amount REAL,
    description TEXT,
    project TEXT,
    client TEXT,
    recurring TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS automix_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    status TEXT,
    genre TEXT,
    style_prefs TEXT,
    error_message TEXT,
    result_path TEXT,
    iteration_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS automix_job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tips_queries (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    confidence TEXT,
    topics TEXT,
    top_source TEXT,
    channel TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS tips_gaps (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    confidence TEXT,
    topics TEXT,
    top_source TEXT,
    channel TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS stem_uploads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_label TEXT,
    original_name TEXT,
    stored_name TEXT,
    size_bytes INTEGER,
    uploader_name TEXT,
    uploader_email TEXT,
    notes TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS demo_feedback (
    id TEXT PRIMARY KEY,
    question TEXT,
    rating TEXT,
    comment TEXT,
    answer TEXT,
    sources_json TEXT,
    topics_json TEXT,
    confidence TEXT,
    source_quality TEXT,
    session_id TEXT,
    channel TEXT,
    issue_tags_json TEXT,
    repair_status TEXT,
    repair_note TEXT,
    repair_checked_at TEXT,
    repair_last_answer TEXT,
    repair_last_sources_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS demo_questions (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    question TEXT,
    confidence TEXT,
    source_quality TEXT,
    top_source TEXT,
    source_count INTEGER,
    answer_chars INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS mix_feature_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    filename TEXT DEFAULT '',
    title TEXT DEFAULT '',
    version_label TEXT DEFAULT '',
    mix_goal_key TEXT DEFAULT '',
    feature_json TEXT NOT NULL,
    UNIQUE(review_id)
);

CREATE TABLE IF NOT EXISTS mix_feedback_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    note TEXT DEFAULT '',
    feature_json TEXT NOT NULL,
    UNIQUE(feedback_id)
);

CREATE TABLE IF NOT EXISTS mix_report_summaries (
    review_id TEXT PRIMARY KEY,
    report_name TEXT,
    title TEXT,
    created_at TEXT,
    version_label TEXT,
    score INTEGER,
    rating TEXT,
    peak_dbfs REAL,
    rms_dbfs_estimate REAL,
    crest_factor_db REAL,
    summary TEXT,
    flags_json TEXT,
    previous_version_json TEXT,
    version_comparison_json TEXT,
    version_advice_json TEXT,
    revision_impact_json TEXT,
    mix_critique_json TEXT,
    reference_json TEXT,
    comparison_json TEXT,
    comparison_advice_json TEXT,
    revision_agent_json TEXT,
    session_report_json TEXT,
    kenn_handoff_json TEXT,
    dominant_band TEXT,
    high_flag_count INTEGER DEFAULT 0,
    cached_at TEXT
);

CREATE TABLE IF NOT EXISTS mix_reviews (
    id TEXT PRIMARY KEY,
    title TEXT,
    original_name TEXT,
    stored_name TEXT,
    report_name TEXT,
    size_bytes INTEGER,
    created_at TEXT,
    status TEXT DEFAULT 'completed',
    error TEXT
);

CREATE TABLE IF NOT EXISTS mix_references (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    style TEXT,
    original_name TEXT,
    stored_name TEXT,
    metrics_json TEXT,
    size_bytes INTEGER,
    created_at TEXT
);
