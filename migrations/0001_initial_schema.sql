-- 0001_initial_schema: tables, constraints, indexes and triggers of the
-- ingestion record (F3, specs/postgres-persistence).
--
-- AC5 = the database refuses a row that breaks a structural rule.
-- AC6 = the database refuses to change or remove what was recorded.
--
-- The runner applies this file inside one transaction together with its
-- bookkeeping row, so this file holds no transaction control and changes no
-- session setting. Every name is unqualified (the connection's default schema).


-- =========================================================================
-- ingestion_run: one row per ingestion execution (identity, scope, outcome)
-- =========================================================================

CREATE TABLE ingestion_run (
    execution_id text        NOT NULL,
    scope        jsonb       NOT NULL,
    started_at   timestamptz NOT NULL,
    finished_at  timestamptz,
    status       text        NOT NULL,

    -- AC5: the identity is unique and never reused.
    CONSTRAINT ingestion_run_pkey PRIMARY KEY (execution_id),

    -- AC5: same rule as the domain's validate_execution_id (1 to 64 characters,
    -- lowercase letters, digits and hyphens, no leading hyphen). PostgreSQL's
    -- $ does not accept a trailing newline, so "abc\n" is refused.
    CONSTRAINT ingestion_run_execution_id_format
        CHECK (execution_id ~ '^[a-z0-9][a-z0-9-]{0,63}$'),

    -- AC5: a scope is a JSON object, never an array, a scalar or null.
    CONSTRAINT ingestion_run_scope_is_object
        CHECK (jsonb_typeof(scope) = 'object'),

    -- AC5: only the three known statuses.
    CONSTRAINT ingestion_run_status_known
        CHECK (status IN ('running', 'succeeded', 'failed')),

    -- AC5: a finish time exists exactly when the run is no longer running.
    CONSTRAINT ingestion_run_finished_at_matches_status
        CHECK ((finished_at IS NULL) = (status = 'running')),

    -- AC5: a run does not finish before it started.
    CONSTRAINT ingestion_run_finished_after_started
        CHECK (finished_at >= started_at)
);


-- =========================================================================
-- raw_evidence: one row per distinct stored content (by content hash)
-- =========================================================================

CREATE TABLE raw_evidence (
    content_hash text   NOT NULL,
    size         bigint NOT NULL,

    -- AC5: one row per content; the same bytes are recorded once.
    CONSTRAINT raw_evidence_pkey PRIMARY KEY (content_hash),

    -- AC5: a SHA-256 in lowercase hexadecimal, exactly 64 characters.
    CONSTRAINT raw_evidence_content_hash_format
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),

    -- AC5: a size is never negative (empty content is size 0).
    CONSTRAINT raw_evidence_size_not_negative
        CHECK (size >= 0)
);


-- =========================================================================
-- observation: one row per captured response of a run (by run and sequence)
-- The size is not stored here; it is read from raw_evidence by join.
-- =========================================================================

CREATE TABLE observation (
    execution_id text        NOT NULL,
    sequence     integer     NOT NULL,
    method       text        NOT NULL,
    url          text        NOT NULL,
    status       integer     NOT NULL,
    headers      jsonb       NOT NULL,
    captured_at  timestamptz NOT NULL,
    content_hash text        NOT NULL,

    -- AC5: one observation per run and sequence number.
    CONSTRAINT observation_pkey PRIMARY KEY (execution_id, sequence),

    -- AC5: an observation belongs to an existing run.
    CONSTRAINT observation_execution_id_fkey
        FOREIGN KEY (execution_id) REFERENCES ingestion_run (execution_id),

    -- AC5: an observation points to content that was recorded.
    CONSTRAINT observation_content_hash_fkey
        FOREIGN KEY (content_hash) REFERENCES raw_evidence (content_hash),

    -- AC5: sequence numbers start at 0.
    CONSTRAINT observation_sequence_not_negative
        CHECK (sequence >= 0),

    -- AC5: method and URL are never empty.
    CONSTRAINT observation_method_not_empty
        CHECK (method <> ''),
    CONSTRAINT observation_url_not_empty
        CHECK (url <> ''),

    -- AC5: an HTTP status code, 100 to 599.
    CONSTRAINT observation_status_is_http
        CHECK (status BETWEEN 100 AND 599),

    -- AC5: headers are a JSON array. In addition, the database refuses any
    -- element whose first value is Set-Cookie, in any letter case (it also
    -- guards the rule that a cookie value is never persisted).
    -- The full [name, value] shape of each pair and the types of its two
    -- values stay the responsibility of the domain and the adapter.
    CONSTRAINT observation_headers_array_without_set_cookie
        CHECK (
            jsonb_typeof(headers) = 'array'
            AND NOT jsonb_path_exists(
                headers,
                '$[*][0] ? (@ like_regex "^set-cookie$" flag "i")'
            )
        )
);

-- Lookup by content: which observations obtained this content.
CREATE INDEX observation_content_hash_idx ON observation (content_hash);


