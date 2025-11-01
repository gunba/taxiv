import os
import json
import re
import traceback
import time
import csv
import sqlite3 # Import SQLite3

# Import necessary libraries.
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    print("Warning: networkx not found. Graph analysis (PageRank) will be disabled.")
    NETWORKX_AVAILABLE = False
    # Define a mock if not available
    class MockNX:
        def DiGraph(self): return self
        def add_node(self, *args, **kwargs): pass
        def add_nodes_from(self, *args, **kwargs): pass
        def add_edge(self, *args, **kwargs): pass
        def edges(self, *args, **kwargs): return []
        def number_of_nodes(self): return 0
        def in_degree(self, node): return 0
        def out_degree(self, node): return 0
        def pagerank(self, *args, **kwargs): return {}
        @property
        def nodes(self):
            class MockNodes:
                def __getitem__(self, key): return {}
                def update(self, *args, **kwargs): pass
                def __call__(self, *args, **kwargs): return []
            return MockNodes()
    nx = MockNX()

# NOTE: Firebase dependencies (firebase_admin) have been removed.

# Configuration
# If running from the directory containing the 'itaa1997-processed' folder:
BASE_DIR = "."
INPUT_DIR = os.path.join(BASE_DIR, "itaa1997-processed")
OUTPUT_DIR = os.path.join(BASE_DIR, "itaa1997-processed")

FILE_PATTERN = "ITAA1997_VOL{}_gemini_concurrent.json"
DEFINITIONS_FILE_PATTERN = "definitions_995_1_gemini_concurrent.json"
ACT_ID = "ITAA1997"
LOG_FILENAME = "unresolved_internal_references_log_v2.csv"

# New Local Output Configuration
OUTPUT_JSON_FILENAME = "ITAA1997_database.json"
OUTPUT_SQLITE_DB = "ITAA1997.db"


# Global structures
G = nx.DiGraph() if NETWORKX_AVAILABLE else MockNX().DiGraph()
node_registry = {}
id_type_registry = {}
reverse_references = {}
skipped_placeholders_log = []
semantic_mismatches_corrected = 0

# --- Regex and Mappings Definitions ---

# Regex to extract the core ID (Handles 104-5, 83A-10, 94J, 159GK, III, IV)
ID_EXTRACTION_REGEX = re.compile(r'([0-9]+[A-Z]*-[0-9A-Z]+|[0-9]+[A-Z]*|[IVXLCDM]+)')

# Heuristic for ITAA1936 pattern (digit(s) followed by letter(s), NOT hyphenated)
ITAA1936_HEURISTIC_REGEX = re.compile(r'^[0-9]+[A-Z]+$')

# Mappings for contextual Act detection in snippets
ACT_MAPPINGS = {
    "Taxation Administration Act 1953": "TAA1953",
    "TAA 1953": "TAA1953",
    "Income Tax Assessment Act 1936": "ITAA1936",
    "ITAA 1936": "ITAA1936",
    "GST Act": "GSTA1999",
    "A New Tax System (Goods and Services Tax) Act 1999": "GSTA1999",
    "Income Tax (Transitional Provisions) Act 1997": "ITTPA1997",
    "Fringe Benefits Tax Assessment Act 1986": "FBTAA1986",
    "Income Tax Rates Act 1986": "ITRA1986",
    "Venture Capital Act 2002": "VCA2002",
    "Wine Tax Act": "WETA1999",
    "Luxury Car Tax Act": "LCTA1999",
}

# --- End Definitions ---

# initialize_firebase() function removed.

def generate_internal_id(node=None, parent_internal_id=None, ref_id_override=None):
    """
    Generates a unique internal ID (Document ID/Primary Key).
    """
    ref_id_to_use = ref_id_override if ref_id_override else (node.get("ref_id") if node else None)

    if ref_id_to_use:
        # Sanitize both ':' and '/'
        sanitized_id = ref_id_to_use.replace(":", "_").replace("/", "_")
        return sanitized_id

    # Generate derived ID for elements without canonical IDs (Guides, etc.)
    if node:
        prefix = parent_internal_id if parent_internal_id else f"{ACT_ID}_Root"
        safe_title = re.sub(r'[^\w\-]+', '_', node.get("title", "UnnamedElement"))
        # Use a timestamp to ensure uniqueness if titles collide
        return f"{prefix}_Element_{safe_title[:80]}_{time.time_ns()}"

    return f"UnknownID_{time.time_ns()}"

