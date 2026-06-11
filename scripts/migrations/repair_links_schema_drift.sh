#!/usr/bin/env bash
set -euo pipefail

# One-shot repair for issues/links-physical-schema-drift.md
#
# Rebuilds `links` as a deduplicated table and restores the migration-baseline
# schema: NOT NULL columns, PRIMARY KEY (src, dst), idx_links_src, idx_links_dst.
#
# Strategy (disk-bound, ~25GB source table):
#   1. load distinct rows into links_new in 8 hash-partitioned batches
#      (bounds sort temp space; partitions are disjoint so the union is distinct)
#   2. verify links_new matches the distinct row set of links on a random sample
#   3. drop the old table to free disk BEFORE building indexes
#   4. build primary key and secondary indexes, rename to canonical names
#
# If the script fails after step 3, links_new still holds the full deduplicated
# data; the remaining steps can be rerun manually.
#
# Preconditions:
#   - all links writers and readers are stopped
#     (crawler, web-model-maintenance-worker)
#   - free disk >= old table size + new table size (~45GB for current PRD)
#
# Usage:
#   PSQL="psql $DATABASE_URL" ./repair_links_schema_drift.sh
#   PSQL="docker exec -i <postgres-container> psql -U websearch -d websearch" \
#     ./repair_links_schema_drift.sh

PSQL="${PSQL:?Set PSQL to a psql command line, e.g. PSQL=\"psql \$DATABASE_URL\"}"
MAINT_MEM="${MAINT_MEM:-256MB}"
BATCHES=8

SQL_FILE="$(mktemp /tmp/repair_links_XXXX.sql)"
trap 'rm -f "$SQL_FILE"' EXIT

{
cat <<SQL
\\timing on
SET statement_timeout = 0;
SET maintenance_work_mem = '${MAINT_MEM}';

-- Preflight: refuse to run if already repaired or a previous run left state.
DO \$\$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'links'::regclass) THEN
    RAISE EXCEPTION 'links already has a constraint; nothing to repair';
  END IF;
  IF to_regclass('links_new') IS NOT NULL THEN
    RAISE EXCEPTION 'links_new already exists; clean up before rerunning';
  END IF;
END
\$\$;

SELECT n_live_tup AS old_estimated_rows,
       pg_size_pretty(pg_total_relation_size('links')) AS old_total_size
FROM pg_stat_user_tables WHERE relname = 'links';

CREATE TABLE links_new (
    src TEXT NOT NULL,
    dst TEXT NOT NULL
);
SQL

for ((k = 0; k < BATCHES; k++)); do
cat <<SQL
\\echo === batch ${k}/$((BATCHES - 1)) ===
INSERT INTO links_new
SELECT DISTINCT src, dst
FROM links
WHERE src IS NOT NULL
  AND dst IS NOT NULL
  AND (hashtextextended(src, 0) & $((BATCHES - 1))) = ${k};
SQL
done

cat <<SQL
SELECT count(*) AS new_rows FROM links_new;

-- Verify: for ~200 random sources, the distinct edge set must be identical.
\\echo === sample verification ===
DO \$\$
DECLARE bad integer;
BEGIN
  WITH s AS (
    SELECT DISTINCT src FROM links TABLESAMPLE SYSTEM (0.001)
    WHERE src IS NOT NULL LIMIT 200
  ),
  o AS (
    SELECT l.src, l.dst FROM links l JOIN s USING (src)
    WHERE l.dst IS NOT NULL
    GROUP BY l.src, l.dst
  ),
  n AS (
    SELECT l.src, l.dst FROM links_new l JOIN s USING (src)
  )
  SELECT count(*) INTO bad FROM (
    (TABLE o EXCEPT TABLE n) UNION ALL (TABLE n EXCEPT TABLE o)
  ) diff;
  IF bad > 0 THEN
    RAISE EXCEPTION 'links_new does not match links on sample: % differing rows', bad;
  END IF;
  RAISE NOTICE 'sample verification passed';
END
\$\$;

-- Point of no return: free disk before index builds.
\\echo === dropping old table ===
DROP TABLE links;

\\echo === building primary key ===
ALTER TABLE links_new ADD CONSTRAINT links_pkey PRIMARY KEY (src, dst);
\\echo === building idx_links_src ===
CREATE INDEX idx_links_src ON links_new (src);
\\echo === building idx_links_dst ===
CREATE INDEX idx_links_dst ON links_new (dst);

ALTER TABLE links_new RENAME TO links;
ANALYZE links;

SELECT pg_size_pretty(pg_table_size('links')) AS table_size,
       pg_size_pretty(pg_indexes_size('links')) AS index_size;
\\d links
SQL
} > "$SQL_FILE"

echo "Running repair via: ${PSQL}"
${PSQL} -v ON_ERROR_STOP=1 < "$SQL_FILE"
echo "Repair completed."
