import React, {useCallback, useEffect, useState} from 'react';
import {HierarchyNode} from '../types';
import {api} from '../utils/api';
import {ChevronRightIcon, SearchIcon} from './Icons';

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
    const embeddedChildren = Array.isArray(node.children) ? node.children : [];

    const [fetchedChildren, setFetchedChildren] = useState<HierarchyNode[] | null>(null);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const isSelected = node.internal_id === selectedNodeId;

    const children = isSearchActive ? embeddedChildren : fetchedChildren;
    const hasChildren = isSearchActive ? embeddedChildren.length > 0 : node.has_children;

    useEffect(() => {
        if (isSearchActive && hasChildren) {
            setIsExpanded(true);
        } else if (!isSearchActive) {
            setIsExpanded(false);
        }
    }, [isSearchActive, hasChildren]);

    const toggleExpand = useCallback(
        async (event: React.MouseEvent) => {
            event.stopPropagation();
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
        },
        [actId, fetchedChildren, hasChildren, isExpanded, isSearchActive, node.internal_id],
    );

    const handleSelect = (event: React.MouseEvent<HTMLDivElement>) => {
        event.stopPropagation();
        onSelectNode(node.internal_id);
        if (hasChildren && !isExpanded) {
            toggleExpand(event);
        }
    };

    const basePadding = (level - 1) * 1.25;

    return (
        <li>
            <div
                onClick={handleSelect}
                className={`flex items-center justify-between p-2 my-1 rounded-md cursor-pointer transition-colors duration-150 ${
                    isSelected ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'
                }`}
                style={{paddingLeft: `${basePadding + 0.5}rem`}}
            >
                <span className="flex-1 truncate text-sm font-medium">{node.title}</span>
                {(hasChildren || isLoading) && (
                    <button
                        onClick={toggleExpand}
                        className="ml-2 p-1 rounded-full hover:bg-gray-600 w-6 h-6 flex items-center justify-center"
                        aria-label="Toggle expansion"
                    >
                        {isLoading ? (
                            <span className="text-xs">...</span>
                        ) : (
                            <ChevronRightIcon
                                className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}/>
                        )}
                    </button>
                )}
            </div>

            {isExpanded && children && children.length > 0 && (
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

interface SideNavProps {
    actId: string;
    onSelectNode: (nodeId: string) => void;
    selectedNodeId: string | null;
}

const SideNav: React.FC<SideNavProps> = ({actId, onSelectNode, selectedNodeId}) => {
    const [topLevelNodes, setTopLevelNodes] = useState<HierarchyNode[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [searchResults, setSearchResults] = useState<HierarchyNode[] | null>(null);
    const [searchError, setSearchError] = useState<string | null>(null);
    const [isSearchLoading, setIsSearchLoading] = useState(false);

    useEffect(() => {
        let isMounted = true;
        const fetchInitialHierarchy = async () => {
            setIsLoading(true);
            setLoadError(null);
            try {
                const nodes = await api.getHierarchy(actId);
                if (isMounted) {
                    setTopLevelNodes(nodes);
                }
            } catch (err) {
                console.error('Failed to load initial hierarchy:', err);
                if (isMounted) {
                    setLoadError('Could not load navigation structure.');
                }
            } finally {
                if (isMounted) {
                    setIsLoading(false);
                }
            }
        };

        fetchInitialHierarchy();

        return () => {
            isMounted = false;
        };
    }, [actId]);

    useEffect(() => {
        const trimmedTerm = searchTerm.trim();
        if (!trimmedTerm) {
            setSearchResults(null);
            setSearchError(null);
            setIsSearchLoading(false);
            return;
        }

        let isCancelled = false;
        setIsSearchLoading(true);

        const timeoutId = window.setTimeout(async () => {
            try {
                const results = await api.searchHierarchy(actId, trimmedTerm);
                if (!isCancelled) {
                    setSearchResults(results);
                    setSearchError(null);
                }
            } catch (err) {
                console.error('Failed to search hierarchy:', err);
                if (!isCancelled) {
                    setSearchResults([]);
                    setSearchError('Search failed. Ensure the backend search endpoint is available.');
                }
            } finally {
                if (!isCancelled) {
                    setIsSearchLoading(false);
                }
            }
        }, 300);

        return () => {
            isCancelled = true;
            window.clearTimeout(timeoutId);
        };
    }, [actId, searchTerm]);

    const isSearchActive = searchResults !== null;
    const nodesToDisplay = isSearchActive ? searchResults ?? [] : topLevelNodes;

    if (isLoading) {
        return <div className="p-4 text-gray-400">Loading navigation...</div>;
    }

    if (loadError) {
        return <div className="p-4 text-red-400">{loadError}</div>;
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="p-4 shrink-0">
                <div className="relative">
                    <input
                        type="text"
                        placeholder="Search code..."
                        value={searchTerm}
                        onChange={event => setSearchTerm(event.target.value)}
                        className="w-full bg-gray-900 border border-gray-600 rounded-md py-2 pl-10 pr-4 focus:ring-2 focus:ring-blue-500 focus:outline-none text-white"
                    />
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <SearchIcon className="w-5 h-5 text-gray-400"/>
                    </div>
                </div>
            </div>

            {(searchError || (isSearchActive && nodesToDisplay.length === 0 && !isSearchLoading)) && (
                <div className="px-4 text-sm text-red-400">
                    {searchError ?? 'No results found.'}
                </div>
            )}

            <nav className="flex-grow overflow-y-auto px-4 pb-4">
                {isSearchLoading && <div className="p-2 text-gray-400">Searching...</div>}

                {!isSearchLoading && nodesToDisplay.length > 0 && (
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