# --- PASS 1: Build Structure and Type Registry (Unchanged from previous version) ---
def load_data_and_build_structure():
    """
    PASS 1: Loads JSON files, builds hierarchy, and populates id_type_registry.
    """
    print("\n=== PASS 1: Building Structure and Type Registry ===")

    processed_files = 0

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    def process_node_pass1(node, parent_internal_id=None, hierarchy_path="/"):
        internal_id = generate_internal_id(node, parent_internal_id)

        is_new_definition = internal_id not in node_registry

        if is_new_definition:
            node_registry[internal_id] = node.copy()
            if internal_id not in G:
                G.add_node(internal_id)

            # Calculate Hierarchy Path
            current_hierarchy_path = hierarchy_path
            node_type = node.get("type")
            node_id = node.get("id")
            if node_type and node_id:
                # Sanitize ID for path
                sanitized_path_id = str(node_id).replace("/", "_")
                current_hierarchy_path += f"{node_type}:{sanitized_path_id}/"

                # --- Populate id_type_registry ---
                # Convert ID to string for consistent lookup
                str_node_id = str(node_id)
                if str_node_id not in id_type_registry:
                    id_type_registry[str_node_id] = node_type
                # Prioritize structural types over 'Definition' if ID is reused
                elif id_type_registry[str_node_id] != node_type:
                    if node_type != 'Definition' and id_type_registry[str_node_id] == 'Definition':
                        id_type_registry[str_node_id] = node_type

            node_registry[internal_id]["hierarchy_path"] = current_hierarchy_path
            node_registry[internal_id]["parent_internal_id"] = parent_internal_id

            # Add CONTAINS Edge
            if parent_internal_id:
                G.add_edge(parent_internal_id, internal_id, type='CONTAINS')
        else:
            current_hierarchy_path = node_registry[internal_id].get("hierarchy_path", hierarchy_path)

        # Recurse into children
        for child in node.get("children", []):
            process_node_pass1(child, internal_id, current_hierarchy_path)

    # Determine search directory
    input_search_dir = INPUT_DIR if os.path.exists(INPUT_DIR) else BASE_DIR

    # --- Load Volume Files ---
    for i in range(1, 11):
        volume_num = f"{i:02d}"
        filepath = os.path.join(input_search_dir, FILE_PATTERN.format(volume_num))

        if os.path.exists(filepath):
            print(f"Processing VOL{volume_num} (Pass 1)...")
            processed_files += 1
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    process_node_pass1(item)
            except Exception as e:
                print(f"Error (Pass 1) processing {filepath}: {e}")
                traceback.print_exc()

    # --- Load Definitions File ---
    def_filepath = os.path.join(input_search_dir, DEFINITIONS_FILE_PATTERN)
    if os.path.exists(def_filepath):
        print(f"Processing Definitions File (Pass 1)...")
        processed_files += 1
        try:
            with open(def_filepath, 'r', encoding='utf-8') as f:
                definitions_data = json.load(f)

            # Attempt to find the parent (Section 995-1)
            parent_internal_id = generate_internal_id(ref_id_override="ITAA1997:Section:995-1")
            if parent_internal_id not in node_registry:
                parent_internal_id = None
                parent_hierarchy_path = "/"
            else:
                parent_hierarchy_path = node_registry[parent_internal_id].get("hierarchy_path", "/")

            for term, data in definitions_data.items():
                # Sanitize term for use in ref_id AND the registry key (node 'id')
                # We must be careful with sanitization to ensure lookups work
                sanitized_term_for_id = re.sub(r'[^\w\-]+', '_', term)
                if not sanitized_term_for_id:
                    sanitized_term_for_id = f"UnnamedTerm_{time.time_ns()}"

                ref_id = f"ITAA1997:Definition:{sanitized_term_for_id}"

                synthetic_node = {
                    "ref_id": ref_id, "type": "Definition",
                    # Use sanitized term as the primary ID for lookups in the registry
                    "id": sanitized_term_for_id,
                    "raw_term": term,     # Keep the original term for display
                    "name": term,
                    "title": term, "level": 6, "content_md": data.get("content_md", ""),
                    "references": data.get("references", []),
                    "defined_terms_used": data.get("defined_terms_used", []), "children": []
                }
                process_node_pass1(synthetic_node, parent_internal_id, parent_hierarchy_path)
        except Exception as e:
            print(f"Error (Pass 1) loading definitions file {def_filepath}: {e}")
            traceback.print_exc()

    if processed_files == 0:
        print("Note: No input files were processed.")

    print(f"Pass 1 Complete. Structure built with {G.number_of_nodes()} nodes.")
    print(f"Type registry contains {len(id_type_registry)} unique IDs.")


