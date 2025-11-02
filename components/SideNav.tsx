// components/SideNav.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { HierarchyNode } from '../types';
import { api } from '../utils/api';
import { ChevronRightIcon, SearchIcon } from './Icons';

// --- Node Item Component ---
interface NavNodeProps {
  node: HierarchyNode;
  actId: string;
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string | null;
  level: number;
  isSearchActive: boolean;
}

const NavNode: React.FC<NavNodeProps> = ({
  node,
  actId,
  onSelectNode,
  selectedNodeId,
  level,
  isSearchActive,
}) => {
  const embeddedChildren = node.children;
  const [fetchedChildren, setFetchedChildren] = useState<HierarchyNode[] | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const isSelected = node.internal_id === selectedNodeId;

  const children = isSearchActive ? embeddedChildren : fetchedChildren;
  const hasChildren = isSearchActive
    ? Boolean(embeddedChildren && embeddedChildren.length > 0)
    : node.has_children;

  useEffect(() => {
    if (isSearchActive && hasChildren) {
      setIsExpanded(true);
    } else if (!isSearchActive) {
      setIsExpanded(false);
    }
  }, [isSearchActive, hasChildren]);

  const toggleExpand = useCallback(async (event?: React.MouseEvent) => {
    event?.stopPropagation();
    if (!hasChildren) return;

    if (isSearchActive) {
      setIsExpanded(prev => !prev);
      return;
    }

    if (!isExpanded && fetchedChildren === null) {
      setIsLoading(true);
      try {
        const data = await api.getHierarchy(actId, node.internal_id);
        setFetchedChildren(data);
        setIsExpanded(true);
      } catch (error) {
        console.error('Failed to fetch children:', error);
      } finally {
        setIsLoading(false);
      }
    } else {
      setIsExpanded(prev => !prev);
    }
  }, [hasChildren, isSearchActive, isExpanded, fetchedChildren, actId, node.internal_id]);

  const handleSelect = (event: React.MouseEvent) => {
    event.stopPropagation();
    onSelectNode(node.internal_id);

    if (hasChildren && !isExpanded && !isSearchActive) {
      void toggleExpand();
    }
  };

  const levelIndicators = level > 1
    ? (
      <div className="flex shrink-0 items-center gap-1 text-gray-600/60" aria-hidden="true">
        {Array.from({ length: level - 1 }).map((_, index) => (
          <span
            key={index}
            className="inline-block h-1.5 w-1.5 rounded-full bg-gray-600/40"
          />
        ))}
      </div>
    )
    : <span className="w-3 shrink-0" aria-hidden="true" />;

  const label = node.title || node.type;

  const itemClasses = isSelected
    ? 'bg-blue-600 text-white shadow-sm'
    : 'text-gray-300 hover:bg-gray-700/70 hover:text-white';

  const expandButtonClasses = isSelected
    ? 'text-white'
    : 'text-gray-400 group-hover:text-white';

  return (
    <li>
      <div
        onClick={handleSelect}
        className={`group flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer transition-colors ${itemClasses}`}
      >
        {levelIndicators}
        {(hasChildren || isLoading) ? (
          <button
            type="button"
            onClick={toggleExpand}
            className={`flex h-5 w-5 items-center justify-center rounded transition-colors ${expandButtonClasses}`}
            aria-label={isExpanded ? 'Collapse section' : 'Expand section'}
          >
            {isLoading ? (
              <span className="text-xs">...</span>
            ) : (
              <ChevronRightIcon className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
            )}
          </button>
        ) : (
          <span
            className={`flex h-5 w-5 items-center justify-center text-gray-500/70 ${isSelected ? 'text-white/70' : 'group-hover:text-white/70'}`}
            aria-hidden="true"
          >
            •
          </span>
        )}

        <span className="flex-1 truncate text-sm font-medium">
          {label}
        </span>
      </div>

      {isExpanded && children && children.length > 0 && (
        <ul className="mt-1 space-y-1 pl-2">
          {children.map(child => (
            <NavNode
              key={child.internal_id}
              node={child}
              actId={actId}
              onSelectNode={onSelectNode}
              selectedNodeId={selectedNodeId}
              level={level + 1}
              isSearchActive={isSearchActive}
            />
          ))}
        </ul>
      )}
    </li>
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
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<HierarchyNode[] | null>(null);
  const [isSearchLoading, setIsSearchLoading] = useState(false);

  useEffect(() => {
    const fetchInitialHierarchy = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const nodes = await api.getHierarchy(actId);
        setTopLevelNodes(nodes);
      } catch (err) {
        console.error('Failed to load initial hierarchy:', err);
        setError('Could not load navigation structure.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitialHierarchy();
  }, [actId]);

  useEffect(() => {
    if (!searchTerm) {
      setSearchResults(null);
      if (error?.includes('Search failed')) {
        setError(null);
      }
      return;
    }

    const debounce = setTimeout(() => {
      const performSearch = async () => {
        setIsSearchLoading(true);
        if (error?.includes('Search failed')) {
          setError(null);
        }
        try {
          const results = await api.searchHierarchy(actId, searchTerm);
          setSearchResults(results);
        } catch (err) {
          console.error('Failed to search:', err);
          setError('Search failed. Ensure the backend search endpoint is implemented.');
          setSearchResults([]);
        } finally {
          setIsSearchLoading(false);
        }
      };

      void performSearch();
    }, 300);

    return () => clearTimeout(debounce);
  }, [searchTerm, actId, error]);

  const isSearchActive = searchResults !== null;
  const nodesToDisplay = isSearchActive ? searchResults : topLevelNodes;

  if (isLoading) {
    return <div className="p-4 text-gray-400">Loading navigation...</div>;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 p-4">
        <div className="relative">
          <input
            type="text"
            placeholder="Search code..."
            value={searchTerm}
            onChange={event => setSearchTerm(event.target.value)}
            className="w-full rounded-md border border-gray-600 bg-gray-900 py-2 pl-10 pr-4 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <SearchIcon className="h-5 w-5 text-gray-400" />
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 pb-2 text-sm text-red-400">{error}</div>
      )}

      <nav className="flex-1 overflow-y-auto px-4 pb-4">
        {isSearchLoading && <div className="p-2 text-gray-400">Searching...</div>}

        {!isSearchLoading && !error && nodesToDisplay.length === 0 && (
          <div className="p-2 text-gray-400">
            {isSearchActive ? 'No results found.' : 'Navigation structure is empty.'}
          </div>
        )}

        {!isSearchLoading && (
          <ul className="space-y-1">
            {nodesToDisplay.map(node => (
              <NavNode
                key={node.internal_id}
                node={node}
                actId={actId}
                onSelectNode={onSelectNode}
                selectedNodeId={selectedNodeId}
                level={1}
                isSearchActive={isSearchActive}
              />
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
};

export default SideNav;
