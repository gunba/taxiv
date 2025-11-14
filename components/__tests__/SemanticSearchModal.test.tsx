import React from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import SemanticSearchModal from '../SemanticSearchModal';
import type {UnifiedSearchItem} from '../../utils/api';

vi.mock('../../utils/api', async () => {
	const actual = await vi.importActual<typeof import('../../utils/api')>('../../utils/api');
	return {
		...actual,
		unifiedSearch: vi.fn(),
		api: {
			...actual.api,
			getProvisionDetail: vi.fn(),
			getProvisionDetailMarkdown: vi.fn(),
		},
	};
});

// Re-import after mocking so we get the mocked version
import {unifiedSearch} from '../../utils/api';

const acts = [
	{
		id: 'ITAA1997',
		title: 'Income Tax Assessment Act 1997',
		description: '',
		is_default: true,
	},
	{
		id: 'ITAA1936',
		title: 'Income Tax Assessment Act 1936',
		description: '',
		is_default: false,
	},
];

describe('SemanticSearchModal', () => {
	it('scopes search to the current Act by default', async () => {
		vi.clearAllMocks();
		(unifiedSearch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
			results: [],
		});

		const {getByLabelText, getByRole} = render(
			<SemanticSearchModal
				isOpen
				actId="ITAA1936"
				acts={acts}
				onClose={vi.fn()}
				onSelectAct={vi.fn()}
				onSelectProvision={vi.fn()}
				state={{query: '', results: []}}
				onStateChange={vi.fn()}
			/>,
		);

		const input = getByLabelText('Query');
		fireEvent.change(input, {target: {value: 'medicare levy'}});

		const searchButton = getByRole('button', {name: /^Search$/});
		fireEvent.click(searchButton);

		await waitFor(() => {
			expect(unifiedSearch).toHaveBeenCalledWith('medicare levy', 25, 'ITAA1936');
		});
	});

	it('supports searching across all Acts', async () => {
		vi.clearAllMocks();
		const item: UnifiedSearchItem = {
			id: 'ITAA1936_Section_8-1',
			act_id: 'ITAA1936',
			ref_id: 'ITAA1936:Section:8-1',
			title: 'Medicare levy',
			type: 'Section',
			score_urs: 90,
			content_snippet: 'Sample snippet',
		};

		(unifiedSearch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
			results: [item],
		});

		const {getAllByLabelText, getByLabelText, getAllByRole, getAllByText} = render(
			<SemanticSearchModal
				isOpen
				actId="ITAA1997"
				acts={acts}
				onClose={vi.fn()}
				onSelectAct={vi.fn()}
				onSelectProvision={vi.fn()}
				state={{query: '', results: []}}
				onStateChange={vi.fn()}
			/>,
		);

		const [scopeSelect] = getAllByLabelText('Semantic search scope');
		fireEvent.change(scopeSelect, {target: {value: 'all'}});

		await waitFor(() => {
			expect(scopeSelect).toHaveValue('all');
		});

		const input = getByLabelText('Query');
		fireEvent.change(input, {target: {value: 'medicare levy'}});

		const [searchButton] = getAllByRole('button', {name: /^Search$/});
		fireEvent.click(searchButton);

		await waitFor(() => {
			expect(unifiedSearch).toHaveBeenCalledWith('medicare levy', 25, '*');
		});

		// Act label should be rendered alongside the result metadata.
		await waitFor(() => {
			const matches = getAllByText('Income Tax Assessment Act 1936', {exact: false});
			expect(matches.length).toBeGreaterThan(0);
		});
	});
});