# --- Robust Normalization Function (Unchanged) ---
def normalize_reference(original_ref_id, snippet="", source_ref_id=None):
    """
    Performs advanced syntactic normalization and semantic validation.
    Handles Act detection (contextual and heuristic), granular roll-up, self-references,
    and complex structures (Schedules, Parts/Divisions).
    """
    global semantic_mismatches_corrected

    if not original_ref_id or not isinstance(original_ref_id, str):
        return None

    # 1. Initial Parsing and Cleanup
    # Clean up the input ID string
    cleaned_id = original_ref_id.strip().replace("/", "_")
    parts = cleaned_id.split(':')

    if len(parts) > 1 and (parts[0].startswith("ITAA") or parts[0] == "Constitution" or parts[0] in ACT_MAPPINGS.values()):
        detected_act = parts[0]
        id_part = ":".join(parts[1:])
    else:
        # If no prefix, assume current act initially, but context might change it
        detected_act = ACT_ID
        id_part = cleaned_id

    # 2. Contextual Act Detection (Snippets) - High Priority
    current_act = detected_act
    snippet_upper = snippet.upper()

    # Check for specific Act mentions in the snippet
    act_detected_in_snippet = False
    for phrase, abbreviation in ACT_MAPPINGS.items():
        if phrase.upper() in snippet_upper:
            current_act = abbreviation
            act_detected_in_snippet = True
            break

    # Specific checks for common ambiguities
    if not act_detected_in_snippet:
        if "1936" in snippet:
            current_act = "ITAA1936"
        elif "TAXATION ADMINISTRATION ACT" in snippet_upper or "TAA 1953" in snippet_upper:
             current_act = "TAA1953"
        elif "TRANSITIONAL PROVISIONS) ACT 1997" in snippet_upper:
             current_act = "ITTPA1997"
        elif "GST ACT" in snippet_upper:
             current_act = "GSTA1999"


    # 3. Handle Generic/Empty References
    id_part_lower = id_part.lower()
    if not id_part or id_part_lower in ['act', 'n_a', 'general', 'na', 'unknown', 'u', 's', 't', 'p', 'd', 'n', 'i', 'ii', 'v', 'x']:
         # If the ID part is empty/generic, check if the original reference was just the Act name
        if cleaned_id.upper() in ACT_MAPPINGS.values() or cleaned_id.upper() + ":ACT" in ACT_MAPPINGS.values():
             return f"{current_act}:Act:General"
        # If it was referring to a specific section but failed extraction, return None to log it
        return None


    # 4. Handle Self-References (Granular types pointing to the source)
    # e.g., "subsection (2)", "paragraph (1)(a)"
    if source_ref_id and (
        re.match(r'^(Subsection|Paragraph|Subparagraph)[:_][0-9A-Za-z()]+$', id_part, re.IGNORECASE) or
        id_part_lower == "this_section" or id_part_lower == "this_division"
        ):
        # Normalize to the source ID (the function calling this normalization)
        # We assume the source_ref_id is already correctly formatted (e.g. ITAA1997:Section:10-5)
        return source_ref_id


    # 5. Handle Complex Structures (Schedules, Parts/Divisions)

    # --- TAA1953 Schedule 1 (Common pattern) ---
    if current_act == "TAA1953" and ("Schedule_1" in id_part or "Schedule:1" in id_part):
        # Look for the provision type and ID after "Schedule 1"
        schedule_part = re.split(r'Schedule[_\:]1', id_part, flags=re.IGNORECASE)[-1]
        match = ID_EXTRACTION_REGEX.search(schedule_part)
        if match:
            base_id = match.group(1)
            if 'subdivision' in schedule_part.lower():
                 normalized_type = "Schedule:1:Subdivision"
            elif 'division' in schedule_part.lower():
                 normalized_type = "Schedule:1:Division"
            else:
                 # Default to Section for specific IDs like 357-85
                 normalized_type = "Schedule:1:Section"
            return f"TAA1953:{normalized_type}:{base_id}"
        else:
             # Reference just to the schedule itself
             return "TAA1953:Schedule:1"

    # --- Other Schedules (e.g., Schedule 2F ITAA1936) ---
    if 'schedule' in id_part_lower:
        schedule_match = re.search(r'Schedule[_\:]([0-9A-Z]+)', id_part, re.IGNORECASE)
        if schedule_match:
            schedule_name = schedule_match.group(1).upper()
            # Known ITAA1936 Schedules
            if schedule_name in ["2D", "2F", "2G", "2H"] and current_act != "ITAA1936":
                 current_act = "ITAA1936"

            # Try to find a specific provision within the schedule
            remaining_part = id_part[schedule_match.end():]
            provision_match = ID_EXTRACTION_REGEX.search(remaining_part)

            if provision_match:
                base_id = provision_match.group(1)
                if 'subdivision' in remaining_part.lower():
                     normalized_type = f"Schedule:{schedule_name}:Subdivision"
                elif 'division' in remaining_part.lower():
                     normalized_type = f"Schedule:{schedule_name}:Division"
                else:
                     normalized_type = f"Schedule:{schedule_name}:Section"
                return f"{current_act}:{normalized_type}:{base_id}"
            else:
                return f"{current_act}:Schedule:{schedule_name}"

    # --- Part/Division Combinations (e.g., Division 7A of Part III) ---
    if 'part' in id_part_lower and ('division' in id_part_lower or 'subdivision' in id_part_lower):
        part_match = re.search(r'Part[_\:]([IVXLCDM]+|[0-9A-Z\-]+)', id_part, re.IGNORECASE)

        div_type, div_match = None, None
        if 'subdivision' in id_part_lower:
            div_type = "Subdivision"
            div_match = re.search(r'Subdivision[_\:]([0-9A-Z\-]+)', id_part, re.IGNORECASE)
        elif 'division' in id_part_lower:
            div_type = "Division"
            div_match = re.search(r'Division[_\:]([0-9A-Z\-]+)', id_part, re.IGNORECASE)

        if part_match and div_match:
            # Preserve the hierarchy: e.g., ITAA1936:Part:III:Division:7A
            return f"{current_act}:Part:{part_match.group(1)}:{div_type}:{div_match.group(1)}"


    # 6. ID Extraction and Heuristic Act Correction
    potential_id_string = None
    potential_id_match = ID_EXTRACTION_REGEX.search(id_part)

    if potential_id_match:
        potential_id_string = potential_id_match.group(1)

        # Apply the 1936 heuristic if context hasn't firmly established the Act.
        # If the ID looks like 159GK (and not 104-5), assume ITAA1936 unless context says otherwise.
        if current_act == ACT_ID and ITAA1936_HEURISTIC_REGEX.match(potential_id_string):
            # Double check it's not actually defined in ITAA1997 registry first
            if potential_id_string not in id_type_registry:
                current_act = "ITAA1936"


    # 7. Granular Roll-up and Type Normalization
    base_id = potential_id_string
    normalized_type = None

    # Definitions
    if 'definition' in id_part_lower:
        match = re.search(r'definition[:_](.+)$', id_part, re.IGNORECASE)
        if match:
            # The ID for a definition is the sanitized term
            base_id = re.sub(r'[^\w\-]+', '_', match.group(1).strip())
            normalized_type = "Definition"

    # Standard Provisions
    if not normalized_type and base_id:
        # If granular types are present, roll up to Section
        if any(x in id_part_lower for x in ['subsection', 'paragraph', 'subparagraph', 'table', 'item', 'cgtevent']):
            normalized_type = "Section"
        # Otherwise, determine the most specific container type mentioned
        elif 'subdivision' in id_part_lower:
            normalized_type = "Subdivision"
        elif 'division' in id_part_lower:
             # Handle ITAA1997 Subdivisions (e.g. 40-B) often mislabeled as Divisions
             if current_act == "ITAA1997" and re.match(r'^[0-9]+-[A-Z]$', base_id):
                  normalized_type = "Subdivision"
             else:
                  normalized_type = "Division"
        elif 'section' in id_part_lower:
            normalized_type = "Section"
        elif 'part' in id_part_lower:
            normalized_type = "Part"
        else:
            # Default assumption if type is missing but ID is present, usually Section
            normalized_type = "Section"

    # 8. Construct Syntactic Normalized ID
    if base_id and normalized_type:
        # Ensure base_id is uppercase for consistency unless it's a definition term
        if normalized_type != "Definition":
             base_id = base_id.upper()
        syntactically_normalized_ref_id = f"{current_act}:{normalized_type}:{base_id}"
    else:
        # Fallback if structured normalization failed. Try to preserve Act and raw ID part.
        # This often happens with references to non-standard acts.
        # We sanitize the id_part to make it safe for the final ID structure.
        sanitized_id_part = re.sub(r'[^A-Za-z0-9_\:]+', '_', id_part)
        if sanitized_id_part:
            return f"{current_act}:Reference:{sanitized_id_part}"
        else:
            return None # Could not extract meaningful ID


    # 9. Semantic Validation (Only for ITAA1997)
    final_ref_id = syntactically_normalized_ref_id

    if current_act == "ITAA1997" and base_id and normalized_type:
        # Use string conversion for lookup consistency
        correct_type = id_type_registry.get(str(base_id))

        # Validate only standard types (not complex ones like Schedules)
        if correct_type and ":" not in normalized_type and correct_type != normalized_type:
            # Mismatch found! Trust the registry.
            final_ref_id = f"{current_act}:{correct_type}:{base_id}"
            semantic_mismatches_corrected += 1

    return final_ref_id

