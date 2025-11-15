import React from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import InteractiveContent from '@/components/InteractiveContent';
import type {TaxDataObject} from '@/types';

const mockReactMarkdown = vi.fn(({children}: any) => <div data-testid="markdown-chunk">{children}</div>);

vi.mock('react-markdown', () => ({
    __esModule: true,
    default: (props: any) => mockReactMarkdown(props),
}));

const baseNode: TaxDataObject = {
    internal_id: 'lazy-render-test',
    ref_id: 'lazy-render-test-ref',
    act_id: 'act',
    type: 'section',
    local_id: null,
    title: 'Lazy Render Test',
    content_md: '',
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

beforeEach(() => {
    mockReactMarkdown.mockClear();
});

describe('InteractiveContent lazy rendering', () => {
    it('progressively renders oversized markdown when the user explicitly loads more', async () => {
        const paragraph = 'This is a test sentence for progressive rendering. '.repeat(30);
        const longMarkdown = Array.from({length: 8}, (_, index) => `Paragraph ${index + 1}: ${paragraph}`).join('\n\n');

        const node: TaxDataObject = {
            ...baseNode,
            content_md: longMarkdown,
        };

        render(
            <InteractiveContent
                node={node}
                onReferenceByRefIdClick={() => {
                }}
                onTermClick={() => {
                }}
            />,
        );

        expect(mockReactMarkdown).toHaveBeenCalled();
        const initialChunkCount = screen.getAllByTestId('markdown-chunk').length;
        expect(initialChunkCount).toBeGreaterThan(0);

        const totalParagraphs = longMarkdown.split('\n\n').length;
        expect(initialChunkCount).toBeLessThan(totalParagraphs);

        const loadMoreButton = screen.getByRole('button', {name: /load more/i});
        expect(loadMoreButton).toBeInTheDocument();

        fireEvent.click(loadMoreButton);

        await waitFor(() => {
            expect(screen.getAllByTestId('markdown-chunk').length).toBeGreaterThan(initialChunkCount);
        });
    });
});