-- =========================================================================
-- audit_event: facts appended to a run's history, in order of insertion
-- =========================================================================

CREATE TABLE audit_event (
    -- AC5: the database assigns the identity; an explicit value is refused.
    event_id     bigint      GENERATED ALWAYS AS IDENTITY,
    execution_id text        NOT NULL,
    occurred_at  timestamptz NOT NULL,
    event_type   text        NOT NULL,
    detail       jsonb       NOT NULL DEFAULT '{}',

    CONSTRAINT audit_event_pkey PRIMARY KEY (event_id),

    -- AC5: an event belongs to an existing run.
    CONSTRAINT audit_event_execution_id_fkey
        FOREIGN KEY (execution_id) REFERENCES ingestion_run (execution_id),

    -- AC5: an event has a type.
    CONSTRAINT audit_event_event_type_not_empty
        CHECK (event_type <> ''),

    -- AC5: a detail is a JSON object (empty by default).
    CONSTRAINT audit_event_detail_is_object
        CHECK (jsonb_typeof(detail) = 'object')
);

-- Reading a run's events by run.
CREATE INDEX audit_event_execution_id_idx ON audit_event (execution_id);


-- =========================================================================
-- Triggers (AC6): what was recorded is not changed or removed.
-- Every refusal raises SQLSTATE 23000 (integrity_constraint_violation). The
-- message names the operation and the table only, never a row value.
-- (BEGIN and END below delimit PL/pgSQL function bodies; they are not
-- transaction control.)
-- A superuser or the table owner can still disable a trigger; these protect
-- against ordinary statements, not against someone who owns the schema.
-- =========================================================================

-- AC6: always refuses. Attached below as a row trigger for UPDATE and DELETE
-- and as a statement trigger for TRUNCATE.
CREATE FUNCTION reject_modification() RETURNS trigger
    LANGUAGE plpgsql
    AS $function$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '23000',
        MESSAGE = TG_OP || ' is not allowed on ' || TG_TABLE_NAME;
END;
$function$;

-- AC6: the one change allowed on ingestion_run is the end of a run:
-- running -> succeeded or failed, with execution_id, scope and started_at
-- unchanged. (The check constraints above then require finished_at.)
CREATE FUNCTION ingestion_run_allow_finish_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $function$
BEGIN
    IF OLD.status = 'running'
        AND NEW.status IN ('succeeded', 'failed')
        AND NEW.execution_id IS NOT DISTINCT FROM OLD.execution_id
        AND NEW.scope IS NOT DISTINCT FROM OLD.scope
        AND NEW.started_at IS NOT DISTINCT FROM OLD.started_at
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING
        ERRCODE = '23000',
        MESSAGE = TG_OP || ' is not allowed on ' || TG_TABLE_NAME;
END;
$function$;

-- AC6: raw_evidence is append-only (no UPDATE, DELETE or TRUNCATE).
CREATE TRIGGER raw_evidence_no_change
    BEFORE UPDATE OR DELETE ON raw_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_modification();
CREATE TRIGGER raw_evidence_no_truncate
    BEFORE TRUNCATE ON raw_evidence
    FOR EACH STATEMENT EXECUTE FUNCTION reject_modification();

-- AC6: observation is append-only (no UPDATE, DELETE or TRUNCATE).
CREATE TRIGGER observation_no_change
    BEFORE UPDATE OR DELETE ON observation
    FOR EACH ROW EXECUTE FUNCTION reject_modification();
CREATE TRIGGER observation_no_truncate
    BEFORE TRUNCATE ON observation
    FOR EACH STATEMENT EXECUTE FUNCTION reject_modification();

-- AC6: audit_event is append-only (no UPDATE, DELETE or TRUNCATE).
CREATE TRIGGER audit_event_no_change
    BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION reject_modification();
CREATE TRIGGER audit_event_no_truncate
    BEFORE TRUNCATE ON audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION reject_modification();

-- AC6: ingestion_run rows are never deleted or truncated.
CREATE TRIGGER ingestion_run_no_delete
    BEFORE DELETE ON ingestion_run
    FOR EACH ROW EXECUTE FUNCTION reject_modification();
CREATE TRIGGER ingestion_run_no_truncate
    BEFORE TRUNCATE ON ingestion_run
    FOR EACH STATEMENT EXECUTE FUNCTION reject_modification();

-- AC6: ingestion_run may be updated only to end a run (see the function).
CREATE TRIGGER ingestion_run_only_finish
    BEFORE UPDATE ON ingestion_run
    FOR EACH ROW EXECUTE FUNCTION ingestion_run_allow_finish_only();

-- AC6, note: a plain TRUNCATE of raw_evidence or ingestion_run, which other
-- tables reference, may be refused by PostgreSQL's own foreign key check
-- (SQLSTATE 0A000) before the triggers run. Either way nothing changes.
-- TRUNCATE ... CASCADE reaches the triggers of the referencing tables and is
-- refused with 23000.
