// App.tsx
import React, {useCallback, useEffect, useState} from 'react';
import type {ActInfo, DetailViewContent, TaxDataObject} from './types';
import SideNav from './components/SideNav';
import MainContent from './components/MainContent';
import DetailView from './components/DetailView';
import {SearchIcon} from './components/Icons';
import {api, type UnifiedSearchItem} from './utils/api';
import SemanticSearchModal from './components/SemanticSearchModal';
import taxivLogo from './assets/taxiv-logo.png';
import {ToastProvider} from './components/ToastProvider';
import ActSelector from './components/ActSelector';

const SEMANTIC_SEARCH_STORAGE_KEY = 'taxiv:semantic_search';
const ACT_STORAGE_KEY = 'taxiv:selected_act';

type SemanticSearchState = {
	query: string;
	results: UnifiedSearchItem[];
};

const loadSemanticSearchState = (): SemanticSearchState => {
	if (typeof window === 'undefined') {
		return {query: '', results: []};
	}
	try {
		const raw = window.localStorage.getItem(SEMANTIC_SEARCH_STORAGE_KEY);
		if (!raw) {
			return {query: '', results: []};
		}
		const parsed = JSON.parse(raw);
		if (typeof parsed.query === 'string' && Array.isArray(parsed.results)) {
			const normalizedResults = (parsed.results as UnifiedSearchItem[]).map(result => ({
				...result,
				content_snippet: typeof result.content_snippet === 'string' && result.content_snippet.trim().length > 0
					? result.content_snippet
					: 'No content',
			}));
			return {query: parsed.query, results: normalizedResults};
		}
		return {query: '', results: []};
	} catch (err) {
		console.warn('Failed to load semantic search state:', err);
		return {query: '', results: []};
	}
};

