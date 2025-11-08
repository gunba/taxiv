// utils/api.ts
import type {HierarchyNode, TaxDataObject} from '../types';

// We use the path '/api' which Vite proxies to the backend container.
const API_BASE_PATH = '/api';

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unable to read error response body');
        console.error(`API Error: ${response.status} ${response.statusText} - ${errorText}`);
        throw new Error(`API request failed with status ${response.status}. Details: ${errorText}`);
    }
    return response.json() as Promise<T>;
}

export const api = {
    getHierarchy: async (actId: string, parentId?: string): Promise<HierarchyNode[]> => {
        const url = new URL(`${API_BASE_PATH}/provisions/hierarchy/${actId}`, window.location.origin);
        if (parentId) {
            url.searchParams.append('parent_id', parentId);
        }
        const response = await fetch(url.toString());
        return handleResponse<HierarchyNode[]>(response);
    },

    getProvisionDetail: async (internalId: string): Promise<TaxDataObject> => {
        const response = await fetch(`${API_BASE_PATH}/provisions/detail/${internalId}`);
        return handleResponse<TaxDataObject>(response);
    },

    getProvisionByRefId: async (refId: string, actId: string): Promise<TaxDataObject> => {
        const url = new URL(`${API_BASE_PATH}/provisions/lookup`, window.location.origin);
        url.searchParams.append('ref_id', refId);
        url.searchParams.append('act_id', actId);

        const response = await fetch(url.toString());
        const results = await handleResponse<TaxDataObject[]>(response);
        if (results.length === 0) {
            throw new Error(`Provision not found for Ref ID: ${refId} in Act: ${actId}`);
        }
        return results[0];
    },

    searchHierarchy: async (actId: string, query: string): Promise<HierarchyNode[]> => {
        const url = new URL(`${API_BASE_PATH}/provisions/search_hierarchy/${actId}`, window.location.origin);
        url.searchParams.append('query', query);

        const response = await fetch(url.toString());
        return handleResponse<HierarchyNode[]>(response);
    },

    getBreadcrumbs: async (internalId: string): Promise<{ internal_id: string; title: string }[]> => {
        const response = await fetch(`${API_BASE_PATH}/provisions/breadcrumbs/${internalId}`);
        return handleResponse<{ internal_id: string; title: string }[]>(response);
    },

    exportMarkdown: async ({
                               internalId,
                               includeDescendants = false,
                               signal,
                           }: {
        internalId: string;
        includeDescendants?: boolean;
        signal?: AbortSignal;
    }): Promise<string> => {
        const response = await fetch(`${API_BASE_PATH}/provisions/export_markdown`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                provision_internal_id: internalId,
                include_descendants: includeDescendants,
            }),
            signal,
        });
        const result = await handleResponse<{ markdown: string }>(response);
        return result.markdown;
    }
};


export type UnifiedSearchWhy = { type: string; detail: string; weight?: number | null };
export type UnifiedSearchItem = {
    id: string;
    ref_id: string;
    title: string;
    type: string;
    score_urs: number;
    why: UnifiedSearchWhy[];
    snippet?: string | null;
    metrics?: Record<string, number>;
};

export type UnifiedSearchResponse = {
    query_interpretation: {
        provisions: string[];
        definitions: string[];
        keywords: string;
        pseudo_seeds?: string[];
    };
    results: UnifiedSearchItem[];
    debug?: { mass_captured: number; num_seeds: number };
};

export const unifiedSearch = async (query: string, k = 25): Promise<UnifiedSearchResponse> => {
    const response = await fetch(`${API_BASE_PATH}/search/unified`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query, k, include_explanations: true})
    });
    return handleResponse<UnifiedSearchResponse>(response);
};
