-- Banco de ORQUESTRAÇÃO. Separado do knowledge.db de propósito (ADR-0014):
-- aqui a escrita é contínua e o histórico tem valor; lá a escrita é em lote e
-- tudo é derivado. `ragx vacuum` roda VACUUM, que bloqueia o banco inteiro —
-- com os dois juntos, ou o vacuum falha ou o worker trava.

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ── definição do trabalho (VERSIONADA em knowledge/tasks/) ──────────────
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    request         TEXT NOT NULL,
    classification  TEXT NOT NULL,
    complexity      TEXT NOT NULL,
    strategy        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','paused','completed','cancelled')),
    analysis_json   TEXT NOT NULL DEFAULT '{}',
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id                      TEXT PRIMARY KEY,
    project_id              TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_task_id          TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    seq                     INTEGER NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    type                    TEXT NOT NULL DEFAULT 'technical',
    track                   TEXT NOT NULL DEFAULT 'backend',
    status                  TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','ready','queued','running','blocked',
                                              'waiting_approval','failed','retrying',
                                              'completed','cancelled','skipped')),
    priority                TEXT NOT NULL DEFAULT 'medium'
                            CHECK (priority IN ('low','medium','high','critical')),
    priority_rank           INTEGER NOT NULL DEFAULT 2,
    complexity              TEXT NOT NULL DEFAULT 'medium',
    acceptance_criteria     TEXT NOT NULL DEFAULT '[]',
    required_context        TEXT NOT NULL DEFAULT '[]',
    required_skills         TEXT NOT NULL DEFAULT '[]',
    files_scope             TEXT NOT NULL DEFAULT '[]',
    security_requirements   TEXT NOT NULL DEFAULT '[]',
    performance_requirements TEXT NOT NULL DEFAULT '[]',
    test_requirements       TEXT NOT NULL DEFAULT '[]',
    agent                   TEXT,
    requires_approval       INTEGER NOT NULL DEFAULT 0,
    -- execução: NUNCA versionado (ADR-0014)
    retry_count             INTEGER NOT NULL DEFAULT 0,
    max_retries             INTEGER NOT NULL DEFAULT 3,
    last_error              TEXT,
    next_retry_at           TEXT,
    locked_by               TEXT,
    locked_at               TEXT,
    lock_expires_at         TEXT,
    started_at              TEXT,
    completed_at            TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

-- A fila é uma consulta só; estes índices são o que a mantêm assim.
CREATE INDEX IF NOT EXISTS idx_tasks_status_prio   ON tasks(status, priority_rank DESC, seq);
CREATE INDEX IF NOT EXISTS idx_tasks_project       ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent        ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lock          ON tasks(lock_expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_retry         ON tasks(next_retry_at);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id            TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind               TEXT NOT NULL DEFAULT 'depends_on'
                       CHECK (kind IN ('depends_on','blocks','blocked_by',
                                       'parent','child','related_to')),
    created_at         TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on_task_id, kind),
    CHECK (task_id <> depends_on_task_id)
);
CREATE INDEX IF NOT EXISTS idx_dep_task    ON task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_dep_on      ON task_dependencies(depends_on_task_id);

-- ── execução (LOCAL, nunca versionada) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS task_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    attempt       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running','completed','failed','released','expired')),
    agent         TEXT,
    claimed_by    TEXT,
    context_hash  TEXT,
    context_tokens INTEGER NOT NULL DEFAULT 0,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    duration_ms   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON task_runs(task_id, status);

CREATE TABLE IF NOT EXISTS task_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
    task_id    TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    number     INTEGER NOT NULL,
    outcome    TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON task_attempts(task_id);

CREATE TABLE IF NOT EXISTS task_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id     INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    level      TEXT NOT NULL DEFAULT 'info',
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_task ON task_logs(task_id, created_at);

CREATE TABLE IF NOT EXISTS task_artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id     INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    rel_path   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_task ON task_artifacts(task_id);

CREATE TABLE IF NOT EXISTS task_context (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id       INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    tokens       INTEGER NOT NULL DEFAULT 0,
    sources      TEXT NOT NULL DEFAULT '[]',
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_task ON task_context(task_id);

CREATE TABLE IF NOT EXISTS task_results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id     INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    summary    TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL DEFAULT '{}',
    valid      INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_task ON task_results(task_id);

CREATE TABLE IF NOT EXISTS task_errors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id     INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    -- 'execution' e 'validation' recebem tratamento diferente no retry:
    -- repetir um resultado inválido raramente adianta.
    kind       TEXT NOT NULL DEFAULT 'execution'
               CHECK (kind IN ('execution','validation','timeout','lease_expired','internal')),
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_errors_task ON task_errors(task_id);

-- Trilha append-only. É a resposta para "por que esta tarefa está assim".
CREATE TABLE IF NOT EXISTS task_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    from_state TEXT,
    to_state   TEXT,
    actor      TEXT,
    detail     TEXT NOT NULL DEFAULT '',
    consumed   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_open ON task_events(consumed, created_at);

-- ── agentes ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    tracks      TEXT NOT NULL DEFAULT '[]',
    skills      TEXT NOT NULL DEFAULT '[]',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT,
    task_id     TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    run_id      INTEGER REFERENCES task_runs(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs ON agent_runs(agent_id, created_at);

-- ── agendamento ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schedules (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id) ON DELETE CASCADE,
    task_id         TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id        TEXT,
    schedule_type   TEXT NOT NULL DEFAULT 'cron'
                    CHECK (schedule_type IN ('once','cron','interval','dependency','event','manual')),
    cron_expression TEXT,
    interval_s      INTEGER,
    event_type      TEXT,
    next_run_at     TEXT,
    last_run_at     TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sched_next ON schedules(enabled, next_run_at);

-- ── conhecimento planejado ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    task_id     TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    doc_type    TEXT NOT NULL,
    title       TEXT NOT NULL,
    rel_path    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','drafted','written','indexed','obsolete')),
    grounding   TEXT NOT NULL DEFAULT '[]',
    gaps        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kdocs_project ON knowledge_documents(project_id, status);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    tokens       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kver_doc ON knowledge_versions(document_id);

CREATE TABLE IF NOT EXISTS decisions (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id) ON DELETE SET NULL,
    task_id      TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    title        TEXT NOT NULL,
    context      TEXT NOT NULL DEFAULT '',
    problem      TEXT NOT NULL DEFAULT '',
    options      TEXT NOT NULL DEFAULT '[]',
    decision     TEXT NOT NULL DEFAULT '',
    consequences TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed','accepted','superseded','obsolete')),
    rel_path     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    requested_at TEXT NOT NULL,
    decided_at  TEXT,
    decided_by  TEXT,
    granted     INTEGER,
    reason      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);
