import React, {useCallback, useEffect, useState} from 'react';
import {HierarchyNode} from '../types';
import {api} from '../utils/api';
import {ChevronRightIcon, ClipboardIcon, SearchIcon} from './Icons';
import {useToast} from './ToastProvider';

type ChildrenCache = Record<string, HierarchyNode[]>;
type LoadingChildrenState = Record<string, boolean>;

interface NavNodeProps {
    node: HierarchyNode;
    onSelectNode: (nodeId: string) => void;
    selectedNodeId: string | null;
    level: number;
    isSearchActive: boolean;
    onToggleNode: (node: HierarchyNode) => void;
    resolveChildren: (node: HierarchyNode) => HierarchyNode[];
    getIsExpanded: (node: HierarchyNode) => boolean;
    getIsLoadingChildren: (node: HierarchyNode) => boolean;
    onCopyMarkdown: (node: HierarchyNode) => Promise<string>;
}

export const NavNode: React.FC<NavNodeProps> = ({
                                                    node,
                                                    onSelectNode,
                                                    selectedNodeId,
                                                    level,
                                                    isSearchActive,
                                                    onToggleNode,
                                                    resolveChildren,
                                                    getIsExpanded,
                                                    getIsLoadingChildren,
                                                    onCopyMarkdown,
                                                }) => {
    const [isActionHovered, setIsActionHovered] = useState(false);
    const [isActionFocused, setIsActionFocused] = useState(false);
    const [isCopying, setIsCopying] = useState(false);
    const {showToast} = useToast();

    const isSelected = node.internal_id === selectedNodeId;
    const isExpanded = getIsExpanded(node);
    const isLoadingChildren = getIsLoadingChildren(node);

    const embeddedChildren = Array.isArray(node.children) ? node.children : [];
    const hasChildren = isSearchActive ? embeddedChildren.length > 0 : node.has_children;
    const children = resolveChildren(node);

    const handleSelect = (event: React.MouseEvent<HTMLDivElement>) => {
        event.stopPropagation();
        onSelectNode(node.internal_id);
        if (hasChildren && !isExpanded) {
            onToggleNode(node);
        }
    };

    const handleToggle = useCallback(
        (event: React.MouseEvent) => {
            event.stopPropagation();
            if (!hasChildren) {
                return;
            }
            onToggleNode(node);
        },
        [hasChildren, node, onToggleNode],
    );

    const handleActionsFocus = useCallback(() => {
        setIsActionFocused(true);
    }, []);

    const handleActionsBlur = useCallback((event: React.FocusEvent<HTMLDivElement>) => {
        const nextFocus = event.relatedTarget as HTMLElement | null;
        if (!nextFocus || !event.currentTarget.contains(nextFocus)) {
            setIsActionFocused(false);
        }
    }, []);

    const handleCopyMarkdown = useCallback(async () => {
        if (isCopying) {
            return;
        }

        setIsCopying(true);
        try {
            const markdown = await onCopyMarkdown(node);
            if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
                throw new Error('Clipboard API is unavailable');
            }
            await navigator.clipboard.writeText(markdown);
            showToast({
                variant: 'success',
                title: 'Markdown copied',
                description: node.title ?? node.ref_id ?? node.internal_id,
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to copy markdown.';
            console.error('Failed to copy provision markdown:', error);
            showToast({
                variant: 'error',
                title: 'Failed to copy markdown',
                description: message,
            });
        } finally {
            setIsCopying(false);
        }
    }, [isCopying, node, onCopyMarkdown, showToast]);

    const indentStep = 12;
    const indentPadding = level * indentStep;
    const showExpandControl = hasChildren || isLoadingChildren;
    const isPending = isCopying;
    const actionGroupVisible = isActionHovered || isActionFocused || isPending;

    return (
        <li>
            <div className="relative">
                <div
                    onClick={handleSelect}
                    onMouseEnter={() => setIsActionHovered(true)}
                    onMouseLeave={() => setIsActionHovered(false)}
                    className={`flex items-center gap-3 p-2 my-1 rounded-md cursor-pointer transition-colors duration-150 ${
                        isSelected ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'
                    }`}
                    style={{paddingLeft: indentPadding}}
                >
                    <div className="w-6 flex items-center justify-center">
                        {showExpandControl ? (
                            <button
                                onClick={handleToggle}
                                className="p-1 rounded-full hover:bg-gray-600 w-6 h-6 flex items-center justify-center"
                                aria-label="Toggle expansion"
                            >
                                {isLoadingChildren ? (
                                    <span className="text-xs">...</span>
                                ) : (
                                    <ChevronRightIcon
                                        className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                    />
                                )}
                            </button>
                        ) : (
                            <span className="inline-block w-6 h-6" aria-hidden="true"/>
                        )}
                    </div>

                    <div className="flex flex-col min-w-0">
                        <span className="text-base font-medium whitespace-normal break-words leading-snug">{node.title}</span>
                    </div>

                    <div
                        onFocus={handleActionsFocus}
                        onBlur={handleActionsBlur}
                        className={`ml-auto flex items-center gap-2 transition-opacity duration-150 ${
                            actionGroupVisible ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
                        }`}
                    >
                        <button
                            type="button"
                            onClick={event => {
                                event.stopPropagation();
                                void handleCopyMarkdown();
                            }}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-400 focus-visible:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
                            aria-label={`Copy markdown for ${node.title} to clipboard`}
                            disabled={isPending}
                        >
                            {isPending ? (
                                <span
                                    className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"
                                    aria-hidden="true"
                                />
                            ) : (
                                <>
                                    <ClipboardIcon className="w-4 h-4" aria-hidden="true"/>
                                    <span className="sr-only">Copy to clipboard</span>
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {isExpanded && children.length > 0 && (
                <ul className="mt-2 space-y-1 pl-0 list-none">
                    {children.map(child => (
                        <NavNode
                            key={child.internal_id}
                            node={child}
                            onSelectNode={onSelectNode}
                            selectedNodeId={selectedNodeId}
                            level={level + 1}
                            isSearchActive={isSearchActive}
                            onToggleNode={onToggleNode}
                            resolveChildren={resolveChildren}
                            getIsExpanded={getIsExpanded}
                            getIsLoadingChildren={getIsLoadingChildren}
                            onCopyMarkdown={onCopyMarkdown}
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
    const [childrenCache, setChildrenCache] = useState<ChildrenCache>({});
    const [loadingChildren, setLoadingChildren] = useState<LoadingChildrenState>({});
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
    const [collapsedSearchNodes, setCollapsedSearchNodes] = useState<Set<string>>(new Set());

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
        setExpandedNodes(new Set());
        setChildrenCache({});
        setLoadingChildren({});
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

    useEffect(() => {
        if (!isSearchActive) {
            setCollapsedSearchNodes(new Set());
        }
    }, [isSearchActive]);

    const nodesToDisplay = isSearchActive ? searchResults ?? [] : topLevelNodes;

    const computeIsExpanded = useCallback(
        (target: HierarchyNode): boolean => {
            if (isSearchActive) {
                const hasEmbeddedChildren = Array.isArray(target.children) && target.children.length > 0;
                if (!hasEmbeddedChildren) {
                    return false;
                }
                return !collapsedSearchNodes.has(target.internal_id);
            }
            if (!target.has_children) {
                return false;
            }
            return expandedNodes.has(target.internal_id);
        },
        [collapsedSearchNodes, expandedNodes, isSearchActive],
    );

    const handleToggleNode = useCallback(
        async (node: HierarchyNode) => {
            const hasChildren = isSearchActive ? Array.isArray(node.children) && node.children.length > 0 : node.has_children;
            if (!hasChildren) {
                return;
            }

            if (isSearchActive) {
                setCollapsedSearchNodes(prev => {
                    const next = new Set(prev);
                    if (next.has(node.internal_id)) {
                        next.delete(node.internal_id);
                    } else {
                        next.add(node.internal_id);
                    }
                    return next;
                });
                return;
            }

            const currentlyExpanded = expandedNodes.has(node.internal_id);
            setExpandedNodes(prev => {
                const next = new Set(prev);
                if (currentlyExpanded) {
                    next.delete(node.internal_id);
                } else {
                    next.add(node.internal_id);
                }
                return next;
            });

            if (!currentlyExpanded && !childrenCache[node.internal_id] && !loadingChildren[node.internal_id]) {
                setLoadingChildren(prev => ({...prev, [node.internal_id]: true}));
                try {
                    const fetchedChildren = await api.getHierarchy(actId, node.internal_id);
                    setChildrenCache(prev => ({...prev, [node.internal_id]: fetchedChildren}));
                } catch (error) {
                    console.error('Failed to fetch children:', error);
                    setChildrenCache(prev => ({...prev, [node.internal_id]: []}));
                } finally {
                    setLoadingChildren(prev => ({...prev, [node.internal_id]: false}));
                }
            }
        },
        [actId, childrenCache, expandedNodes, isSearchActive, loadingChildren],
    );

    const handleCopyVisibleMarkdown = useCallback(
        async (node: HierarchyNode) => {
            const context: VisibilityContext = {
                isSearchActive,
                expandedNavNodes: expandedNodes,
                collapsedSearchNodes,
                childrenCache,
            };
            const descendantIds = collectVisibleDescendantIds(node, context);
            return api.getVisibleSubtreeMarkdown(node.internal_id, descendantIds);
        },
        [childrenCache, collapsedSearchNodes, expandedNodes, isSearchActive],
    );

    const resolveChildren = useCallback(
        (target: HierarchyNode): HierarchyNode[] => {
            if (isSearchActive) {
                return Array.isArray(target.children) ? target.children : [];
            }
            return childrenCache[target.internal_id] ?? [];
        },
        [childrenCache, isSearchActive],
    );

    const getIsLoadingChildren = useCallback(
        (target: HierarchyNode): boolean => {
            if (isSearchActive) {
                return false;
            }
            return Boolean(loadingChildren[target.internal_id]);
        },
        [isSearchActive, loadingChildren],
    );

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

            <nav className="flex-grow overflow-y-auto px-4 pb-4 scrollbar-stable">
                {isSearchLoading && <div className="p-2 text-gray-400">Searching...</div>}

                {!isSearchLoading && nodesToDisplay.length > 0 && (
                    <ul className="space-y-1 list-none pl-0">
                        {nodesToDisplay.map(node => (
                            <NavNode
                                key={node.internal_id}
                                node={node}
                                onSelectNode={onSelectNode}
                                selectedNodeId={selectedNodeId}
                                level={0}
                                isSearchActive={isSearchActive}
                                onToggleNode={handleToggleNode}
                                resolveChildren={resolveChildren}
                                getIsExpanded={computeIsExpanded}
                                getIsLoadingChildren={getIsLoadingChildren}
                                onCopyMarkdown={handleCopyVisibleMarkdown}
                            />
                        ))}
                    </ul>
                )}
            </nav>
        </div>
    );
};

interface VisibilityContext {
    isSearchActive: boolean;
    expandedNavNodes: Set<string>;
    collapsedSearchNodes: Set<string>;
    childrenCache: ChildrenCache;
}

const getChildrenForContext = (node: HierarchyNode, context: VisibilityContext): HierarchyNode[] => {
    if (context.isSearchActive) {
        return Array.isArray(node.children) ? node.children : [];
    }
    return context.childrenCache[node.internal_id] ?? [];
};

const isNodeExpandedInContext = (node: HierarchyNode, context: VisibilityContext): boolean => {
    const hasChildren = context.isSearchActive
        ? Array.isArray(node.children) && node.children.length > 0
        : node.has_children;
    if (!hasChildren) {
        return false;
    }
    if (context.isSearchActive) {
        return !context.collapsedSearchNodes.has(node.internal_id);
    }
    return context.expandedNavNodes.has(node.internal_id);
};

const collectVisibleDescendantIds = (root: HierarchyNode, context: VisibilityContext): string[] => {
    if (!isNodeExpandedInContext(root, context)) {
        return [];
    }
    const result: string[] = [];
    const seen = new Set<string>();

    const walk = (current: HierarchyNode) => {
        const children = getChildrenForContext(current, context);
        for (const child of children) {
            if (seen.has(child.internal_id)) {
                continue;
            }
            seen.add(child.internal_id);
            result.push(child.internal_id);
            if (isNodeExpandedInContext(child, context)) {
                walk(child);
            }
        }
    };

    walk(root);
    return result;
};

export default SideNav;
