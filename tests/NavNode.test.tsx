import React from 'react';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, describe, expect, it, vi} from 'vitest';
import type {HierarchyNode} from '@/types';
import {exportMarkdownToClipboard} from '@/utils/exportMarkdown';
import {NavNode} from '@/components/SideNav';

vi.mock('@/utils/exportMarkdown', () => ({
    exportMarkdownToClipboard: vi.fn(),
}));

const mockedExportMarkdown = vi.mocked(exportMarkdownToClipboard);

const baseNode: HierarchyNode = {
    internal_id: 'node-1',
    ref_id: 'ref-1',
    title: 'Sample Node',
    type: 'section',
    has_children: false,
    children: null,
};

const renderNavNode = (overrides: Partial<HierarchyNode> = {}) => {
    return render(
        <ul>
            <NavNode
                node={{...baseNode, ...overrides}}
                actId="act-1"
                onSelectNode={vi.fn()}
                selectedNodeId={null}
                level={0}
                isSearchActive={false}
            />
        </ul>,
    );
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe('NavNode export controls', () => {
    it('reveals export actions on hover and copies node markdown', async () => {
        mockedExportMarkdown.mockResolvedValue({status: 'success', markdown: '# heading'});
        const user = userEvent.setup();

        renderNavNode();

        const copyButton = screen.getByRole('button', {
            name: 'Copy markdown for Sample Node to clipboard',
            exact: true,
        });

        const actionsContainer = copyButton.parentElement as HTMLElement;
        expect(actionsContainer.className).toContain('opacity-0');
        expect(actionsContainer.className).toContain('pointer-events-none');

        const row = copyButton.closest('div')?.parentElement as HTMLElement;
        await user.hover(row);

        expect(actionsContainer.className).not.toContain('opacity-0');
        expect(actionsContainer.className).not.toContain('pointer-events-none');

        await user.click(copyButton);

        expect(mockedExportMarkdown).toHaveBeenCalledWith(
            expect.objectContaining({
                internalId: 'node-1',
                includeDescendants: true,
            }),
        );

        await waitFor(() => {
            expect(screen.getByRole('status')).toHaveTextContent('Markdown copied to clipboard.');
        });
    });

    it('disables actions while export is pending and prevents concurrent requests', async () => {
        let resolveExport: (value: { status: 'success'; markdown: string }) => void = () => {};
        mockedExportMarkdown.mockImplementation(
            () =>
                new Promise(resolve => {
                    resolveExport = resolve;
                }),
        );
        const user = userEvent.setup();

        renderNavNode();

        const copyButton = screen.getByRole('button', {
            name: 'Copy markdown for Sample Node to clipboard',
            exact: true,
        });
        const row = copyButton.closest('div')?.parentElement as HTMLElement;
        await user.hover(row);

        await user.click(copyButton);

        expect(mockedExportMarkdown).toHaveBeenCalledTimes(1);
        expect(mockedExportMarkdown).toHaveBeenCalledWith(
            expect.objectContaining({
                internalId: 'node-1',
                includeDescendants: true,
            }),
        );

        expect(copyButton).toBeDisabled();

        await user.click(copyButton);
        expect(mockedExportMarkdown).toHaveBeenCalledTimes(1);

        resolveExport({status: 'success', markdown: '## done'});

        await waitFor(() => {
            expect(copyButton).not.toBeDisabled();
        });
    });

    it('surfaces error feedback when export fails', async () => {
        mockedExportMarkdown.mockResolvedValue({
            status: 'error',
            error: new Error('Network unavailable'),
        });
        const user = userEvent.setup();

        renderNavNode();

        const copyButton = screen.getByRole('button', {
            name: 'Copy markdown for Sample Node to clipboard',
            exact: true,
        });
        const row = copyButton.closest('div')?.parentElement as HTMLElement;
        await user.hover(row);

        await user.click(copyButton);

        await waitFor(() => {
            expect(screen.getByRole('status')).toHaveTextContent('Network unavailable');
        });
    });
});
