CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_format TEXT NOT NULL,
  blocks_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  size_bytes INTEGER NOT NULL
);

CREATE TABLE comparisons (
  id TEXT PRIMARY KEY,
  a_document_id TEXT NOT NULL,
  b_document_id TEXT NOT NULL,
  options_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  blocks_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY (a_document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY (b_document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE INDEX idx_documents_expires_at ON documents(expires_at);
CREATE INDEX idx_comparisons_expires_at ON comparisons(expires_at);
CREATE INDEX idx_comparisons_a_document_id ON comparisons(a_document_id);
CREATE INDEX idx_comparisons_b_document_id ON comparisons(b_document_id);
