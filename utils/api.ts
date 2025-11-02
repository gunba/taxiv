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
    }
};