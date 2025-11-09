import React from 'react';
import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, describe, expect, it, vi} from 'vitest';
import type {HierarchyNode} from '@/types';
import {NavNode} from '@/components/SideNav';

const copyToClipboardMock = vi.fn<(text: string) => Promise<void>>().mockResolvedValue();

const showToastMock = vi.fn();

vi.mock('@/components/ToastProvider', () => ({
    ToastProvider: ({children}: { children: React.ReactNode }) => <>{children}</>,
    useToast: () => ({showToast: showToastMock}),
}));

vi.mock('@/utils/clipboard', () => ({
    copyToClipboard: (text: string) => copyToClipboardMock(text),
}));

const baseNode: HierarchyNode = {
    internal_id: 'node-1',
    ref_id: 'ref-1',
    title: 'Sample Node',
    type: 'section',
    has_children: false,
    children: null,
};

const renderNavNode = (
    overrides: Partial<HierarchyNode> = {},
    options: Partial<{
        onCopyMarkdown: (node: HierarchyNode) => Promise<string>;
        isExpanded: boolean;
    }> = {},
) => {
    const onCopyMarkdown =
        options.onCopyMarkdown ?? vi.fn<(node: HierarchyNode) => Promise<string>>().mockResolvedValue('# heading');
    const isExpanded = options.isExpanded ?? false;
    return {
        onCopyMarkdown,
        ...render(
            <ul>
                <NavNode
                    node={{...baseNode, ...overrides}}
                    onSelectNode={vi.fn()}
                    selectedNodeId={null}
                    level={0}
                    isSearchActive={false}
                    onToggleNode={vi.fn()}
                    resolveChildren={(): HierarchyNode[] => []}
                    getIsExpanded={() => isExpanded}
                    getIsLoadingChildren={() => false}
                    onCopyMarkdown={onCopyMarkdown}
                />
            </ul>,
        ),
    };
};

beforeEach(() => {
    vi.restoreAllMocks();
    showToastMock.mockReset();
    copyToClipboardMock.mockReset();
    copyToClipboardMock.mockResolvedValue();
});

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe('NavNode export controls', () => {
    it('reveals export actions on hover and copies node markdown', async () => {
        const user = userEvent.setup();

        const {onCopyMarkdown} = renderNavNode();

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

        expect(onCopyMarkdown).toHaveBeenCalledWith(expect.objectContaining({internal_id: 'node-1'}));

        await waitFor(() => {
            expect(copyToClipboardMock).toHaveBeenCalledWith('# heading');
        });

        expect(showToastMock).toHaveBeenCalledWith(
            expect.objectContaining({
                title: 'Markdown copied',
                variant: 'success',
            }),
        );
    });

    it('disables actions while export is pending and prevents concurrent requests', async () => {
        let resolveExport: (value: string) => void = () => {};
        const onCopyMarkdown = vi.fn(
            () =>
                new Promise<string>(resolve => {
                    resolveExport = resolve;
                }),
        );
        const user = userEvent.setup();

        renderNavNode({}, {onCopyMarkdown});

        const copyButton = screen.getByRole('button', {
            name: 'Copy markdown for Sample Node to clipboard',
            exact: true,
        });
        const row = copyButton.closest('div')?.parentElement as HTMLElement;
        await user.hover(row);

        await user.click(copyButton);

        expect(onCopyMarkdown).toHaveBeenCalledTimes(1);

        expect(copyButton).toBeDisabled();

        await user.click(copyButton);
        expect(onCopyMarkdown).toHaveBeenCalledTimes(1);

        resolveExport('## done');

        await waitFor(() => {
            expect(copyButton).not.toBeDisabled();
        });

        expect(copyToClipboardMock).toHaveBeenCalledWith('## done');
    });

    it('surfaces error feedback when export fails', async () => {
        const onCopyMarkdown = vi.fn().mockRejectedValue(new Error('Network unavailable'));
        const user = userEvent.setup();

        renderNavNode({}, {onCopyMarkdown});

        const copyButton = screen.getByRole('button', {
            name: 'Copy markdown for Sample Node to clipboard',
            exact: true,
        });
        const row = copyButton.closest('div')?.parentElement as HTMLElement;
        await user.hover(row);

        await user.click(copyButton);

        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith(
                expect.objectContaining({
                    title: 'Failed to copy markdown',
                    variant: 'error',
                }),
            );
        });
    });
});
