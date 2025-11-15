import React from 'react';
import {render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import InteractiveContent from '@/components/InteractiveContent';
import type {TaxDataObject} from '@/types';

vi.mock('react-markdown', () => ({
	__esModule: true,
	default: ({components}: any) => {
		const Paragraph = components?.p ?? ((props: any) => <p {...props} />);

		return (
			<div>
				<Paragraph>{'(1) Top-level numeric'}</Paragraph>
				<Paragraph>{'(1A) Child numeric with letter'}</Paragraph>
				<Paragraph>{'(a) Letter level'}</Paragraph>
				<Paragraph>{'(aa) Double-letter child'}</Paragraph>
				<Paragraph>{'(i) Roman numeral child'}</Paragraph>
			</div>
		);
	},
}));

const baseNode: TaxDataObject = {
	internal_id: 'test-id',
	ref_id: 'ITAA1936:Section:6',
	act_id: 'ITAA1936',
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

describe('InteractiveContent enumeration marker indentation', () => {
	it('applies expected padding classes for ITAA-style markers', () => {
		const {container} = render(
			<InteractiveContent
				node={baseNode}
				onReferenceByRefIdClick={() => {}}
				onTermClick={() => {}}
			/>,
		);

		const paragraphs = container.querySelectorAll('p');
		expect(paragraphs.length).toBe(5);

		const [numeric, numericChild, letter, doubleLetter, roman] = Array.from(paragraphs);

		expect(numeric).toHaveClass('pl-6');
		expect(numericChild).toHaveClass('pl-6');
		expect(letter).toHaveClass('pl-12');
		expect(doubleLetter).toHaveClass('pl-[4.5rem]');
		expect(roman).toHaveClass('pl-[4.5rem]');
	});
});

