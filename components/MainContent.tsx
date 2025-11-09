// components/MainContent.tsx
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {TaxDataObject} from '../types';
import InteractiveContent from './InteractiveContent';
import {ChevronRightIcon, ClipboardIcon} from './Icons';
import {api} from '../utils/api';
import {formatNodeHeading} from '../utils/nodeFormatting';
import {sortProvisions} from '../utils/provisionSort';
import {copyToClipboard} from '../utils/clipboard';

interface MainContentProps {
    node: TaxDataObject | null;
    breadcrumbs: { internal_id: string; title: string }[];
    isLoading: boolean;
    onTermClick: (definitionInternalId: string, termText: string) => void;
    onReferenceByRefIdClick: (refId: string) => void;
    onSelectNode: (nodeId: string) => void;
}

const MainContent: React.FC<MainContentProps> = ({
                                                     node,
                                                     breadcrumbs,
                                                     isLoading,
                                                     onTermClick,
                                                     onReferenceByRefIdClick,
                                                     onSelectNode,
                                                 }) => {
    const [renderedNodes, setRenderedNodes] = useState<TaxDataObject[]>([]);
    const pendingIdsRef = useRef<string[]>([]);
    const [pendingCount, setPendingCount] = useState(0);
    const [isLoadingChildren, setIsLoadingChildren] = useState(false);
    const [childLoadError, setChildLoadError] = useState<string | null>(null);
    const [isSentinelVisible, setIsSentinelVisible] = useState(false);
    const sentinelRef = useRef<HTMLDivElement | null>(null);
    const rootIdRef = useRef<string | null>(null);
    const scrollContainerRef = useRef<HTMLElement | null>(null);

    const topProvision = renderedNodes[0] ?? null;

    // Scroll to top when the node changes
    useEffect(() => {
        const mainElement = document.querySelector('main') as HTMLElement | null;
        scrollContainerRef.current = mainElement;
        if (mainElement) {
            mainElement.scrollTo({top: 0});
        }
    }, [node]);

    // Reset rendered nodes whenever the selected node changes
    useEffect(() => {
        rootIdRef.current = node?.internal_id ?? null;
        setChildLoadError(null);
        setIsLoadingChildren(false);
        pendingIdsRef.current = [];
        setPendingCount(0);

        if (!node) {
            setRenderedNodes([]);
            return;
        }

        setRenderedNodes(sortProvisions([node]));

        let isCancelled = false;

        const prepareChildStack = async () => {
            try {
                const children = await api.getHierarchy(node.act_id, node.internal_id);
                if (isCancelled || rootIdRef.current !== node.internal_id) {
                    return;
                }
                const childIds = children.map(child => child.internal_id).reverse();
                pendingIdsRef.current = childIds;
                setPendingCount(childIds.length);
            } catch (error) {
                if (isCancelled || rootIdRef.current !== node.internal_id) {
                    return;
                }
                console.error('Error loading child hierarchy:', error);
                setChildLoadError('Failed to load child provisions.');
            }
        };

        prepareChildStack();

        return () => {
            isCancelled = true;
        };
    }, [node]);

    // Observe the sentinel for lazy loading
    useEffect(() => {
        const sentinel = sentinelRef.current;
        const scrollContainer =
            scrollContainerRef.current ?? (document.querySelector('main') as HTMLElement | null);

        if (!sentinel || !scrollContainer) {
            return;
        }

        if (!scrollContainerRef.current) {
            scrollContainerRef.current = scrollContainer;
        }

        const observer = new IntersectionObserver(
            (entries) => {
                const [entry] = entries;
                if (entry) {
                    setIsSentinelVisible(entry.isIntersecting);
                }
            },
            {
                root: scrollContainer,
                rootMargin: '400px 0px',
            }
        );

        observer.observe(sentinel);

        return () => {
            observer.disconnect();
        };
    }, [node]);

    const handleCopyToClipboard = useCallback(() => {
        if (!topProvision || !topProvision.content_md) return;
        const {markdownHeading} = formatNodeHeading(topProvision);
        const heading = markdownHeading || topProvision.title || topProvision.ref_id;
        const markdown = `# ${heading}\n\n${topProvision.content_md}\n\n`;
        copyToClipboard(markdown).catch(err => console.error('Failed to copy text: ', err));
    }, [topProvision]);

    const loadNextProvision = useCallback(async () => {
        if (isLoadingChildren) {
            return;
        }

        const queue = pendingIdsRef.current;
        const nextId = queue.pop() ?? null;
        setPendingCount(queue.length);

        if (!nextId) {
            return;
        }

        setIsLoadingChildren(true);
        const activeRootId = rootIdRef.current;

        try {
            const detail = await api.getProvisionDetail(nextId);
            if (rootIdRef.current !== activeRootId) {
                return;
            }

            setRenderedNodes(prev => {
                const withoutDuplicate = prev.filter(entry => entry.internal_id !== detail.internal_id);
                withoutDuplicate.push(detail);
                return sortProvisions(withoutDuplicate);
            });

            try {
                const children = await api.getHierarchy(detail.act_id, detail.internal_id);
                if (rootIdRef.current !== activeRootId) {
                    return;
                }
                if (children.length > 0) {
                    const childIds = children.map(child => child.internal_id).reverse();
                    queue.push(...childIds);
                    setPendingCount(queue.length);
                }
            } catch (error) {
                if (rootIdRef.current === activeRootId) {
                    console.error('Error loading nested child hierarchy:', error);
                    setChildLoadError('Failed to load some descendant provisions.');
                }
            }

            if (rootIdRef.current === activeRootId) {
                setChildLoadError(null);
            }
        } catch (error) {
            if (rootIdRef.current === activeRootId) {
                console.error('Error loading child provision detail:', error);
                setChildLoadError(`Failed to load additional provisions. ${(error as Error).message}`);
            }
        } finally {
            if (rootIdRef.current === activeRootId) {
                setIsLoadingChildren(false);
            }
        }
    }, [isLoadingChildren]);

    // Trigger loading whenever the sentinel is visible and items remain on the stack
    useEffect(() => {
        if (isSentinelVisible && pendingCount > 0 && !isLoadingChildren) {
            loadNextProvision();
        }
    }, [isSentinelVisible, pendingCount, isLoadingChildren, loadNextProvision]);

    // Ensure the first child loads immediately after a node is selected, even if the
    // sentinel hasn't yet become visible (for example when the initial content is
    // shorter than the scroll container).
    useEffect(() => {
        if (renderedNodes.length === 1 && pendingCount > 0 && !isLoadingChildren) {
            loadNextProvision();
        }
    }, [renderedNodes.length, pendingCount, isLoadingChildren, loadNextProvision]);

    if (isLoading) {
        return <div className="p-8 text-center text-gray-400">Loading provision details...</div>;
    }

    if (!topProvision) {
        return (
            <div className="p-8 text-center text-gray-400">
                <h2 className="text-2xl font-semibold">Welcome to the Tax Code Explorer</h2>
                <p className="mt-2">Select an item from the navigation panel on the left to view its content here.</p>
            </div>
        );
    }

    return (
        <div className="p-6 md:p-8">
            {renderedNodes.map((provision, index) => (
                <article
                    key={provision.internal_id}
                    className={index === 0 ? '' : 'pt-6 mt-6 border-t border-gray-800'}
                >
                    {index === 0 ? (
                        <>
                            <div className="flex items-center justify-between pb-4 mb-4 border-b border-gray-700">
                                <div className="flex items-center text-sm text-gray-400 overflow-hidden">
                                    {breadcrumbs.length > 0 ? breadcrumbs.map((crumb, crumbIndex) => (
                                        <React.Fragment key={crumb.internal_id}>
                                            <button
                                                type="button"
                                                onClick={() => onSelectNode(crumb.internal_id)}
                                                className="truncate hover:underline whitespace-nowrap"
                                            >
                                                {crumb.title}
                                            </button>
                                            {crumbIndex < breadcrumbs.length - 1 &&
                                                <ChevronRightIcon className="w-4 h-4 mx-1 shrink-0"/>}
                                        </React.Fragment>
                                    )) : (
                                        <span
                                            className="text-gray-500 text-xs">(Loading breadcrumbs or API unavailable)</span>
                                    )}
                                </div>
                                <button
                                    type="button"
                            onClick={handleCopyToClipboard}
                                    className="p-2 rounded-md hover:bg-gray-700 text-gray-400 hover:text-white transition-colors shrink-0 ml-4"
                                    aria-label="Copy content to clipboard"
                                >
                                    <ClipboardIcon className="w-5 h-5"/>
                                </button>
                            </div>
                            <div className="prose prose-invert prose-sm sm:prose-base max-w-none">
                                <p className="text-sm font-semibold text-blue-400">{provision.type}</p>
                                <h1 className="text-2xl md:text-3xl font-bold text-gray-100 mt-1">{provision.title}</h1>
                            </div>
                        </>
                    ) : (
                        <header className="mb-4">
                            <button
                                type="button"
                                onClick={() => onSelectNode(provision.internal_id)}
                                className="text-left group"
                            >
                                <p className="text-xs font-semibold text-blue-400 uppercase tracking-wide">{provision.type}</p>
                                <h2 className="text-xl md:text-2xl font-bold text-gray-100 mt-1 group-hover:text-blue-200 group-hover:underline">
                                    {provision.title}
                                </h2>
                            </button>
                        </header>
                    )}

                    <div className="mt-4 text-gray-300 leading-7 prose prose-invert max-w-none">
                        <InteractiveContent
                            key={provision.internal_id}
                            node={provision}
                            onTermClick={onTermClick}
                            onReferenceByRefIdClick={onReferenceByRefIdClick}
                        />
                    </div>
                </article>
            ))}

            <div ref={sentinelRef} className="h-1"/>

            {isLoadingChildren && (
                <div className="py-4 text-center text-gray-400 text-sm">Loading additional provisions...</div>
            )}

            {childLoadError && (
                <div className="py-4 text-center text-red-400 text-sm">{childLoadError}</div>
            )}
        </div>
    );
};

export default MainContent;
