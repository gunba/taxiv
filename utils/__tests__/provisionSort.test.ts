import {describe, expect, it} from 'vitest';
import type {TaxDataObject} from '../../types';
import {compareProvisions, sortProvisions} from '../provisionSort';

const baseNode = (overrides: Partial<TaxDataObject>): TaxDataObject => ({
    internal_id: 'id',
    ref_id: 'ref',
    act_id: 'ITAA1997',
    type: 'SECTION',
    local_id: null,
    title: 'Title',
    content_md: null,
    level: 1,
    hierarchy_path_ltree: '1',
    parent_internal_id: undefined,
    sibling_order: null,
    pagerank: 0,
    in_degree: 0,
    out_degree: 0,
    references_to: [],
    referenced_by: [],
    defined_terms_used: [],
    definitions_with_references: [],
    breadcrumbs: [],
    children: [],
    ...overrides,
});

describe('provision ordering helpers', () => {
    it('sorts by hierarchy path first', () => {
        const provisions = [
            baseNode({internal_id: 'b', hierarchy_path_ltree: '001.002'}),
            baseNode({internal_id: 'a', hierarchy_path_ltree: '001.001'}),
        ];

        const sorted = sortProvisions(provisions);
        expect(sorted.map(p => p.internal_id)).toEqual(['a', 'b']);
    });

    it('uses sibling order when hierarchy path matches', () => {
        const provisions = [
            baseNode({internal_id: 'b', hierarchy_path_ltree: '001', sibling_order: 20}),
            baseNode({internal_id: 'a', hierarchy_path_ltree: '001', sibling_order: 10}),
        ];

        const sorted = sortProvisions(provisions);
        expect(sorted.map(p => p.internal_id)).toEqual(['a', 'b']);
    });

    it('falls back to internal id for stability', () => {
        const provisions = [
            baseNode({internal_id: 'b', hierarchy_path_ltree: '001'}),
            baseNode({internal_id: 'a', hierarchy_path_ltree: '001'}),
        ];

        const sorted = sortProvisions(provisions);
        expect(sorted.map(p => p.internal_id)).toEqual(['a', 'b']);
    });

    it('handles missing sibling order values', () => {
        const a = baseNode({internal_id: 'a', hierarchy_path_ltree: '001', sibling_order: null});
        const b = baseNode({internal_id: 'b', hierarchy_path_ltree: '001', sibling_order: 5});

        expect(compareProvisions(a, b)).toBeGreaterThan(0);
        expect(compareProvisions(b, a)).toBeLessThan(0);
    });
});
