// utils/api.ts
import type { TaxDataObject, HierarchyNode } from '../types';

// We use the path '/api' which Vite proxies to the backend container.
const API_BASE_PATH = '/api';

async function fetchJson<T>(path: string): Promise<T> {
    const url = `${API_BASE_PATH}${path}`;
    const response = await fetch(url);
    if (!response.ok) {
        let errorText = response.statusText;
        try {
            const errorBody = await response.json();
            if (errorBody.detail) {
                errorText = errorBody.detail;
            }
        } catch (e) {
            // Ignore parsing error
        }
        throw new Error(`API request failed: ${response.status} - ${errorText}`);
    }
    return response.json() as Promise<T>;
}

export const api = {
    getHierarchy: async (actId: string, parentId?: string): Promise<HierarchyNode[]> => {
        const params = new URLSearchParams({ act_id: actId });
        if (parentId) {
            params.append('parent_id', parentId);
        }
        return fetchJson<HierarchyNode[]>(`/hierarchy?${params.toString()}`);
    },

    getProvisionDetail: async (internalId: string): Promise<TaxDataObject> => {
        return fetchJson<TaxDataObject>(`/provisions/${internalId}`);
    },
};