# --- PASS 2: Add References and Validate (Unchanged) ---
def add_references_and_validate():
    """
    PASS 2: Iterates through nodes, normalizes references, adds REFERENCE edges,
    and handles placeholders.
    """
    print("\n=== PASS 2: Adding and Validating References ===")
    references_processed = 0

    for internal_id, node_data in list(node_registry.items()):
        if node_data.get("is_placeholder"): continue

        # Get the source ref_id for context (needed for self-references)
        source_node_ref_id = node_data.get("ref_id")
        references = node_data.get("references", [])

        for ref_data in references:
            references_processed += 1
            if not (isinstance(ref_data, (list, tuple)) and len(ref_data) > 0):
                continue

            original_target_ref_id = ref_data[0]
            snippet = ref_data[1] if len(ref_data) > 1 else ""

            # --- Apply Robust Normalization ---
            # Pass snippet and source_ref_id for context
            final_ref_id = normalize_reference(original_target_ref_id, snippet=snippet, source_ref_id=source_node_ref_id)
            # --- End Normalization ---

            if not final_ref_id:
                # Log if normalization failed completely
                skipped_placeholders_log.append({
                        "source_node_ref_id": source_node_ref_id or internal_id,
                        "original_reference": original_target_ref_id,
                        "normalized_reference": "FAILED_NORMALIZATION",
                        "snippet": snippet
                    })
                continue

            # --- Add Edge and Handle Placeholders ---
            target_internal_id = generate_internal_id(ref_id_override=final_ref_id)

            if target_internal_id not in G:
                G.add_node(target_internal_id)

            # If target isn't in node_registry, it's missing (external or internal miss)
            if target_internal_id not in node_registry:
                # Add placeholder if it doesn't already exist
                if not node_registry.get(target_internal_id):
                    # Determine if external based on the normalized ID
                    is_external = not final_ref_id.startswith(ACT_ID + ":")
                    node_registry[target_internal_id] = {"is_placeholder": True, "ref_id": final_ref_id, "is_external": is_external}

                    # Log skipped placeholder ONLY if it refers to the current Act (ITAA1997)
                    if not is_external:
                         skipped_placeholders_log.append({
                                "source_node_ref_id": source_node_ref_id or internal_id,
                                "original_reference": original_target_ref_id,
                                "normalized_reference": final_ref_id,
                                "snippet": snippet
                            })

            # Add edge (avoid self-loops)
            if internal_id != target_internal_id:
                G.add_edge(internal_id, target_internal_id, type='REFERENCES')

                # Update reverse references
                if target_internal_id not in reverse_references:
                    reverse_references[target_internal_id] = set()
                reverse_references[target_internal_id].add(internal_id)

    print(f"Pass 2 Complete. Processed {references_processed} references.")
    print(f"Total semantic mismatches corrected during normalization: {semantic_mismatches_corrected}.")
    # Calculate internal misses for logging summary
    internal_misses = len([p for p in skipped_placeholders_log if p['normalized_reference'] != "FAILED_NORMALIZATION"])
    print(f"Logged {internal_misses} missing INTERNAL (ITAA1997) references (see {LOG_FILENAME}).")


