-- Proveniência de cada indexação: de qual branch/commit e quem disparou.
-- Ver docs/03-modelo-de-dados.md e docs/12-git-sync.md.

ALTER TABLE index_runs ADD COLUMN git_branch TEXT;
ALTER TABLE index_runs ADD COLUMN git_commit TEXT;
ALTER TABLE index_runs ADD COLUMN git_dirty  INTEGER;
ALTER TABLE index_runs ADD COLUMN source     TEXT NOT NULL DEFAULT 'cli';
