// types.ts

// Matches ReferenceToDetail schema
export interface ReferenceInfo {
    target_ref_id: string;
    snippet: string | null;
    target_title: string | null;
    target_internal_id?: string | null;
}

// Matches ReferencedByDetail schema
export interface ReferencedByInfo {
    source_internal_id: string;
    source_ref_id: string;
    source_title: string;
}

// Matches DefinedTermUsageDetail schema
export interface DefinedTermInfo {
    term_text: string;
    definition_internal_id: string | null;
}

// Matches the ProvisionDetail schema from the backend
export interface TaxDataObject {
    internal_id: string;
    ref_id: string;
    act_id: string;
    type: string;
    local_id: string | null;
    title: string;
    content_md: string | null;
    level: number;
    hierarchy_path_ltree: string;
    parent_internal_id?: string;
    sibling_order?: number | null;

    // Metrics
    pagerank: number;
    in_degree: number;
    out_degree: number;

    // Related Data (Updated structure)
    references_to: ReferenceInfo[];
    referenced_by: ReferencedByInfo[];
    defined_terms_used: DefinedTermInfo[];
}

// Matches the ProvisionHierarchy schema (for SideNav)
export interface HierarchyNode {
    internal_id: string;
    ref_id: string;
    title: string;
    type: string;
    has_children: boolean;
    sibling_order?: number | null;
    // Optional children property; null when the API omits nested nodes
    children?: HierarchyNode[] | null;
}


// Updated DetailViewContent type to include termText for better display when type is 'term'
export type DetailViewContent =
    | { type: 'reference'; data: TaxDataObject }
    | { type: 'term'; data: TaxDataObject; termText: string }
    | { type: 'error'; data: string };