# --- Analyze Graph (Unchanged) ---
def analyze_graph():
    """Performs graph analysis (PageRank) on the citation network."""
    print("\n=== Analyzing Graph ===")
    if G.number_of_nodes() == 0 or not NETWORKX_AVAILABLE:
        print("Skipping PageRank (Graph empty or networkx unavailable).")
        return {"pagerank": {}}

    try:
        reference_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('type') == 'REFERENCES']

        reference_subgraph = nx.DiGraph()
        # Add all nodes first to ensure disconnected nodes get a score
        reference_subgraph.add_nodes_from(G.nodes(data=False))
        reference_subgraph.add_edges_from(reference_edges)

        if reference_subgraph.number_of_nodes() > 0:
            pagerank_scores = nx.pagerank(reference_subgraph, alpha=0.85)
            print("PageRank calculation complete.")
        else:
            pagerank_scores = {}

        return {"pagerank": pagerank_scores}
    except Exception as e:
        print(f"Error during graph analysis: {e}")
        traceback.print_exc()
        return {"pagerank": {}}

# --- Prepare Payload ---
# Renamed from prepare_firestore_payload
def prepare_database_payload(metrics):
    """Prepares the final data structure for saving."""
    payload = {}
    pagerank_scores = metrics.get("pagerank", {})

    print("\n=== Preparing Database Payload ===")
    placeholders_skipped_count = 0

    for internal_id, node_data in node_registry.items():

        # Skip placeholders in the final payload
        if node_data.get("is_placeholder"):
            placeholders_skipped_count +=1
            continue

        if internal_id not in G: continue

        # Calculate degrees
        in_degree = G.in_degree(internal_id) if G.number_of_nodes() > 0 else 0
        out_degree = G.out_degree(internal_id) if G.number_of_nodes() > 0 else 0
        pagerank = pagerank_scores.get(internal_id, 0.0)

        referenced_by_ids = sorted(list(reverse_references.get(internal_id, set())))

        original_references = node_data.get("references", [])
        source_ref_id = node_data.get("ref_id")

        # --- Store Normalized References in Payload ---
        # Re-normalize during payload creation to ensure consistency.

        normalized_references_list = []
        references_with_snippets_normalized = []

        for ref_data in original_references:
             if isinstance(ref_data, (list, tuple)) and len(ref_data) > 0 and ref_data[0]:
                original_ref_id = ref_data[0]
                snippet = ref_data[1] if len(ref_data) > 1 else ""

                # Normalize the reference ID (using snippet and source context)
                normalized_ref_id = normalize_reference(original_ref_id, snippet=snippet, source_ref_id=source_ref_id)

                if normalized_ref_id:
                    normalized_references_list.append(normalized_ref_id)
                    references_with_snippets_normalized.append({
                        "original_ref_id": original_ref_id,
                        "normalized_ref_id": normalized_ref_id,
                        "snippet": snippet
                    })

        # Remove duplicates and sort
        normalized_references_list = sorted(list(set(normalized_references_list)))
        # --- End ---


        document = {
            "internal_id": internal_id,
            "ref_id": source_ref_id,
            "type": node_data.get("type"),
            "id": node_data.get("id"),
            "raw_term": node_data.get("raw_term"), # Include raw term if present (for definitions)
            "name": node_data.get("name"),
            "title": node_data.get("title"),
            "level": node_data.get("level"),
            "content_md": node_data.get("content_md", ""),
            "hierarchy_path": node_data.get("hierarchy_path"),
            "parent_internal_id": node_data.get("parent_internal_id"),
            # Use the normalized references
            "references_to_normalized": normalized_references_list,
            "references_with_snippets_normalized": references_with_snippets_normalized,
            "defined_terms_used": node_data.get("defined_terms_used", []),
            "referenced_by_internal_ids": referenced_by_ids,
            "metrics": {
                "pagerank": pagerank,
                "in_degree": in_degree,
                "out_degree": out_degree
            }
        }

        # Clean up unnecessary fields and None values
        document = {k: v for k, v in document.items() if v is not None}
        if 'children' in document: del document['children']
        if 'references' in document: del document['references'] # Remove raw list

        payload[internal_id] = document

    print(f"Payload prepared with {len(payload)} documents.")
    if placeholders_skipped_count > 0:
        print(f"Excluded {placeholders_skipped_count} placeholder nodes from payload.")
    return payload

