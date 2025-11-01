// components/SideNav.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { HierarchyNode } from '../types';
import { api } from '../utils/api';
import { ChevronRightIcon, SearchIcon } from './Icons';

// --- Node Item Component (NavNode) ---
// Merges lazy-loading logic from the new version with the styling and interaction of the original NavItem.
interface NavNodeProps {
  node: HierarchyNode;
  actId: string;
  onSelectNode: (nodeId: string) => void;
  selectedNodeId: string | null;
  level: number;
  isSearchActive: boolean;
}

const NavNode: React.FC<NavNodeProps> = ({ node, actId, onSelectNode, selectedNodeId, level, isSearchActive }) => {
  // When searching, the search API returns a tree structure with embedded children.
  const embeddedChildren = node.children;

  const [fetchedChildren, setFetchedChildren] = useState<HierarchyNode[] | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const isSelected = node.internal_id === selectedNodeId;

  // Determine children to display based on mode
  const children = isSearchActive ? embeddedChildren : fetchedChildren;
  const hasChildren = isSearchActive ? (embeddedChildren && embeddedChildren.length > 0) : node.has_children;

  // Auto-expand if searching (restored functionality)
  useEffect(() => {
    if (isSearchActive && hasChildren) {
        setIsExpanded(true);
    } else if (!isSearchActive) {
        // Reset expansion when search is cleared (simplified logic)
        setIsExpanded(false);
    }
  }, [isSearchActive, hasChildren]);

  const toggleExpand = useCallback(async (event: React.MouseEvent) => {
    event.stopPropagation();
    if (!hasChildren) return;

    if (isSearchActive) {
        // Simple toggle for search results
        setIsExpanded(!isExpanded);
        return;
    }

    // Lazy loading logic for browsing
    if (!isExpanded && fetchedChildren === null) {
      setIsLoading(true);
      try {
        const data = await api.getHierarchy(actId, node.internal_id);
        setFetchedChildren(data);
        setIsExpanded(true);
      } catch (error) {
        console.error("Failed to fetch children:", error);
      } finally {
        setIsLoading(false);
      }
    } else {
      setIsExpanded(!isExpanded);
    }
  }, [isExpanded, fetchedChildren, node.internal_id, actId, hasChildren, isSearchActive]);

  const handleSelect = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelectNode(node.internal_id);
    // Auto-expand on select (Behavior from original NavItem)
    if(hasChildren && !isExpanded) {
        toggleExpand(e);
    }
  };

  // Styling restored from original NavItem
  const basePadding = (level - 1) * 1.25;

  return (
    <li>
        {/* Node visualization */}
        <div
          onClick={handleSelect}
          /* Styling restored from original NavItem (e.g., bg-blue-600) */
        className={`flex items-center justify-between p-2 my-1 rounded-md cursor-pointer transition-colors duration-150 ${
            isSelected ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'
          }`}
        style={{ paddingLeft: `${basePadding + 0.5}rem` }}
        >

        {/* Node Title */}
        <span className="flex-1 truncate text-sm font-medium">
        {node.title}
        </span>

        {/* Expand/Collapse Icon */}
        {hasChildren || isLoading ? (
            <button onClick={toggleExpand} className="ml-2 p-1 rounded-full hover:bg-gray-600 w-6 h-6 flex items-center justify-center" aria-label="Toggle expansion">
            {isLoading ? (
              <span className="text-xs">...</span>
            ) : (
              <ChevronRightIcon className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
            )}
            </button>
        ) : null}

        </div>

    {/* Children */}
    {isExpanded && children && children.length > 0 && (
        // Styling restored from original (border-l)
      <ul className="pl-2 border-l border-gray-600 ml-2">
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
  // Search state
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<HierarchyNode[] | null>(null);
  const [isSearchLoading, setIsSearchLoading] = useState(false);

  // Fetch initial hierarchy
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

  // Handle Search (Restored functionality, requires api.searchHierarchy)
  useEffect(() => {
    if (!searchTerm) {
        setSearchResults(null);
        // Clear search-related errors when search term is cleared
        if (error?.includes("Search failed")) setError(null);
        return;
    }

    const delayDebounceFn = setTimeout(() => {
        const performSearch = async () => {
            setIsSearchLoading(true);
            // Clear previous search errors
            if (error?.includes("Search failed")) setError(null);
            try {
                // Assumes api.searchHierarchy exists and returns a filtered tree
                const results = await api.searchHierarchy(actId, searchTerm);
                setSearchResults(results);
            } catch (err) {
                console.error("Failed to search:", err);
                setError("Search failed. Ensure the backend search endpoint (api/provisions/search_hierarchy) is implemented.");
                setSearchResults([]);
            } finally {
                setIsSearchLoading(false);
            }
        };
        performSearch();
    }, 300); // Debounce search input

    return () => clearTimeout(delayDebounceFn);
  }, [searchTerm, actId, error]);

  const isSearchActive = searchResults !== null;
  const nodesToDisplay = isSearchActive ? searchResults : topLevelNodes;

  if (isLoading) {
    return <div className="p-4 text-gray-400">Loading navigation...</div>;
  }

  // Layout restored from original
  return (
    <div className="flex flex-col h-full overflow-hidden">
        {/* Search Bar (Restored design) */}
        <div className="p-4 shrink-0">
            <div className="relative">
            <input
                type="text"
                placeholder="Search code..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-gray-900 border border-gray-600 rounded-md py-2 pl-10 pr-4 focus:ring-2 focus:ring-blue-500 focus:outline-none text-white"
            />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <SearchIcon className="w-5 h-5 text-gray-400" />
            </div>
            </div>
        </div>

        {/* Error display */}
        {error && (
            <div className="px-4 pb-2 text-red-400 text-sm">{error}</div>
        )}

        {/* Navigation List */}
        <nav className="flex-grow overflow-y-auto px-4 pb-4">
            {isSearchLoading && <div className="p-2 text-gray-400">Searching...</div>}

            {!isSearchLoading && !error && nodesToDisplay.length === 0 && (
                <div className="p-2 text-gray-400">
                    {isSearchActive ? "No results found." : "Navigation structure is empty."}
                </div>
            )}

            {!isSearchLoading && (
            <ul>
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