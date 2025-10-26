import React, { useState, useMemo } from 'react';
import type { TaxDataObject } from '../types';
import NavItem from './NavItem';
import { SearchIcon } from './Icons';
import { ProcessedData } from '../utils/dataProcessor';

interface SideNavProps {
  nodes: TaxDataObject[];
  onSelectNode: (nodeId: string) => void;
  selectedNode: TaxDataObject | null;
  processedData: ProcessedData;
}

const SideNav: React.FC<SideNavProps> = ({ nodes, onSelectNode, selectedNode, processedData }) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredNodes = useMemo(() => {
    if (!searchTerm) {
      return nodes;
    }

    const lowercasedFilter = searchTerm.toLowerCase();
    const filteredIds = new Set<string>();

    for (const node of processedData.nodeMapByInternalId.values()) {
        if (node.title.toLowerCase().includes(lowercasedFilter) || (node.id && node.id.toLowerCase().includes(lowercasedFilter))) {
            let current = node;
            while(current) {
                filteredIds.add(current.internal_id);
                if (!current.parent_internal_id) break;
                current = processedData.nodeMapByInternalId.get(current.parent_internal_id)!;
            }
        }
    }

    // FIX: Changed return type to any[] to allow for a filtered tree structure with a `children` property.
    const filter = (nodesToFilter: TaxDataObject[]): any[] => {
      // FIX: Changed accumulator type to any[] to support adding a `children` property to nodes for filtering.
      return nodesToFilter.reduce((acc: any[], node) => {
        if (filteredIds.has(node.internal_id)) {
          const childIds = processedData.childrenMap.get(node.internal_id) || [];
          const childrenNodes = childIds.map(id => processedData.nodeMapByInternalId.get(id)!).filter(Boolean);
          const children = filter(childrenNodes);
          acc.push({ ...node, children });
        }
        return acc;
      }, []);
    };

    return filter(nodes);
  }, [nodes, searchTerm, processedData]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 shrink-0">
        <div className="relative">
          <input
            type="text"
            placeholder="Search code..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded-md py-2 pl-10 pr-4 focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <SearchIcon className="w-5 h-5 text-gray-400" />
          </div>
        </div>
      </div>
      <nav className="flex-grow overflow-y-auto px-4 pb-4">
        <ul>
          {filteredNodes.map((node) => (
            <NavItem 
              key={node.internal_id} 
              node={node} 
              onSelectNode={onSelectNode} 
              selectedNode={selectedNode}
              searchTerm={searchTerm}
              processedData={processedData}
            />
          ))}
        </ul>
      </nav>
    </div>
  );
};

export default SideNav;