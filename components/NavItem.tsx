import React, { useState, useEffect } from 'react';
import type { TaxDataObject } from '../types';
import { ChevronRightIcon } from './Icons';
import { ProcessedData } from '../utils/dataProcessor';

interface NavItemProps {
  node: TaxDataObject;
  onSelectNode: (nodeId: string) => void;
  selectedNode: TaxDataObject | null;
  searchTerm: string;
  processedData: ProcessedData;
}

const NavItem: React.FC<NavItemProps> = ({ node, onSelectNode, selectedNode, searchTerm, processedData }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const isSelected = selectedNode?.internal_id === node.internal_id;
  const isParentOfSelected = selectedNode?.hierarchy_path.startsWith(node.hierarchy_path + node.type) ?? false;


  useEffect(() => {
    if (searchTerm || (isSelected || isParentOfSelected)) {
      setIsExpanded(true);
    }
  }, [searchTerm, isSelected, isParentOfSelected]);

  // FIX: When searching, the parent `SideNav` provides filtered children via a `children` property.
  // This logic checks for that property and falls back to the full children list if not searching.
  const children = 'children' in node 
    ? (node as any).children 
    : (processedData.childrenMap.get(node.internal_id) || []).map(id => processedData.nodeMapByInternalId.get(id)!).filter(Boolean);
  const hasChildren = children.length > 0;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (hasChildren) {
      setIsExpanded(!isExpanded);
    }
  };

  const handleSelect = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelectNode(node.internal_id);
    if(hasChildren && !isExpanded) {
        setIsExpanded(true);
    }
  };

  const basePadding = (node.level - 1) * 1.25;

  return (
    <li>
      <div
        onClick={handleSelect}
        className={`flex items-center justify-between p-2 my-1 rounded-md cursor-pointer transition-colors duration-150 ${
          isSelected ? 'bg-blue-600 text-white' : 'hover:bg-gray-700'
        }`}
        style={{ paddingLeft: `${basePadding + 0.5}rem` }}
      >
        <span className="truncate flex-grow">{node.title}</span>
        {hasChildren && (
          <button onClick={handleToggle} className="ml-2 p-1 rounded-full hover:bg-gray-600">
            <ChevronRightIcon className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
          </button>
        )}
      </div>
      {hasChildren && isExpanded && (
        <ul className="pl-2 border-l border-gray-600 ml-2">
          {children.map((child: TaxDataObject) => (
            <NavItem 
              key={child.internal_id} 
              node={child} 
              onSelectNode={onSelectNode} 
              selectedNode={selectedNode}
              searchTerm={searchTerm}
              processedData={processedData}
            />
          ))}
        </ul>
      )}
    </li>
  );
};

export default NavItem;