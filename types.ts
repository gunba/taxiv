export interface ReferenceSnippet {
  original_ref_id: string;
  normalized_ref_id: string;
  snippet: string;
}

export interface TaxDataObject {
  internal_id: string;
  ref_id: string | null;
  type: string;
  id: string | null;
  name: string;
  title: string;
  level: number;
  content_md: string;
  hierarchy_path: string;
  parent_internal_id?: string;
  references_to_normalized: string[];
  references_with_snippets_normalized: ReferenceSnippet[];
  defined_terms_used: string[];
  raw_term?: string; // For definition types
}

export type DetailViewContent = 
  | { type: 'reference'; data: TaxDataObject }
  | { type: 'term'; data: TaxDataObject }
  | { type: 'error'; data: string };