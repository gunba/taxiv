// utils/api.ts
import type {ActInfo, DatasetInfo, HierarchyNode, TaxDataObject} from '../types';

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

async function handleTextResponse(response: Response): Promise<string> {
    const bodyText = await response.text().catch(() => '');
    if (!response.ok) {
        console.error(`API Error: ${response.status} ${response.statusText} - ${bodyText}`);
        throw new Error(`API request failed with status ${response.status}. Details: ${bodyText || 'Unable to read error response body'}`);
    }
    return bodyText;
}

export const api = {
    getActs: async (): Promise<ActInfo[]> => {
        const response = await fetch(`${API_BASE_PATH}/acts`);
        return handleResponse<ActInfo[]>(response);
    },

    getDatasets: async (): Promise<DatasetInfo[]> => {
        const response = await fetch(`${API_BASE_PATH}/datasets`);
        return handleResponse<DatasetInfo[]>(response);
    },

    getHierarchy: async (actId: string, parentId?: string): Promise<HierarchyNode[]> => {
        const url = new URL(`${API_BASE_PATH}/provisions/hierarchy/${actId}`, window.location.origin);
        if (parentId) {
            url.searchParams.append('parent_id', parentId);
        }
        const response = await fetch(url.toString());
        return handleResponse<HierarchyNode[]>(response);
    },

    getProvisionDetail: async (
        internalId: string,
        options?: {
            includeBreadcrumbs?: boolean;
            includeChildren?: boolean;
            includeDefinitions?: boolean;
            includeReferences?: boolean;
            actId?: string;
        },
    ): Promise<TaxDataObject> => {
        const url = new URL(`${API_BASE_PATH}/provisions/detail/${internalId}`, window.location.origin);
        if (options?.includeBreadcrumbs) {
            url.searchParams.append('include_breadcrumbs', '1');
        }
        if (options?.includeChildren) {
            url.searchParams.append('include_children', '1');
        }
        if (options?.includeDefinitions) {
            url.searchParams.append('include_definitions', '1');
        }
        if (options?.includeReferences) {
            url.searchParams.append('include_references', '1');
        }
        if (options?.actId) {
            url.searchParams.append('act_id', options.actId);
        }
        const response = await fetch(url.toString());
        return handleResponse<TaxDataObject>(response);
    },

    getProvisionDetailMarkdown: async (internalId: string): Promise<string> => {
        const url = new URL(`${API_BASE_PATH}/provisions/detail/${internalId}`, window.location.origin);
        url.searchParams.append('format', 'markdown');
        const response = await fetch(url.toString(), {
            headers: {
                'Accept': 'text/plain',
            },
        });
        return handleTextResponse(response);
    },
    getVisibleSubtreeMarkdown: async (rootInternalId: string, visibleDescendantIds: string[]): Promise<string> => {
        const response = await fetch(`${API_BASE_PATH}/provisions/markdown_subtree`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/plain',
            },
            body: JSON.stringify({
                root_internal_id: rootInternalId,
                visible_descendant_ids: visibleDescendantIds,
            }),
        });
        return handleTextResponse(response);
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
};


export type UnifiedSearchItem = {
    id: string;
    act_id: string;
    ref_id: string;
    title: string;
    type: string;
    score_urs: number;
    content_snippet: string;
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

export const unifiedSearch = async (query: string, k = 25, actId?: string): Promise<UnifiedSearchResponse> => {
    const response = await fetch(`${API_BASE_PATH}/search/unified`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query, k, act_id: actId})
    });
    return handleResponse<UnifiedSearchResponse>(response);
};
