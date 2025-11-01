# ingest/core/normalization.py
import re
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Global counter (used for logging/metrics during a specific run)
semantic_mismatches_corrected_count = 0

# --- Regex and Mappings Definitions (Copied from original analyze_and_ingest.py) ---

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
    "Constitution": "Constitution",
}

def reset_normalization_metrics():
    """Resets global metrics before a new analysis run."""
    global semantic_mismatches_corrected_count
    semantic_mismatches_corrected_count = 0

def get_normalization_metrics() -> Dict[str, int]:
    """Returns the metrics collected during the run."""
    return {
        "semantic_mismatches_corrected": semantic_mismatches_corrected_count
    }

def normalize_reference(
        original_ref_id: str,
        snippet: str = "",
        source_ref_id: Optional[str] = None,
        # Registry format is standardized: ACT_ID/Local_ID -> Type
        id_type_registry: Dict[str, str] = {},
        default_act: str = "ITAA1997"
    ) -> Optional[str]:
    """
    Performs advanced syntactic normalization and semantic validation.
    (Adapted from analyze_and_ingest.py for generalization)
    """
    global semantic_mismatches_corrected_count

    if not original_ref_id or not isinstance(original_ref_id, str):
        return None

    # 1. Initial Parsing and Cleanup
    cleaned_id = original_ref_id.strip().replace("/", "_")
    parts = cleaned_id.split(':')

    # Check if the prefix is a known Act identifier
    if len(parts) > 1 and (parts[0].startswith("ITAA") or parts[0] == "Constitution" or parts[0] in ACT_MAPPINGS.values()):
        detected_act = parts[0]
        id_part = ":".join(parts[1:])
    else:
        # If no prefix, assume current act initially, but context might change it
        detected_act = default_act # Use the parameterized default
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
        # Heuristic: if 1936 is present and 1997 is not explicitly mentioned nearby, prefer 1936
        if "1936" in snippet and "1997" not in snippet:
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
    if source_ref_id and (
        re.match(r'^(Subsection|Paragraph|Subparagraph)[:_][0-9A-Za-z()]+$', id_part, re.IGNORECASE) or
        id_part_lower == "this_section" or id_part_lower == "this_division"
        ):
        return source_ref_id


    # 5. Handle Complex Structures (Schedules, Parts/Divisions)

    # --- TAA1953 Schedule 1 (Common pattern) ---
    if current_act == "TAA1953" and ("Schedule_1" in id_part or "Schedule:1" in id_part):
        schedule_part = re.split(r'Schedule[_\:]1', id_part, flags=re.IGNORECASE)[-1]
        match = ID_EXTRACTION_REGEX.search(schedule_part)
        if match:
            base_id = match.group(1)
            if 'subdivision' in schedule_part.lower():
                 normalized_type = "Schedule:1:Subdivision"
            elif 'division' in schedule_part.lower():
                 normalized_type = "Schedule:1:Division"
            else:
                 normalized_type = "Schedule:1:Section"
            return f"TAA1953:{normalized_type}:{base_id}"
        else:
             return "TAA1953:Schedule:1"

    # --- Other Schedules (e.g., Schedule 2F ITAA1936) ---
    if 'schedule' in id_part_lower:
        schedule_match = re.search(r'Schedule[_\:]([0-9A-Z]+)', id_part, re.IGNORECASE)
        if schedule_match:
            schedule_name = schedule_match.group(1).upper()
            # Known ITAA1936 Schedules
            if schedule_name in ["2D", "2F", "2G", "2H"] and current_act != "ITAA1936":
                 current_act = "ITAA1936"

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
        # ADAPTATION: Use standardized registry key format (ACT/ID)
        if current_act == default_act and ITAA1936_HEURISTIC_REGEX.match(potential_id_string):
            # Double check it's not actually defined in the default act registry first
            registry_key = f"{default_act}/{potential_id_string}"
            if registry_key not in id_type_registry:
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
        # Fallback if structured normalization failed.
        sanitized_id_part = re.sub(r'[^A-Za-z0-9_\:]+', '_', id_part)
        if sanitized_id_part:
            return f"{current_act}:Reference:{sanitized_id_part}"
        else:
            return None # Could not extract meaningful ID


    # 9. Semantic Validation (Generalized)
    final_ref_id = syntactically_normalized_ref_id

    # ADAPTATION: Use standardized registry key format (ACT/ID)
    if base_id and normalized_type:
        # Use string conversion for lookup consistency
        registry_key = f"{current_act}/{str(base_id)}"
        correct_type = id_type_registry.get(registry_key)

        # Validate only standard types (not complex ones like Schedules)
        if correct_type and ":" not in normalized_type and correct_type != normalized_type:
            # Mismatch found! Trust the registry.
            final_ref_id = f"{current_act}:{correct_type}:{base_id}"
            semantic_mismatches_corrected_count += 1

    return final_ref_id
