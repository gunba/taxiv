// components/SideNav.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { HierarchyNode } from '../types';
import { api } from '../utils/api';
import { ChevronRightIcon } from './Icons';

// --- Node Item Component ---
interface NavNodeProps {
  node: HierarchyNode;
  actId: string;
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string | null;
  level: number;
}

const NavNode: React.FC<NavNodeProps> = ({ node, actId, onSelectNode, selectedNodeId, level }) => {
  const [children, setChildren] = useState<HierarchyNode[] | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const isSelected = node.internal_id === selectedNodeId;

  const toggleExpand = useCallback(async (event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent triggering the node selection when toggling
    if (!node.has_children) return;

    if (!isExpanded && children === null) {
      setIsLoading(true);
      try {
        const fetchedChildren = await api.getHierarchy(actId, node.internal_id);
        setChildren(fetchedChildren);
        setIsExpanded(true);
      } catch (error) {
        console.error("Failed to fetch children:", error);
      } finally {
        setIsLoading(false);
      }
    } else {
      setIsExpanded(!isExpanded);
    }
  }, [isExpanded, children, node.internal_id, actId, node.has_children]);

  const indentation = `${level * 20}px`;

  // Determine display name based on ref_id (e.g., "10-5" or "Chapter 1")
  let displayName = node.type;
  if (node.ref_id) {
    const parts = node.ref_id.split(':');
    if (parts.length > 2) {
      displayName = parts.slice(2).join(':');
    }
  }

  return (
    <div>
    <div
    className={`flex items-center p-2 cursor-pointer hover:bg-gray-700 ${isSelected ? 'bg-blue-900 text-white' : 'text-gray-300'}`}
    style={{ paddingLeft: indentation }}
    onClick={() => onSelectNode(node.internal_id)}
    >
    {/* Expand/Collapse Icon */}
    <div onClick={toggleExpand} className="w-5 h-5 flex items-center justify-center mr-2">
    {isLoading ? (
      <span className="text-xs">...</span>
    ) : node.has_children ? (
      <ChevronRightIcon className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
    ) : (
      <span className="text-gray-500">•</span>
    )}
    </div>

    {/* Node Title */}
    <span className="flex-1 truncate text-sm font-medium">
    {displayName}
    </span>
    <span className="text-xs text-gray-500 truncate hidden lg:inline ml-2" title={node.title}>
    {node.title !== displayName ? node.title : ''}
    </span>
    </div>

    {/* Children */}
    {isExpanded && children && (
      <div>
      {children.map(child => (
        <NavNode
        key={child.internal_id}
        node={child}
        actId={actId}
        onSelectNode={onSelectNode}
        selectedNodeId={selectedNodeId}
        level={level + 1}
        />
      ))}
      </div>
    )}
    </div>
  );
};


// --- Main SideNav Component ---
interface SideNavProps {
  actId: string;
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string | null;
}

const SideNav: React.FC<SideNavProps> = ({ actId, onSelectNode, selectedNodeId }) => {
  const [topLevelNodes, setTopLevelNodes] = useState<HierarchyNode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchInitialHierarchy = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const nodes = await api.getHierarchy(actId);
        setTopLevelNodes(nodes);
      } catch (err) {
        console.error("Failed to load initial hierarchy:", err);
        setError("Could not load navigation structure.");
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitialHierarchy();
  }, [actId]);

  if (isLoading) {
    return <div className="p-4 text-gray-400">Loading navigation...</div>;
  }

  if (error) {
    return <div className="p-4 text-red-400">{error}</div>;
  }

  return (
    <nav className="flex-1 overflow-y-auto py-2">
    {topLevelNodes.map(node => (
      <NavNode
      key={node.internal_id}
      node={node}
      actId={actId}
      onSelectNode={onSelectNode}
      selectedNodeId={selectedNodeId}
      level={1}
      />
    ))}
    </nav>
  );
};

export default SideNav;
