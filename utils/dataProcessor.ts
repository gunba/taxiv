import type { TaxDataObject } from "../types";

export interface ProcessedData {
    nodeMapByInternalId: Map<string, TaxDataObject>;
    nodeMapByRefId: Map<string, TaxDataObject>;
    definitionMapByTerm: Map<string, TaxDataObject>;
    childrenMap: Map<string, string[]>;
    tree: TaxDataObject[];
}

export function processRawData(rawData: Record<string, TaxDataObject>): ProcessedData {
    const nodeMapByInternalId = new Map<string, TaxDataObject>();
    const nodeMapByRefId = new Map<string, TaxDataObject>();
    const definitionMapByTerm = new Map<string, TaxDataObject>();
    const childrenMap = new Map<string, string[]>();

    // First pass: populate maps
    for (const internalId in rawData) {
        const node = rawData[internalId];
        nodeMapByInternalId.set(internalId, node);
        if (node.ref_id) {
            nodeMapByRefId.set(node.ref_id, node);
        }
        if (node.type === 'Definition' && node.raw_term) {
            definitionMapByTerm.set(node.raw_term.toLowerCase(), node);
        }
    }

    // Second pass: build hierarchy
    const tree: TaxDataObject[] = [];
    for (const node of nodeMapByInternalId.values()) {
        const parentId = node.parent_internal_id;
        if (parentId && nodeMapByInternalId.has(parentId)) {
            if (!childrenMap.has(parentId)) {
                childrenMap.set(parentId, []);
            }
            childrenMap.get(parentId)!.push(node.internal_id);
        } else {
            // It's a root node
            tree.push(node);
        }
    }

    // Sort children by their title/ID to maintain order
    for (const children of childrenMap.values()) {
        children.sort((aId, bId) => {
            const aNode = nodeMapByInternalId.get(aId);
            const bNode = nodeMapByInternalId.get(bId);
            return aNode?.title.localeCompare(bNode?.title ?? '', undefined, { numeric: true }) ?? 0;
        });
    }

    // Sort root nodes as well
    tree.sort((a, b) => a.title.localeCompare(b.title, undefined, { numeric: true }));

    return { nodeMapByInternalId, nodeMapByRefId, definitionMapByTerm, childrenMap, tree };
}
