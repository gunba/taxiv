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
    * Word exports sometimes suffix style names (e.g., `ActHead 5,s`,
      `subsection,ss`). Normalize styles before comparing them against the
      configured `STYLE_MAP`, ignore lists, or formatting hints so the parser
      works for both Acts.
    * Section 6 of ITAA1936 includes subsections (1AA), (1) before the bold
      definitions. Configure `DEFINITION_SECTION_EXIT_STYLES` plus
      `DEFINITION_SECTION_EXIT_REQUIRES_CONTENT` so the parser stays inside the
      definition block long enough to capture every term but exits before the
      operative subsections begin.
  - 4. Config adapters: Mirroring ingest/pipelines/itaa1997/config.py, define
    a config class that declares file patterns, input directories, concurrency,
    media paths, etc. Use Config.ACT_ID everywhere instead of literal strings.
    For ITAA1936 we added Config.RAW_INPUT_DIR and pipe the AustLII RTF volumes
    through `ingest.core.conversion.convert_rtf_to_docx` so Phase A can keep
    consuming DOCX. Keep those converted artifacts under ingest/output/converted
    because all data files must remain ephemeral. LLM enrichment is currently
    disabled for this act until the reference extraction path stabilizes. When
    the raw sources live as RTF, persist a lightweight manifest
    (`ingest/output/converted/<act>/conversion_manifest.json`) with the source
    hashes so successive runs can skip redundant LibreOffice conversions.
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
