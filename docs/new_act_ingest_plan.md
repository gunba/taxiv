• Here’s a lightweight playbook the next agent can follow when onboarding a new
  act or a case/ruling dataset. I stopped short of detailing format-specific
  transforms (per your note); those requirements can slot into the highlighted
  “Act Adapter” / “Document Ingest Prep” sections.

  Act Ingestion Workflow

  - 1. Register metadata: Add an entry to config/datasets.json -> acts[]
    with id, title, description, exclusions.ref_ids, tokenizer hints, and
    ingestion.pipeline pointing at the act-specific runner.
  - 2. Scaffold an adapter: Create ingest/pipelines/<act_id>/ that exports a
    pipeline class extending BaseActPipeline (see ingest/pipelines/base_act.py)
    and implements run_phase_a (parse/raw transforms) and run_phase_b
    (GraphAnalyzer + DatabaseLoader + relatedness). Document any preprocessing
    requirements inside the module.
  - 3. Parser specifics: Place parser helpers (style maps, regexes, definition
    logic) in <act_id>/parser.py, keeping global state confined to that
    module. Only override what differs from ITAA 1997; reuse shared ingest/core
    utilities everywhere else.
  - 4. Config adapters: Mirroring ingest/pipelines/itaa1997/config.py, define
    a config class that declares file patterns, input directories, concurrency,
    media paths, etc. Use Config.ACT_ID everywhere instead of literal strings.
  - 5. Reference normalization & prompts: Update config/datasets.json tokenizer
    metadata (explicit prefixes, section gap handling) and extend any LLM
    prompt/normalization data files so the new act’s acronyms and quirks are
    recognized.
  - 6. Run pipeline: docker compose exec backend python -m

  - 1. Register dataset: Add a datasets[] entry to config/datasets.json with
    id, title, type: "document", description, and ingestion.input_dir pointing
    to the folder with raw files.
  - 3. Ingest: Run docker compose exec backend python -m
    ingest.pipelines.documents.run_pipeline (optionally set
  - 4. Surface data: /api/documents/search already returns snippets; front-end
    work can happen independently once the dataset is loaded.

  This keeps the process deterministic so a future agent can plug in your
  transformation specs and immediately know where to wire them.