# --- Save Data Locally (JSON and SQLite) ---
# This replaces upload_to_firestore
def save_data_locally(payload):
    """Saves the prepared payload locally as a JSON file and in a SQLite database."""
    if not payload:
        print("Payload is empty. Skipping save.")
        return

    print(f"\n=== Starting Local Data Save ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Save to SQLite (Primary database for querying)
    db_filepath = os.path.join(OUTPUT_DIR, OUTPUT_SQLITE_DB)
    conn = None
    try:
        # Connect and get cursor. This creates the file if it doesn't exist.
        conn = sqlite3.connect(db_filepath)
        cursor = conn.cursor()

        # Create table (DROP first to ensure fresh data on re-run)
        cursor.execute("DROP TABLE IF EXISTS provisions")
        cursor.execute("""
            CREATE TABLE provisions (
                internal_id TEXT PRIMARY KEY,
                ref_id TEXT,
                type TEXT,
                title TEXT,
                content_md TEXT,
                hierarchy_path TEXT,
                parent_internal_id TEXT,
                pagerank REAL,
                in_degree INTEGER,
                out_degree INTEGER,
                full_json_data TEXT
            )
        """)

        # Prepare data for insertion
        data_to_insert = []
        for internal_id, data in payload.items():
            metrics = data.get("metrics", {})
            data_to_insert.append((
                internal_id,
                data.get("ref_id"),
                data.get("type"),
                data.get("title"),
                data.get("content_md"),
                data.get("hierarchy_path"),
                data.get("parent_internal_id"),
                metrics.get("pagerank", 0.0),
                metrics.get("in_degree", 0),
                metrics.get("out_degree", 0),
                json.dumps(data, ensure_ascii=False) # Serialize the whole object for the JSON column
            ))

        # Insert data in bulk
        cursor.executemany("""
            INSERT INTO provisions (
                internal_id, ref_id, type, title, content_md, hierarchy_path,
                parent_internal_id, pagerank, in_degree, out_degree, full_json_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data_to_insert)

        conn.commit()
        print(f"Successfully inserted {len(data_to_insert)} records into SQLite database: {db_filepath}")

        # Create indexes for faster querying (essential for the web interface)
        print("Ensuring SQLite indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ref_id ON provisions (ref_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON provisions (type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent_id ON provisions (parent_internal_id)")
        conn.commit()
        

    except sqlite3.Error as e:
        print(f"Error saving to SQLite database: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

    # 2. Save as JSON (For visualization and bulk access)
    json_filepath = os.path.join(OUTPUT_DIR, OUTPUT_JSON_FILENAME)
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            # Save the payload as a dictionary (Key=internal_id) for efficient lookup
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved data to JSON: {json_filepath}")
    except Exception as e:
        print(f"Error saving JSON file: {e}")
        traceback.print_exc()


# upload_to_firestore function removed.

# --- Write Skipped Log (Unchanged) ---
def write_skipped_log():
    """Writes the skipped internal placeholder details to a CSV file."""

    # Ensure output directory exists (redundant but safe)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_filepath = os.path.join(OUTPUT_DIR, LOG_FILENAME)

    # Filter the log (External references are excluded during Pass 2 logging)
    if not skipped_placeholders_log:
        print(f"\nNo unresolved internal references found. Log file not created.")
        return

    print(f"\nWriting unresolved internal reference log to: {log_filepath}")

    headers = ["source_node_ref_id", "original_reference", "normalized_reference", "snippet"]

    try:
        with open(log_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(skipped_placeholders_log)
        print(f"Successfully wrote {len(skipped_placeholders_log)} entries to log.")
    except Exception as e:
        print(f"Error writing log file: {e}")
        traceback.print_exc()


# --- Main Execution ---
def main():
    # Firebase initialization removed

    # Pass 1: Build Structure & Type Registry
    load_data_and_build_structure()

    # Pass 2: Add References & Validate
    add_references_and_validate()

    # Analyze Graph
    metrics = analyze_graph()

    # Prepare Payload
    payload = prepare_database_payload(metrics)

    # Save Locally (replaces upload)
    save_data_locally(payload)

    # Write Log
    write_skipped_log()

if __name__ == '__main__':
    # To run this, ensure the INPUT_DIR exists and contains the JSON files.
    # Ensure dependencies (networkx) are installed if needed. sqlite3 is standard library.
    main()