import {describe, expect, it} from 'vitest';
import type {HierarchyNode} from '../../types';
import type {NodeFormattingInput} from '../../utils/nodeFormatting';
import {formatNodeHeading} from '../../utils/nodeFormatting';

describe('formatNodeHeading', () => {
    it('produces section variants with abbreviations and preserves existing titles', () => {
        const node: NodeFormattingInput = {
            type: 'Section',
            title: 'Section 355-100 Reporting obligations',
            local_id: '355-100',
            ref_id: 'ITAA1997:Section:355-100',
            act_id: 'ITAA1997',
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Section 355-100');
        expect(result.orderedLabelVariants).toEqual(
            expect.arrayContaining([
                'Section 355-100',
                'section 355-100',
                'Sect 355-100',
                'sect 355-100',
                's 355-100',
                'ITAA1997:Section:355-100',
            ]),
        );
        expect(result.markdownHeading).toBe('Section 355-100 Reporting obligations');
    });

    it('infers local identifiers for lowercase section types and combines title text', () => {
        const node: NodeFormattingInput = {
            type: 'section',
            title: 'Meaning of 10-5',
            local_id: null,
            ref_id: 'ITAA1997:Section:10-5',
            act_id: 'ITAA1997',
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Section 10-5');
        expect(result.markdownHeading).toBe('Section 10-5 — Meaning of 10-5');
    });

    it('formats parts with abbreviations and roman numerals', () => {
        const node: NodeFormattingInput = {
            type: 'Part',
            title: 'Part III Liability rules',
            local_id: 'III',
            ref_id: 'ITAA1936:Part:III',
            act_id: 'ITAA1936',
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Part III');
        expect(result.orderedLabelVariants).toEqual(expect.arrayContaining(['Pt III']));
        expect(result.markdownHeading).toBe('Part III Liability rules');
    });

    it('adds schedule section context and abbreviations', () => {
        const node: NodeFormattingInput = {
            type: 'Schedule:1:Section',
            title: 'Application of item 12-5',
            local_id: '12-5',
            ref_id: 'TAA1953:Schedule:1:Section:12-5',
            act_id: 'TAA1953',
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Schedule 1 Section 12-5');
        expect(result.orderedLabelVariants).toEqual(
            expect.arrayContaining(['Sch 1 s 12-5', 'schedule 1 section 12-5']),
        );
        expect(result.markdownHeading).toBe('Schedule 1 Section 12-5 — Application of item 12-5');
    });

    it('falls back to the title when type is unknown', () => {
        const node: NodeFormattingInput = {
            type: 'Definition',
            title: 'Defined term: taxable income',
            local_id: 'taxable_income',
            ref_id: 'ITAA1997:Definition:taxable_income',
            act_id: 'ITAA1997',
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Defined term: taxable income');
        expect(result.orderedLabelVariants).toContain('Defined term: taxable income');
        expect(result.markdownHeading).toBe('Defined term: taxable income');
    });

    it('supports hierarchy nodes without local_id metadata', () => {
        const node: HierarchyNode = {
            internal_id: 'part-2-1',
            ref_id: 'ITAA1997:Part:2-1',
            title: 'Part 2-1 Core rules',
            type: 'Part',
            has_children: true,
        };

        const result = formatNodeHeading(node);

        expect(result.preferredHeadingLabel).toBe('Part 2-1');
        expect(result.markdownHeading).toBe('Part 2-1 Core rules');
    });
});
