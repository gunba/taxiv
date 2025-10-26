import type { TaxDataObject } from '../types';

export const taxDatabase: Record<string, TaxDataObject> = {
  "ITAA1997_Chapter_1": {
    "internal_id": "ITAA1997_Chapter_1",
    "ref_id": "ITAA1997:Chapter:1",
    "type": "Chapter",
    "id": "1",
    "name": "Introduction and core provisions",
    "title": "Chapter 1—Introduction and core provisions",
    "level": 1,
    "content_md": "This chapter provides an introduction to the Act.",
    "hierarchy_path": "/Chapter:1/",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": [],
  },
  "ITAA1997_Part_1-1": {
    "internal_id": "ITAA1997_Part_1-1",
    "ref_id": "ITAA1997:Part:1-1",
    "type": "Part",
    "id": "1-1",
    "name": "Preliminary",
    "title": "Part 1-1—Preliminary",
    "level": 2,
    "content_md": "",
    "hierarchy_path": "/Chapter:1/Part:1-1/",
    "parent_internal_id": "ITAA1997_Chapter_1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": [],
  },
  "ITAA1997_Division_1": {
    "internal_id": "ITAA1997_Division_1",
    "ref_id": "ITAA1997:Division:1",
    "type": "Division",
    "id": "1",
    "name": "Preliminary",
    "title": "Division 1—Preliminary",
    "level": 3,
    "content_md": "",
    "hierarchy_path": "/Chapter:1/Part:1-1/Division:1/",
    "parent_internal_id": "ITAA1997_Part_1-1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": [],
  },
  "ITAA1997_Section_1-1": {
    "internal_id": "ITAA1997_Section_1-1",
    "ref_id": "ITAA1997:Section:1-1",
    "type": "Section",
    "id": "1-1",
    "name": "Short title",
    "title": "1-1  Short title",
    "level": 4,
    "content_md": "This Act may be cited as the Income Tax Assessment Act 1997.",
    "hierarchy_path": "/Chapter:1/Part:1-1/Division:1/Section:1-1/",
    "parent_internal_id": "ITAA1997_Division_1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": [],
  },
  "ITAA1997_Section_1-2": {
    "internal_id": "ITAA1997_Section_1-2",
    "ref_id": "ITAA1997:Section:1-2",
    "type": "Section",
    "id": "1-2",
    "name": "Commencement",
    "title": "1-2  Commencement",
    "level": 4,
    "content_md": "This Act commences on 1 July 1997.",
    "hierarchy_path": "/Chapter:1/Part:1-1/Division:1/Section:1-2/",
    "parent_internal_id": "ITAA1997_Division_1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": [],
  },
  "ITAA1997_Section_152-78": {
    "internal_id": "ITAA1997_Section_152-78",
    "ref_id": "ITAA1997:Section:152-78",
    "type": "Section",
    "id": "152-78",
    "name": "Trustee of discretionary trust may nominate beneficiaries to be controllers of trust",
    "title": "152-78  Trustee of discretionary trust may nominate beneficiaries to be controllers of trust",
    "level": 4,
    "content_md": "(1)\tThis section applies for the purposes of determining whether an entity is *connected with you, for the purposes of:\n\n(a)\tthis Subdivision; and\n\n(b)\tsections 328-110, 328-115 and 328-125 so far as they relate to this Subdivision.\n\n(2)\tThe trustee of a discretionary trust may nominate not more than 4 beneficiaries as being controllers of the trust for an income year (the relevant income year) for which the trustee did not make a distribution of income or capital if the trust had a *tax loss, or no *net income, for that year.",
    "hierarchy_path": "/Chapter:3/Part:3-3/Division:152/Section:152-78/",
    "parent_internal_id": "ITAA1997_Division_152",
    "references_to_normalized": [
      "ITAA1997:Section:328-110"
    ],
    "references_with_snippets_normalized": [
      {
        "original_ref_id": "ITAA1997:Section:328-110",
        "normalized_ref_id": "ITAA1997:Section:328-110",
        "snippet": "sections 328-110, 328-115 and 328-125"
      },
       {
        "original_ref_id": "ITAA1997:Section:328-125",
        "normalized_ref_id": "ITAA1997:Section:328-125",
        "snippet": "this Subdivision"
      }
    ],
    "defined_terms_used": [
      "connected with",
      "net income",
      "tax loss"
    ]
  },
  "ITAA1997_Definition_connected_with": {
    "internal_id": "ITAA1997_Definition_connected_with",
    "ref_id": "ITAA1997:Definition:connected_with",
    "type": "Definition",
    "id": "connected_with",
    "raw_term": "connected with",
    "name": "connected with",
    "title": "connected with",
    "level": 5,
    "content_md": "An entity is **connected with** another entity in the circumstances described in section 328-125.",
    "hierarchy_path": "/Chapter:6/Part:6-5/Division:995/Section:995-1/Definition:connected_with/",
    "parent_internal_id": "ITAA1997_Section_995-1",
    "references_to_normalized": [
      "ITAA1997:Section:328-125"
    ],
    "references_with_snippets_normalized": [
      {
        "original_ref_id": "ITAA1997:Section:328-125",
        "normalized_ref_id": "ITAA1997:Section:328-125",
        "snippet": "section 328-125"
      }
    ],
    "defined_terms_used": []
  },
  "ITAA1997_Definition_net_income": {
    "internal_id": "ITAA1997_Definition_net_income",
    "ref_id": "ITAA1997:Definition:net_income",
    "type": "Definition",
    "id": "net_income",
    "raw_term": "net income",
    "name": "net income",
    "title": "net income",
    "level": 5,
    "content_md": "The **net income** of a trust estate is the total assessable income of the trust estate calculated as if the trustee were a resident taxpayer, less all allowable deductions.",
    "hierarchy_path": "/Chapter:6/Part:6-5/Division:995/Section:995-1/Definition:net_income/",
    "parent_internal_id": "ITAA1997_Section_995-1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": []
  },
   "ITAA1997_Definition_tax_loss": {
    "internal_id": "ITAA1997_Definition_tax_loss",
    "ref_id": "ITAA1997:Definition:tax_loss",
    "type": "Definition",
    "id": "tax_loss",
    "raw_term": "tax loss",
    "name": "tax loss",
    "title": "tax loss",
    "level": 5,
    "content_md": "A **tax loss** is the amount by which a taxpayer's allowable deductions for an income year exceed their assessable income for that year.",
    "hierarchy_path": "/Chapter:6/Part:6-5/Division:995/Section:995-1/Definition:tax_loss/",
    "parent_internal_id": "ITAA1997_Section_995-1",
    "references_to_normalized": [],
    "references_with_snippets_normalized": [],
    "defined_terms_used": []
  }
};
