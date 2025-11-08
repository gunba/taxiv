import React, {useCallback, useEffect, useRef, useState} from 'react';
import {HierarchyNode} from '../types';
import {api} from '../utils/api';
import {ChevronRightIcon, ClipboardIcon, SearchIcon} from './Icons';
import {exportMarkdownToClipboard} from '../utils/exportMarkdown';

type ExportAction = 'with-descendants';

interface ExportState {
    status: 'idle' | 'pending' | 'success' | 'error';
    action: ExportAction | null;
    message: string | null;
}

interface NavNodeProps {
    node: HierarchyNode;
    actId: string;
    onSelectNode: (nodeId: string) => void;
    selectedNodeId: string | null;
    level: number;
    isSearchActive: boolean;
}

export const NavNode: React.FC<NavNodeProps> = ({
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
    const [isActionHovered, setIsActionHovered] = useState(false);
    const [isActionFocused, setIsActionFocused] = useState(false);
    const [exportState, setExportState] = useState<ExportState>({status: 'idle', action: null, message: null});

    const abortControllerRef = useRef<AbortController | null>(null);
    const feedbackTimeoutRef = useRef<number | null>(null);
    const isMountedRef = useRef(true);

    const safeSetExportState = useCallback((update: React.SetStateAction<ExportState>) => {
        if (!isMountedRef.current) {
            return;
        }
        setExportState(update);
    }, []);

    const clearFeedbackTimeout = useCallback(() => {
        if (feedbackTimeoutRef.current !== null) {
            window.clearTimeout(feedbackTimeoutRef.current);
            feedbackTimeoutRef.current = null;
        }
    }, []);

    const resetExportState = useCallback(() => {
        safeSetExportState(prev => (prev.status === 'pending' ? prev : {status: 'idle', action: null, message: null}));
    }, [safeSetExportState]);

    useEffect(() => {
        return () => {
            isMountedRef.current = false;
            abortControllerRef.current?.abort();
            clearFeedbackTimeout();
        };
    }, [clearFeedbackTimeout]);

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

    const handleActionsFocus = useCallback(() => {
        setIsActionFocused(true);
    }, []);

    const handleActionsBlur = useCallback((event: React.FocusEvent<HTMLDivElement>) => {
        const nextFocus = event.relatedTarget as HTMLElement | null;
        if (!nextFocus || !event.currentTarget.contains(nextFocus)) {
            setIsActionFocused(false);
        }
    }, []);

    const handleExport = useCallback(
        async () => {
            if (exportState.status === 'pending') {
                return;
            }

            const action: ExportAction = 'with-descendants';
            abortControllerRef.current?.abort();
            const controller = new AbortController();
            abortControllerRef.current = controller;
            clearFeedbackTimeout();
            safeSetExportState({status: 'pending', action, message: null});
            let shouldScheduleReset = true;

            try {
                const result = await exportMarkdownToClipboard({
                    internalId: node.internal_id,
                    includeDescendants: true,
                    signal: controller.signal,
                });

                if (!isMountedRef.current) {
                    return;
                }

                if (result.status === 'success' || result.status === 'clipboard-fallback') {
                    const message =
                        result.status === 'clipboard-fallback'
                            ? 'Copied markdown. Clipboard permissions are restricted; paste manually if needed.'
                            : 'Markdown copied to clipboard.';
                    safeSetExportState({status: 'success', action, message});
                } else if (result.status === 'cancelled') {
                    shouldScheduleReset = false;
                    resetExportState();
                    return;
                } else {
                    const message = result.error?.message ?? 'Failed to export markdown.';
                    safeSetExportState({status: 'error', action, message});
                }
            } catch (error) {
                if (!isMountedRef.current) {
                    return;
                }

                const message = error instanceof Error ? error.message : 'Failed to export markdown.';
                safeSetExportState({status: 'error', action, message});
            } finally {
                if (isMountedRef.current) {
                    abortControllerRef.current = null;
                    if (shouldScheduleReset) {
                        feedbackTimeoutRef.current = window.setTimeout(() => {
                            resetExportState();
                            feedbackTimeoutRef.current = null;
                        }, 2000);
                    }
                }
            }
        },
        [
            clearFeedbackTimeout,
            exportState.status,
            node.internal_id,
            resetExportState,
            safeSetExportState,
        ],
    );

    const indentStep = 12;
    const indentPadding = level * indentStep;
    const guidePosition = indentPadding - indentStep / 2;
    const showExpandControl = hasChildren || isLoading;
    const isPending = exportState.status === 'pending';
    const actionGroupVisible =
        isActionHovered ||
        isActionFocused ||
        exportState.status === 'pending' ||
        exportState.status === 'success' ||
        exportState.status === 'error';

    return (
        <li>
            <div className="relative">
                {level > 0 && (
                    <span
                        aria-hidden="true"
                        className={`absolute top-2 bottom-2 w-px rounded-full ${
                            isSelected ? 'bg-blue-300/70' : 'bg-gray-700/70'
                        }`}
                        style={{left: guidePosition}}
                    />
                )}
                <div
                    onClick={handleSelect}
                    onMouseEnter={() => setIsActionHovered(true)}
                    onMouseLeave={() => setIsActionHovered(false)}
                    className={`flex items-start gap-3 p-2 my-1 rounded-md cursor-pointer transition-colors duration-150 ${
                        isSelected ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'
                    }`}
                    style={{paddingLeft: indentPadding}}
                >
                    <div className="w-6 flex justify-center self-start">
                        {showExpandControl ? (
                            <button
                                onClick={toggleExpand}
                                className="p-1 rounded-full hover:bg-gray-600 w-6 h-6 flex items-center justify-center"
                                aria-label="Toggle expansion"
                            >
                                {isLoading ? (
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
                        <span className="text-sm font-medium whitespace-normal break-words leading-snug">{node.title}</span>
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
                                void handleExport();
                            }}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-400 focus-visible:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
                            aria-label={`Copy markdown for ${node.title} to clipboard`}
                            disabled={isPending}
                        >
                            {isPending && exportState.action === 'with-descendants' ? (
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

            {exportState.message && (
                <div
                    className="mt-1 text-xs text-gray-400"
                    style={{paddingLeft: indentPadding + 48}}
                    role="status"
                    aria-live="polite"
                >
                    {exportState.message}
                </div>
            )}

            {isExpanded && children && children.length > 0 && (
                <ul className="mt-2 space-y-1 pl-0 list-none">
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

            <nav className="flex-grow overflow-y-auto px-4 pb-4 scrollbar-stable">
                {isSearchLoading && <div className="p-2 text-gray-400">Searching...</div>}

                {!isSearchLoading && nodesToDisplay.length > 0 && (
                    <ul className="space-y-1 list-none pl-0">
                        {nodesToDisplay.map(node => (
                            <NavNode
                                key={node.internal_id}
                                node={node}
                                actId={actId}
                                onSelectNode={onSelectNode}
                                selectedNodeId={selectedNodeId}
                                level={0}
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
