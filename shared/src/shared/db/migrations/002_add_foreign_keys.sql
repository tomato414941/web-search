-- pg_only: true
-- Add FK constraints to documents-dependent tables.
-- Cleans up orphan rows first (required for FK to succeed).
-- Idempotent: checks for existing constraints before adding.

-- Clean orphan rows
DELETE FROM inverted_index WHERE url NOT IN (SELECT url FROM documents);
DELETE FROM page_embeddings WHERE url NOT IN (SELECT url FROM documents);
DELETE FROM page_ranks WHERE url NOT IN (SELECT url FROM documents);

-- Add FK constraints (only if not already present via schema)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'fk_inverted_index_documents' AND table_name = 'inverted_index'
  ) THEN
    ALTER TABLE inverted_index
      ADD CONSTRAINT fk_inverted_index_documents
      FOREIGN KEY (url) REFERENCES documents(url) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'fk_page_embeddings_documents' AND table_name = 'page_embeddings'
  ) THEN
    ALTER TABLE page_embeddings
      ADD CONSTRAINT fk_page_embeddings_documents
      FOREIGN KEY (url) REFERENCES documents(url) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'fk_page_ranks_documents' AND table_name = 'page_ranks'
  ) THEN
    ALTER TABLE page_ranks
      ADD CONSTRAINT fk_page_ranks_documents
      FOREIGN KEY (url) REFERENCES documents(url) ON DELETE CASCADE;
  END IF;
END $$;
