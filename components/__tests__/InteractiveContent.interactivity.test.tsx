import React from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import InteractiveContent from '../InteractiveContent';
import type {TaxDataObject} from '../../types';

vi.mock('react-markdown', () => ({
    __esModule: true,
    default: ({components}: any) => {
        const Paragraph = components?.p ?? ((props: any) => <p {...props} />);

        return (
            <div>
                <Paragraph>
                    {
                        'TAXABLE INCOME should not highlight tax within taxable income, but tax should still highlight. Another Tax item.'
                    }
                </Paragraph>
            </div>
        );
    },
}));

const baseNode: TaxDataObject = {
	internal_id: 'interactive-test-id',
	ref_id: 'interactive-test-ref',
	act_id: 'act',
    type: 'section',
    local_id: null,
    title: 'Test',
    content_md: 'placeholder',
    level: 1,
    hierarchy_path_ltree: '1',
    pagerank: 0,
    in_degree: 0,
    out_degree: 0,
	references_to: [],
	referenced_by: [],
	defined_terms_used: [
        {
            definition_internal_id: 'taxable-income',
            term_text: 'Taxable Income',
        },
        {
            definition_internal_id: 'tax-term',
            term_text: 'Tax',
		},
	],
	definitions_with_references: [],
	breadcrumbs: [],
	children: [],
};

describe('InteractiveContent term matching', () => {
    it('prefers longer matches and compares tokens case-insensitively', () => {
        const onTermClick = vi.fn();
        const onReferenceByRefIdClick = vi.fn();

        render(
            <InteractiveContent
                node={baseNode}
                onReferenceByRefIdClick={onReferenceByRefIdClick}
                onTermClick={onTermClick}
            />,
        );

        const taxableIncomeButton = screen.getByRole('button', {name: 'TAXABLE INCOME'});
        const lowercaseTaxableIncomeButton = screen.getByRole('button', {name: 'taxable income'});
        const [firstTaxButton] = screen.getAllByRole('button', {name: 'tax'});
        const capitalTaxButton = screen.getByRole('button', {name: 'Tax'});

        expect(screen.queryByRole('button', {name: 'TAXABLE'})).toBeNull();
        expect(screen.queryByRole('button', {name: 'taxable'})).toBeNull();

        fireEvent.click(taxableIncomeButton);
        fireEvent.click(lowercaseTaxableIncomeButton);
        fireEvent.click(firstTaxButton);
        fireEvent.click(capitalTaxButton);

        expect(onTermClick).toHaveBeenNthCalledWith(1, 'taxable-income', 'Taxable Income');
        expect(onTermClick).toHaveBeenNthCalledWith(2, 'taxable-income', 'Taxable Income');
        expect(onTermClick).toHaveBeenNthCalledWith(3, 'tax-term', 'Tax');
        expect(onTermClick).toHaveBeenNthCalledWith(4, 'tax-term', 'Tax');
        expect(onReferenceByRefIdClick).not.toHaveBeenCalled();
    });
});
