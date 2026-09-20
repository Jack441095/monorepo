-- Recreate tables to add Foreign Key constraints and Indexes (removing name-based foreign keys)

PRAGMA foreign_keys=OFF;

-- 1. projects
CREATE TABLE IF NOT EXISTS projects_new (
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
INSERT OR IGNORE INTO projects_new (id, client, project, service, status, deadline, waiting_on, follow_up, next_action, source, created_at, updated_at)
SELECT id, client, project, service, status, deadline, waiting_on, follow_up, next_action, source, created_at, updated_at FROM projects;
DROP TABLE IF EXISTS projects;
ALTER TABLE projects_new RENAME TO projects;

-- 2. invoices
CREATE TABLE IF NOT EXISTS invoices_new (
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
INSERT OR IGNORE INTO invoices_new (id, date, client, service, hours, rate, total, status, notes, created_at, updated_at)
SELECT id, date, client, service, hours, rate, total, status, notes, created_at, updated_at FROM invoices;
DROP TABLE IF EXISTS invoices;
ALTER TABLE invoices_new RENAME TO invoices;

-- 3. sessions
CREATE TABLE IF NOT EXISTS sessions_new (
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
INSERT OR IGNORE INTO sessions_new (id, client, project, service, date, time, duration, location, status, rate, notes, created_at, updated_at)
SELECT id, client, project, service, date, time, duration, location, status, rate, notes, created_at, updated_at FROM sessions;
DROP TABLE IF EXISTS sessions;
ALTER TABLE sessions_new RENAME TO sessions;

-- 4. expenses
CREATE TABLE IF NOT EXISTS expenses_new (
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
INSERT OR IGNORE INTO expenses_new (id, date, category, amount, description, project, client, recurring, notes, created_at, updated_at)
SELECT id, date, category, amount, description, project, client, recurring, notes, created_at, updated_at FROM expenses;
DROP TABLE IF EXISTS expenses;
ALTER TABLE expenses_new RENAME TO expenses;

-- 5. automix_jobs
-- project_id identifies an Automix upload workspace. It may refer to a CRM project,
-- but the upload workflow deliberately also supports standalone project identifiers.
CREATE TABLE IF NOT EXISTS automix_jobs_new (
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
INSERT OR IGNORE INTO automix_jobs_new (id, project_id, status, genre, style_prefs, error_message, result_path, iteration_count, created_at, updated_at)
SELECT id, project_id, status, genre, style_prefs, error_message, result_path, iteration_count, created_at, updated_at FROM automix_jobs;
DROP TABLE IF EXISTS automix_jobs;
ALTER TABLE automix_jobs_new RENAME TO automix_jobs;

-- 6. automix_job_events (job_id REFERENCES automix_jobs(id) is ID-based and correct!)
CREATE TABLE IF NOT EXISTS automix_job_events_new (
    id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES automix_jobs(id) ON DELETE CASCADE,
    status TEXT,
    message TEXT,
    created_at TEXT,
    updated_at TEXT
);
INSERT OR IGNORE INTO automix_job_events_new (id, job_id, status, message, created_at, updated_at)
SELECT id, job_id, status, message, created_at, updated_at FROM automix_job_events;
DROP TABLE IF EXISTS automix_job_events;
ALTER TABLE automix_job_events_new RENAME TO automix_job_events;

PRAGMA foreign_keys=ON;

-- Indexes on foreign keys
CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client);
CREATE INDEX IF NOT EXISTS idx_invoices_client ON invoices(client);
CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_expenses_client ON expenses(client);
CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses(project);
CREATE INDEX IF NOT EXISTS idx_automix_jobs_project ON automix_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_automix_job_events_job ON automix_job_events(job_id);
