# ingest/core/analysis.py
import json
import re
import time
import traceback
import csv
import os
from typing import Dict, Any, List, Tuple, Set
import logging

# Import normalization functions
from .normalization import normalize_reference, get_normalization_metrics, reset_normalization_metrics
from sqlalchemy_utils import Ltree

logger = logging.getLogger(__name__)

# Import networkx (Mock implementation copied from original analyze_and_ingest.py)
try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    logger.warning("networkx not found. Graph analysis (PageRank) will be disabled.")
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

def sanitize_for_ltree(identifier):
    """(NEW) Sanitizes a string for LTree path component."""
    if identifier is None:
        # Use a timestamp to ensure uniqueness if identifier is missing
        return f"UNKNOWN_{time.time_ns()}"

    # LTree labels must contain only alphanumeric characters and underscores.
    sanitized = re.sub(r'[^A-Za-z0-9_]+', '_', str(identifier))

    # Ensure it doesn't start/end excessively with underscore
    sanitized = sanitized.lstrip('_').strip('_')

    # LTree labels cannot start with a digit. Prepend an underscore if it does.
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    if not sanitized:
         return f"EMPTY_{time.time_ns()}"
    return sanitized


class GraphAnalyzer:
    """
    Analyzes structure and references, calculates LTree paths, and prepares DB payload.
    """
    def __init__(self, default_act_id: str):
        self.G = nx.DiGraph() if NETWORKX_AVAILABLE else MockNX().DiGraph()
        self.default_act_id = default_act_id
        self.node_registry: Dict[str, Dict[str, Any]] = {}
        # Registry key format: ACT/ID (Standardized for cross-act lookups)
        self.id_type_registry: Dict[str, str] = {}
        self.reverse_references: Dict[str, Set[str]] = {}
        self.unresolved_log: List[Dict[str, str]] = []
        # Reset normalization metrics for this analysis run
        reset_normalization_metrics()

    def generate_internal_id(self, node=None, parent_internal_id=None, ref_id_override=None):
        """
        Generates a unique internal ID (Document ID/Primary Key).
        (Copied and adapted from analyze_and_ingest.py)
        """
        ref_id_to_use = ref_id_override if ref_id_override else (node.get("ref_id") if node else None)

        if ref_id_to_use:
            # Sanitize both ':' and '/' for the DB primary key
            sanitized_id = ref_id_to_use.replace(":", "_").replace("/", "_")
            return sanitized_id

        # Generate derived ID for elements without canonical IDs (Guides, etc.)
        if node:
            # ADAPTED: Use self.default_act_id
            prefix = parent_internal_id if parent_internal_id else f"{self.default_act_id}_Root"
            safe_title = re.sub(r'[^\w\-]+', '_', node.get("title", "UnnamedElement"))
            # Use a timestamp to ensure uniqueness if titles collide
            return f"{prefix}_Element_{safe_title[:80]}_{time.time_ns()}"

        return f"UnknownID_{time.time_ns()}"

    # --- PASS 1: Build Structure, LTree Paths, and Type Registry ---

    def process_node_pass1(self, node, parent_internal_id=None, ltree_path="", sibling_index=None):
        """
        (ADAPTED) Calculates LTree paths and populates the registry (using ACT/ID keys).
        """
        internal_id = self.generate_internal_id(node, parent_internal_id)
        # For this pipeline, the current act is the default act.
        current_act_id = self.default_act_id

        # Check if it's a new node OR a placeholder that needs to be hydrated
        is_new_or_placeholder = (
            internal_id not in self.node_registry or
            self.node_registry[internal_id].get("is_placeholder", False)
        )

        current_ltree_path = ltree_path

        if is_new_or_placeholder:
            # If it's a placeholder, update it. If it's new, create it.
            if internal_id in self.node_registry:
                # Hydrate placeholder
                self.node_registry[internal_id].update(node.copy())
                self.node_registry[internal_id].pop("is_placeholder", None)
                self.node_registry[internal_id].pop("is_external", None)
            else:
                # Create new
                self.node_registry[internal_id] = node.copy()
                if internal_id not in self.G:
                    self.G.add_node(internal_id)

            # --- Calculate LTree Path (Moved inside) ---
            node_type = node.get("type")
            node_id = node.get("id") # This is the local_id (e.g., '10-5' or the term)

            # Determine the path component for LTree
            if node_id:
                path_component = sanitize_for_ltree(node_id)
            elif node_type:
                path_component = f"{sanitize_for_ltree(node_type)}_{time.time_ns()}"
            else:
                path_component = sanitize_for_ltree(None)

            # Build the LTree path (e.g., ITAA1997.1.10_5)
            if current_ltree_path:
                current_ltree_path += f".{path_component}"
            else:
                logger.warning(f"Root level element '{internal_id}' processed without parent LTree path.")
                current_ltree_path = path_component

            # --- Populate id_type_registry (Standardized Key) ---
            if node_type and node_id:
                str_node_id = str(node_id)
                registry_key = f"{current_act_id}/{str_node_id}"

                if registry_key not in self.id_type_registry:
                    self.id_type_registry[registry_key] = node_type
                # Prioritize structural types over 'Definition' if ID is reused
                elif self.id_type_registry[registry_key] != node_type:
                    if node_type != 'Definition' and self.id_type_registry[registry_key] == 'Definition':
                        self.id_type_registry[registry_key] = node_type

            # Store the calculated path and parent link
            self.node_registry[internal_id]["hierarchy_path_ltree"] = Ltree(current_ltree_path)
            self.node_registry[internal_id]["parent_internal_id"] = parent_internal_id
            self.node_registry[internal_id]["sibling_order"] = sibling_index

            # Add CONTAINS Edge (For graph structure visualization if needed)
            if parent_internal_id:
                self.G.add_edge(parent_internal_id, internal_id, type='CONTAINS')

        else:
            # If node already exists (and not a placeholder), retrieve its path for children processing
            retrieved_ltree = self.node_registry[internal_id].get("hierarchy_path_ltree")
            if isinstance(retrieved_ltree, Ltree):
                current_ltree_path = str(retrieved_ltree)
            if sibling_index is not None:
                self.node_registry[internal_id]["sibling_order"] = sibling_index
            # else: current_ltree_path remains as passed in (ltree_path)


        # Recurse into children
        for index, child in enumerate(node.get("children", [])):
            # Pass the calculated path and sibling order down to children
            self.process_node_pass1(child, internal_id, current_ltree_path, sibling_index=index)

    # --- PASS 2: Reference Validation ---

    def add_references_and_validate(self):
        """
        PASS 2: Iterates through nodes, normalizes references, adds REFERENCE edges,
        and handles placeholders. (Copied and adapted from analyze_and_ingest.py)
        """
        logger.info("\n=== PASS 2: Adding and Validating References ===")
        references_processed = 0

        for internal_id, node_data in list(self.node_registry.items()):
            if node_data.get("is_placeholder"): continue

            source_node_ref_id = node_data.get("ref_id")
            references = node_data.get("references", [])

            for ref_data in references:
                references_processed += 1
                if not (isinstance(ref_data, (list, tuple)) and len(ref_data) > 0):
                    continue

                original_target_ref_id = ref_data[0]
                snippet = ref_data[1] if len(ref_data) > 1 else ""

                # --- Apply Robust Normalization ---
                # ADAPTED: Call the generalized normalization function
                final_ref_id = normalize_reference(
                    original_target_ref_id,
                    snippet=snippet,
                    source_ref_id=source_node_ref_id,
                    id_type_registry=self.id_type_registry,
                    default_act=self.default_act_id
                )
                # --- End Normalization ---

                if not final_ref_id:
                    # Log if normalization failed completely
                    self.unresolved_log.append({
                        "source_node_ref_id": source_node_ref_id or internal_id,
                        "original_reference": original_target_ref_id,
                        "normalized_reference": "FAILED_NORMALIZATION",
                        "snippet": snippet
                    })
                    continue

                # --- Add Edge and Handle Placeholders ---
                target_internal_id = self.generate_internal_id(ref_id_override=final_ref_id)

                if target_internal_id not in self.G:
                    self.G.add_node(target_internal_id)

                # If target isn't in node_registry, it's missing (external or internal miss)
                if target_internal_id not in self.node_registry:
                    # Add placeholder if it doesn't already exist
                    if not self.node_registry.get(target_internal_id):
                        # Determine if external based on the normalized ID prefix
                        # ADAPTED: Check against self.default_act_id
                        is_external = not final_ref_id.startswith(self.default_act_id + ":")
                        self.node_registry[target_internal_id] = {"is_placeholder": True, "ref_id": final_ref_id, "is_external": is_external}

                        # Log skipped placeholder ONLY if it refers to the current Act
                        if not is_external:
                            self.unresolved_log.append({
                                "source_node_ref_id": source_node_ref_id or internal_id,
                                "original_reference": original_target_ref_id,
                                "normalized_reference": final_ref_id,
                                "snippet": snippet
                            })

                # Add edge (avoid self-loops)
                if internal_id != target_internal_id:
                    self.G.add_edge(internal_id, target_internal_id, type='REFERENCES')

                    # Update reverse references
                    if target_internal_id not in self.reverse_references:
                        self.reverse_references[target_internal_id] = set()
                    self.reverse_references[target_internal_id].add(internal_id)

        # Retrieve metrics collected during normalization
        metrics = get_normalization_metrics()
        logger.info(f"Pass 2 Complete. Processed {references_processed} references.")
        logger.info(f"Total semantic mismatches corrected during normalization: {metrics['semantic_mismatches_corrected']}.")
        # Calculate internal misses for logging summary
        internal_misses = len([p for p in self.unresolved_log if p['normalized_reference'] != "FAILED_NORMALIZATION"])
        logger.info(f"Logged {internal_misses} missing INTERNAL ({self.default_act_id}) references.")


    # --- Analysis and Payload Preparation ---

    def analyze_graph_metrics(self) -> Dict[str, Dict[str, float]]:
        """Performs graph analysis (PageRank) on the citation network."""
        logger.info("\n=== Analyzing Graph Metrics ===")
        if self.G.number_of_nodes() == 0 or not NETWORKX_AVAILABLE:
            logger.info("Skipping PageRank (Graph empty or networkx unavailable).")
            return {"pagerank": {}}

        try:
            # Analyze only the citation network (REFERENCES edges)
            reference_edges = [(u, v) for u, v, d in self.G.edges(data=True) if d.get('type') == 'REFERENCES']

            reference_subgraph = nx.DiGraph()
            # Add all nodes first to ensure disconnected nodes get a score
            reference_subgraph.add_nodes_from(self.G.nodes(data=False))
            reference_subgraph.add_edges_from(reference_edges)

            if reference_subgraph.number_of_nodes() > 0:
                pagerank_scores = nx.pagerank(reference_subgraph, alpha=0.85)
                logger.info("PageRank calculation complete.")
            else:
                pagerank_scores = {}

            return {"pagerank": pagerank_scores}
        except Exception as e:
            logger.error(f"Error during graph analysis: {e}")
            logger.error(traceback.format_exc())
            return {"pagerank": {}}


    def prepare_database_payload(self, metrics: Dict[str, Dict[str, float]]):
        """
        (ADAPTED) Prepares data for the SQLAlchemy models (Provisions, References, DefinedTermUsage).
        """
        logger.info("\n=== Preparing Database Payload ===")

        # Initialize payloads for the database models
        provisions_payload = []
        references_payload = []
        defined_terms_usage_payload = []

        pagerank_scores = metrics.get("pagerank", {})
        placeholders_skipped_count = 0

        for internal_id, node_data in self.node_registry.items():

            # Skip placeholders in the final payload
            if node_data.get("is_placeholder"):
                placeholders_skipped_count +=1
                continue

            if internal_id not in self.G: continue

            # Calculate degrees based on REFERENCES edges
            # In-degree is accurately represented by the count of reverse references
            in_degree = len(self.reverse_references.get(internal_id, set()))
            pagerank = pagerank_scores.get(internal_id, 0.0)

            source_ref_id = node_data.get("ref_id")
            # Ensure ref_id is never None, use internal_id as fallback for non-canonical items
            final_ref_id = source_ref_id if source_ref_id is not None else internal_id

            # --- Process References (for Reference model) ---
            # We must re-normalize here to ensure consistency and populate the Reference table accurately.

            original_references = node_data.get("references", [])
            unique_normalized_targets = set() # To calculate out_degree

            for ref_data in original_references:
                 if isinstance(ref_data, (list, tuple)) and len(ref_data) > 0 and ref_data[0]:
                    original_ref_id = ref_data[0]
                    snippet = ref_data[1] if len(ref_data) > 1 else ""

                    # Normalize the reference ID
                    normalized_ref_id = normalize_reference(
                        original_ref_id, snippet=snippet, source_ref_id=source_ref_id,
                        id_type_registry=self.id_type_registry, default_act=self.default_act_id
                    )

                    if normalized_ref_id:
                        unique_normalized_targets.add(normalized_ref_id)

                        # Resolve target_internal_id
                        target_internal_id = self.generate_internal_id(ref_id_override=normalized_ref_id)

                        # Check if target exists in the registry AND is NOT a placeholder
                        if target_internal_id in self.node_registry and not self.node_registry[target_internal_id].get("is_placeholder"):
                            resolved_target_id = target_internal_id
                        else:
                            # The target is external or missing
                            resolved_target_id = None

                        # Add to References payload
                        references_payload.append({
                            "source_internal_id": internal_id,
                            "target_ref_id": normalized_ref_id,
                            "target_internal_id": resolved_target_id,
                            "original_ref_text": original_ref_id,
                            "snippet": snippet
                        })

            # Out-degree is the count of unique normalized targets referenced
            out_degree = len(unique_normalized_targets)

            # --- Process Defined Terms (for DefinedTermUsage model) ---
            defined_terms_used = node_data.get("defined_terms_used", [])

            for term_text in defined_terms_used:
                # Attempt to find the definition provision for this term.
                # We rely on the standard definition format: ACT:Definition:SanitizedTerm

                # Sanitize the term text to match the expected local_id format used during Pass 1
                sanitized_term_for_id = re.sub(r'[^\w\-]+', '_', term_text)
                if not sanitized_term_for_id: continue

                definition_ref_id = f"{self.default_act_id}:Definition:{sanitized_term_for_id}"
                definition_internal_id = self.generate_internal_id(ref_id_override=definition_ref_id)

                # Check if the definition exists and is not a placeholder
                if definition_internal_id in self.node_registry and not self.node_registry[definition_internal_id].get("is_placeholder"):
                    resolved_definition_id = definition_internal_id
                else:
                    resolved_definition_id = None

                defined_terms_usage_payload.append({
                    "source_internal_id": internal_id,
                    "term_text": term_text,
                    "definition_internal_id": resolved_definition_id
                })

            # Prepare Provision data (matching the Provision model fields)
            provision_data = {
                "internal_id": internal_id,
                "act_id": self.default_act_id,
                "ref_id": final_ref_id,
                "type": node_data.get("type"),
                "local_id": node_data.get("id"), # ADAPTED (was 'id' in source JSON)
                # Use raw_term if present (for definitions), otherwise fallback to name/title
                "title": node_data.get("raw_term") or node_data.get("title") or node_data.get("name", "Unnamed Provision"),
                "content_md": node_data.get("content_md", ""),
                "level": node_data.get("level"),
                "hierarchy_path_ltree": node_data.get("hierarchy_path_ltree"), # ADAPTED
                "parent_internal_id": node_data.get("parent_internal_id"),
                "sibling_order": node_data.get("sibling_order"),
                "pagerank": pagerank,
                "in_degree": in_degree,
                "out_degree": out_degree
            }
            # Clean up None values that might violate NOT NULL constraints (like 'title' if missing)
            provision_data_cleaned = {k: v for k, v in provision_data.items() if v is not None}
            provisions_payload.append(provision_data_cleaned)


        logger.info(f"Payload prepared with {len(provisions_payload)} provisions, {len(references_payload)} references, {len(defined_terms_usage_payload)} term usages.")
        if placeholders_skipped_count > 0:
            logger.info(f"Excluded {placeholders_skipped_count} placeholder nodes from payload.")

        return provisions_payload, references_payload, defined_terms_usage_payload

    def write_unresolved_log(self, output_dir: str):
        """Writes the unresolved internal placeholder details to a CSV file."""
        LOG_FILENAME = f"unresolved_internal_references_{self.default_act_id}.csv"

        os.makedirs(output_dir, exist_ok=True)
        log_filepath = os.path.join(output_dir, LOG_FILENAME)

        if not self.unresolved_log:
            logger.info(f"\nNo unresolved internal references found. Log file not created.")
            return

        logger.info(f"\nWriting unresolved internal reference log to: {log_filepath}")

        headers = ["source_node_ref_id", "original_reference", "normalized_reference", "snippet"]

        try:
            with open(log_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                writer.writerows(self.unresolved_log)
            logger.info(f"Successfully wrote {len(self.unresolved_log)} entries to log.")
        except Exception as e:
            logger.error(f"Error writing log file: {e}")
            logger.error(traceback.format_exc())