const App: React.FC = () => {
    const [acts, setActs] = useState<ActInfo[]>([]);
    const [selectedActId, setSelectedActId] = useState<string | null>(null);
    const [isLoadingActs, setIsLoadingActs] = useState<boolean>(true);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [mainContentData, setMainContentData] = useState<TaxDataObject | null>(null);
    // State for breadcrumbs (restored functionality)
    const [breadcrumbs, setBreadcrumbs] = useState<{ internal_id: string; title: string }[]>([]);
    const [detailViewContent, setDetailViewContent] = useState<DetailViewContent | null>(null);
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [isSemanticSearchOpen, setSemanticSearchOpen] = useState(false);
    const [semanticSearchState, setSemanticSearchState] = useState<SemanticSearchState>(() => loadSemanticSearchState());

    useEffect(() => {
        const loadActs = async () => {
            try {
                const data = await api.getActs();
                setActs(data);
                let nextAct: string | null = null;
                if (typeof window !== 'undefined') {
                    const stored = window.localStorage.getItem(ACT_STORAGE_KEY);
                    if (stored && data.some(act => act.id === stored)) {
                        nextAct = stored;
                    }
                }
                if (!nextAct) {
                    const defaultAct = data.find(act => act.is_default) ?? data[0];
                    nextAct = defaultAct?.id ?? null;
                }
                setSelectedActId(nextAct);
            } catch (err) {
                console.error('Failed to load act metadata:', err);
                setError('Failed to load available acts. Ensure the backend is reachable.');
            } finally {
                setIsLoadingActs(false);
            }
        };
        loadActs();
    }, []);

    useEffect(() => {
        if (selectedActId && typeof window !== 'undefined') {
            window.localStorage.setItem(ACT_STORAGE_KEY, selectedActId);
        }
    }, [selectedActId]);

    useEffect(() => {
        setSemanticSearchState({query: '', results: []});
    }, [selectedActId]);

    // Function to fetch details for the main view
    const fetchMainContent = useCallback(async (internalId: string) => {
        setIsLoading(true);
        setError(null);
        setSelectedNodeId(internalId); // Update ID immediately for responsiveness

		try {
			const data = await api.getProvisionDetail(internalId, {includeBreadcrumbs: true});
			setMainContentData(data);
			setBreadcrumbs(data.breadcrumbs ?? []);
        } catch (err) {
            console.error("Error fetching main content:", err);
            setError(`Failed to load provision: ${(err as Error).message}`);
            setMainContentData(null);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Function to fetch details for the side panel (DetailView) by Internal ID
    const fetchDetailContent = useCallback(async (internalId: string, type: 'reference' | 'term', termText?: string) => {
        try {
            const data = await api.getProvisionDetail(internalId);

            if (type === 'term' && termText) {
                setDetailViewContent({type: 'term', data, termText});
            } else {
                // Default to reference type if not a specific term click
                setDetailViewContent({type: 'reference', data});
            }

        } catch (err) {
            console.error("Error fetching detail content:", err);
            const errorMessage = (err as Error).message;
            if (errorMessage.includes("404") || errorMessage.includes("not found")) {
                setDetailViewContent({type: 'error', data: `Details not found for ID ${internalId}.`});
            } else {
                setDetailViewContent({type: 'error', data: `Failed to load details: ${errorMessage}`});
            }
        }
    }, []);

    // Function to fetch details by Ref ID (for InteractiveContent references)
    const fetchDetailContentByRefId = useCallback(async (refId: string) => {
        let actId = mainContentData?.act_id || selectedActId;
        // If the refId is fully qualified (e.g., ITAA1936:Section:6),
        // prefer the act prefix from the reference itself so cross-act
        // links resolve to the correct dataset.
        const prefix = refId.split(':', 1)[0];
        if (prefix && prefix !== actId) {
            actId = prefix;
        }

        if (!actId) {
            setDetailViewContent({
                type: 'error',
                data: 'No act context is available to resolve this reference.'
            });
            return;
        }

        try {
            const data = await api.getProvisionByRefId(refId, actId);
            setDetailViewContent({type: 'reference', data});
        } catch (err) {
            console.error("Error fetching detail content by Ref ID:", err);
            setDetailViewContent({
                type: 'error',
                data: `Reference could not be resolved: "${refId}". It might be external (another Act), or the lookup API failed. Error: ${(err as Error).message}`
            });
        }
    }, [mainContentData, selectedActId]);

    // Initial Load
    useEffect(() => {
        const initializeView = async () => {
            if (!selectedActId) return;

            setIsLoading(true);
            setError(null);
            setSelectedNodeId(null);
            setMainContentData(null);
            setBreadcrumbs([]);
            try {
                const topLevelNodes = await api.getHierarchy(selectedActId);
                if (topLevelNodes.length > 0) {
                    const initialNode = topLevelNodes[0];
                    fetchMainContent(initialNode.internal_id);
                } else {
                    setError(`No data found for Act: ${selectedActId}.`);
                }
            } catch (err) {
                console.error("Error initializing view:", err);
                setError("Failed to connect to the backend API. Ensure containers are running and required endpoints (see utils/api.ts) are implemented.");
            } finally {
                setIsLoading(false);
            }
        };
        initializeView();
    }, [selectedActId, fetchMainContent]);


    const handleSelectNode = useCallback((nodeId: string) => {
        fetchMainContent(nodeId);
    }, [fetchMainContent]);

    // Handler for links where internal ID is known (e.g., 'Referenced By' links)
    const handleReferenceClick = useCallback((internalId: string) => {
        fetchDetailContent(internalId, 'reference');
    }, [fetchDetailContent]);

    // Handler for links where only Ref ID is known (e.g., InteractiveContent references)
    const handleReferenceByRefIdClick = useCallback((refId: string) => {
        fetchDetailContentByRefId(refId);
    }, [fetchDetailContentByRefId]);

    // Handler for defined terms (InteractiveContent)
    const handleTermClick = useCallback((definitionInternalId: string, termText: string) => {
        fetchDetailContent(definitionInternalId, 'term', termText);
    }, [fetchDetailContent]);

    const persistSemanticSearchState = useCallback((nextState: SemanticSearchState) => {
        setSemanticSearchState(nextState);
        if (typeof window !== 'undefined') {
            try {
                window.localStorage.setItem(
                    SEMANTIC_SEARCH_STORAGE_KEY,
                    JSON.stringify({...nextState, act_id: selectedActId})
                );
            } catch (err) {
                console.warn('Failed to persist semantic search state:', err);
            }
        }
    }, [selectedActId]);

    const handleOpenSemanticSearch = useCallback(() => {
        setSemanticSearchOpen(true);
    }, []);

    const handleCloseSemanticSearch = useCallback(() => {
        setSemanticSearchOpen(false);
    }, []);


    if (isLoadingActs) {
        return (
            <div className="flex h-screen items-center justify-center bg-gray-900 text-gray-200">
                <p className="text-lg">Loading available acts…</p>
            </div>
        );
    }

    if (!selectedActId) {
        return (
            <div className="flex h-screen items-center justify-center bg-gray-900 text-gray-200">
                <p className="text-lg">No acts are available. Ingest an act and reload the page.</p>
            </div>
        );
    }

    // Render Global Error state
    if (error && !isLoading && (!mainContentData || !selectedNodeId)) {
        return (
            <div className="flex h-screen bg-gray-900 text-gray-200 justify-center items-center">
                <div className="text-red-400 p-8 border border-red-700 bg-gray-800 rounded-lg max-w-xl">
                    <h2 className="text-2xl font-bold mb-4">Application Error</h2>
                    <p>{error}</p>
					<p className="mt-4 text-sm text-gray-400">Please check the backend service status. Full
                        functionality requires the hierarchy/search endpoints and the provision detail + reference lookup APIs.</p>
                </div>
            </div>
        );
    }

    // Main Layout (Design restored from original)
    return (
        <ToastProvider>
            <div className="flex h-screen bg-gray-900 text-gray-200 font-sans">
            {/* Side Navigation Panel */}
            <div className="w-full md:w-1/4 h-full flex flex-col border-r border-gray-700 bg-gray-800">
                <header className="p-4 border-b border-gray-700 flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-4">
                        <img src={taxivLogo} alt="Taxiv" className="h-8 w-auto" />
                        <ActSelector acts={acts} value={selectedActId} onChange={next => setSelectedActId(next)} />
                    </div>
                    <button
                        type="button"
                        onClick={handleOpenSemanticSearch}
                        className="inline-flex items-center justify-center rounded-full border border-gray-600 p-2 text-gray-200 hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                        aria-label="Open semantic search"
                    >
                        <SearchIcon className="w-5 h-5"/>
                    </button>
                </header>
                <SideNav
                    actId={selectedActId}
                    onSelectNode={handleSelectNode}
                    selectedNodeId={selectedNodeId}
                />
            </div>

            {/* Main Content Panel */}
            <main className="w-full md:w-1/2 h-full overflow-y-auto bg-gray-900 scrollbar-stable">
                <MainContent
                    node={mainContentData}
                    breadcrumbs={breadcrumbs}
                    isLoading={isLoading}
                    onTermClick={handleTermClick}
                    onReferenceByRefIdClick={handleReferenceByRefIdClick}
                    onSelectNode={handleSelectNode}
                />
            </main>

            {/* Detail View Panel */}
            <aside
                className="hidden lg:block lg:w-1/4 h-full border-l border-gray-700 bg-gray-800 overflow-y-auto scrollbar-stable">
                <DetailView
                    content={detailViewContent}
                    onTermClick={handleTermClick}
                    onReferenceByRefIdClick={handleReferenceByRefIdClick}
                    onReferenceClick={handleReferenceClick} // For 'Referenced By' links (internal IDs known)
                    onSetMainView={handleSelectNode}
                />
            </aside>
            </div>
            <SemanticSearchModal
                isOpen={isSemanticSearchOpen}
                actId={selectedActId}
                acts={acts}
                onClose={handleCloseSemanticSearch}
                onSelectAct={next => setSelectedActId(next)}
                onSelectProvision={handleSelectNode}
                state={semanticSearchState}
                onStateChange={persistSemanticSearchState}
            />
        </ToastProvider>
    );
};

export default App;
