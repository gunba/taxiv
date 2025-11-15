import React from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import InteractiveContent from '../InteractiveContent';
import type {TaxDataObject} from '../../types';

vi.mock('react-markdown', () => ({
	__esModule: true,
	default: ({components, children}: any) => {
		const Paragraph = components?.p ?? ((props: any) => <p {...props} />);
		return (
			<div>
				<Paragraph>{children}</Paragraph>
			</div>
		);
	},
}));

const baseNode: TaxDataObject = {
	internal_id: 'root-id',
	ref_id: 'ITAA1997:Section:6-5',
	act_id: 'ITAA1997',
	type: 'Section',
	local_id: '6-5',
	title: 'Ordinary income',
	content_md: 'See s 6 of the 1936 Act.',
	level: 5,
	hierarchy_path_ltree: 'ITAA1997.Root.6_5',
	pagerank: 0,
	in_degree: 0,
	out_degree: 0,
	references_to: [
		{
			target_ref_id: 'ITAA1936:Section:6',
			snippet: 's 6 of the 1936 Act',
			target_title: 'Interpretation',
			target_internal_id: 'ITAA1936_Section_6',
		},
	],
	referenced_by: [],
	defined_terms_used: [],
	definitions_with_references: [],
	breadcrumbs: [],
	children: [],
};

describe('InteractiveContent reference handling', () => {
	it('treats cross-act references with internal targets as internal (in-app) links', () => {
		const onTermClick = vi.fn();
		const onReferenceByRefIdClick = vi.fn();

		render(
			<InteractiveContent
				node={baseNode}
				onReferenceByRefIdClick={onReferenceByRefIdClick}
				onTermClick={onTermClick}
			/>,
		);

		const refToken = screen.getByRole('button', {name: 's 6 of the 1936 Act'});
		expect(refToken).toBeInTheDocument();

		fireEvent.click(refToken);
		expect(onReferenceByRefIdClick).toHaveBeenCalledWith('ITAA1936:Section:6');
		expect(onTermClick).not.toHaveBeenCalled();
	});
});

