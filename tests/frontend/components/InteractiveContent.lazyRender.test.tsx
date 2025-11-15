import React from 'react';
import {act, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import InteractiveContent from '@/components/InteractiveContent';
import type {TaxDataObject} from '@/types';

const mockReactMarkdown = vi.fn(({children}: any) => <div data-testid="markdown-chunk">{children}</div>);

vi.mock('react-markdown', () => ({
    __esModule: true,
    default: (props: any) => mockReactMarkdown(props),
}));

const observers: MockIntersectionObserver[] = [];

class MockIntersectionObserver {
    callback: IntersectionObserverCallback;
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();

    constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
    }

    trigger(entries: Partial<IntersectionObserverEntry>[]) {
        const formattedEntries = entries.map(entry => ({
            isIntersecting: entry.isIntersecting ?? true,
            target: entry.target as Element,
            intersectionRatio: entry.intersectionRatio ?? 1,
            time: entry.time ?? Date.now(),
            boundingClientRect: entry.boundingClientRect ?? {
                bottom: 0,
                height: 0,
                left: 0,
                right: 0,
                top: 0,
                width: 0,
                x: 0,
                y: 0,
                toJSON() {
                    return '';
                },
            },
            rootBounds: entry.rootBounds ?? null,
            intersectionRect: entry.intersectionRect ?? {
                bottom: 0,
                height: 0,
                left: 0,
                right: 0,
                top: 0,
                width: 0,
                x: 0,
                y: 0,
                toJSON() {
                    return '';
                },
            },
        })) as IntersectionObserverEntry[];

        this.callback(formattedEntries, this as unknown as IntersectionObserver);
    }
}

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
    observers.length = 0;
    mockReactMarkdown.mockClear();
    const intersectionObserverMock = vi.fn(function (this: unknown, callback: IntersectionObserverCallback) {
        const instance = new MockIntersectionObserver(callback);
        observers.push(instance);
        return instance as unknown as IntersectionObserver;
    });
    (window as any).IntersectionObserver = intersectionObserverMock as unknown as typeof IntersectionObserver;
});

afterEach(() => {
    delete (window as any).IntersectionObserver;
});

describe('InteractiveContent lazy rendering', () => {
    it('progressively renders oversized markdown as the sentinel enters view', async () => {
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
        expect(observers).not.toHaveLength(0);

        let sentinel = screen.getByTestId('chunk-sentinel');
        act(() => {
            observers[0].trigger([
                {
                    target: sentinel,
                    isIntersecting: true,
                },
            ]);
        });

        await waitFor(() => {
            expect(screen.getAllByTestId('markdown-chunk').length).toBeGreaterThan(initialChunkCount);
        });

        let iterations = 0;
        while (iterations < 10) {
            sentinel = document.querySelector('[data-testid="chunk-sentinel"]') as HTMLElement | null;
            if (!sentinel) {
                break;
            }

            const previousCount = mockReactMarkdown.mock.calls.length;
            act(() => {
                observers[0].trigger([
                    {
                        target: sentinel!,
                        isIntersecting: true,
                    },
                ]);
            });

            await waitFor(() => {
                expect(mockReactMarkdown.mock.calls.length).toBeGreaterThan(previousCount);
            });

            iterations += 1;
        }

        expect(document.querySelector('[data-testid="chunk-sentinel"]')).toBeNull();
        const finalChunkCount = screen.getAllByTestId('markdown-chunk').length;
        expect(finalChunkCount).toBeGreaterThan(initialChunkCount);
    });
});
