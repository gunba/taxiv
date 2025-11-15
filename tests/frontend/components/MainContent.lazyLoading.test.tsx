import React from 'react';
import {act, render, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import MainContent from '@/components/MainContent';
import type {TaxDataObject} from '@/types';
import * as apiModule from '@/utils/api';

let mainElement: HTMLElement | null = null;

const baseNode: TaxDataObject = {
    internal_id: 'main-content-root',
    ref_id: '6',
    act_id: 'itaa-1936',
    type: 'section',
    local_id: null,
    title: '6 Interpretation',
    content_md: 'Root content',
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

describe('MainContent provision lazy loading', () => {
    beforeEach(() => {
        mainElement = document.createElement('main');
        (mainElement as any).scrollTo = vi.fn();
        document.body.appendChild(mainElement);

        vi.spyOn(apiModule.api, 'getHierarchy').mockImplementation(async (_actId: string, internalId: string) => {
            if (internalId === baseNode.internal_id) {
                return [
                    {internal_id: 'child-1', ref_id: '6(1)', title: 'Child 1', type: 'definition'},
                    {internal_id: 'child-2', ref_id: '6(2)', title: 'Child 2', type: 'definition'},
                    {internal_id: 'child-3', ref_id: '6(3)', title: 'Child 3', type: 'definition'},
                ];
            }
            return [];
        });

        vi.spyOn(apiModule.api, 'getProvisionDetail').mockImplementation(async (id: string) => ({
            ...baseNode,
            internal_id: id,
            ref_id: id,
            title: `Detail for ${id}`,
        }));
    });

    afterEach(() => {
        if (mainElement && mainElement.parentNode) {
            mainElement.parentNode.removeChild(mainElement);
            mainElement = null;
        }
        vi.restoreAllMocks();
    });

    it('loads additional provisions when scrolling near the bottom without chaining at the same position', async () => {
        const {api} = apiModule;

        render(
            <MainContent
                node={baseNode}
                breadcrumbs={[]}
                isLoading={false}
                onTermClick={() => {
                }}
                onReferenceByRefIdClick={() => {
                }}
                onSelectNode={() => {
                }}
            />,
        );

        // Initial hierarchy fetch for the root node
        await waitFor(() => {
            expect(api.getHierarchy).toHaveBeenCalledTimes(1);
        });

        // First child should load immediately via the "first child" effect
        await waitFor(() => {
            expect(api.getProvisionDetail).toHaveBeenCalledTimes(1);
        });

        // Simulate scrolling near the bottom of the main container
        act(() => {
            Object.defineProperty(mainElement!, 'clientHeight', {
                value: 600,
                configurable: true,
            });
            Object.defineProperty(mainElement!, 'scrollHeight', {
                value: 2000,
                configurable: true,
            });
            (mainElement as any).scrollTop = 1500;
            mainElement!.dispatchEvent(new Event('scroll'));
        });

        await waitFor(() => {
            expect(api.getProvisionDetail).toHaveBeenCalledTimes(2);
        });

        // Additional scroll events at the same position should not trigger extra loads
        act(() => {
            mainElement!.dispatchEvent(new Event('scroll'));
            mainElement!.dispatchEvent(new Event('scroll'));
        });

        await waitFor(() => {
            expect(api.getProvisionDetail).toHaveBeenCalledTimes(2);
        });
    });
});
