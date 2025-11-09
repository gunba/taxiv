import React from 'react';
import {render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import InteractiveContent from '../InteractiveContent';
import type {TaxDataObject} from '../../types';

vi.mock('react-markdown', () => ({
    __esModule: true,
    default: ({components}: any) => {
        const Paragraph = components?.p ?? ((props: any) => <p {...props} />);
        const ListItem = components?.li ?? ((props: any) => <li {...props} />);

        return (
            <div>
                <Paragraph>{'    Wrapped paragraph line one\n    line two continues for indentation testing.'}</Paragraph>
                <ul>
                    <ListItem>{'      Secondary list item line\n      that wraps to confirm spacing.'}</ListItem>
                </ul>
            </div>
        );
    },
}));

const baseNode: TaxDataObject = {
	internal_id: 'test-id',
	ref_id: 'test-ref',
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
	defined_terms_used: [],
	definitions_with_references: [],
	breadcrumbs: [],
	children: [],
};

describe('InteractiveContent indentation handling', () => {
    it('applies Tailwind padding classes for four-space indentation', () => {
        const {container} = render(
            <InteractiveContent
                node={baseNode}
                onReferenceByRefIdClick={() => {
                }}
                onTermClick={() => {
                }}
            />,
        );

        const paragraph = container.querySelector('p');

        expect(paragraph).toBeInTheDocument();
        expect(paragraph).toHaveClass('pl-4');
        expect(paragraph?.textContent).toBe(
            'Wrapped paragraph line one\nline two continues for indentation testing.',
        );
    });

    it('falls back to inline padding for non-multiple indentation widths', () => {
        const {container} = render(
            <InteractiveContent
                node={baseNode}
                onReferenceByRefIdClick={() => {
                }}
                onTermClick={() => {
                }}
            />,
        );

        const listItem = container.querySelector('li');

        expect(listItem).toBeInTheDocument();
        expect(listItem).not.toHaveClass('pl-4');
        expect(listItem).toHaveStyle({paddingLeft: '1.5rem'});
        expect(listItem?.textContent).toBe('Secondary list item line\nthat wraps to confirm spacing.');
    });
});
