import type {TaxDataObject} from '../types';

const DEFAULT_SIBLING_ORDER = Number.MAX_SAFE_INTEGER;

const normalizePath = (path?: string | null): string => path ?? '';

const normalizeSiblingOrder = (order?: number | null): number => {
    if (order === null || typeof order === 'undefined') {
        return DEFAULT_SIBLING_ORDER;
    }
    return order;
};

export const compareProvisions = (a: TaxDataObject, b: TaxDataObject): number => {
    const pathComparison = normalizePath(a.hierarchy_path_ltree).localeCompare(
        normalizePath(b.hierarchy_path_ltree),
        'en',
        {numeric: true, sensitivity: 'base'},
    );
    if (pathComparison !== 0) {
        return pathComparison;
    }

    const siblingComparison = normalizeSiblingOrder(a.sibling_order) - normalizeSiblingOrder(b.sibling_order);
    if (siblingComparison !== 0) {
        return siblingComparison;
    }

    return a.internal_id.localeCompare(b.internal_id, 'en', {numeric: true, sensitivity: 'base'});
};

export const sortProvisions = <T extends TaxDataObject>(provisions: T[]): T[] => {
    return [...provisions].sort(compareProvisions);
};
