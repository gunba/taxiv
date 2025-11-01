// App.tsx
import React, { useState, useEffect, useCallback } from 'react';
import type { TaxDataObject, DetailViewContent } from './types';
import SideNav from './components/SideNav';
import MainContent from './components/MainContent';
import DetailView from './components/DetailView';
import { LogoIcon } from './components/Icons';
import { api } from './utils/api';

// Hardcode the primary Act ID for now.
const PRIMARY_ACT_ID = 'ITAA1997';

const App: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [mainContentData, setMainContentData] = useState<TaxDataObject | null>(null);
  // State for breadcrumbs (restored functionality)
  const [breadcrumbs, setBreadcrumbs] = useState<{ internal_id: string; title: string }[]>([]);
  const [detailViewContent, setDetailViewContent] = useState<DetailViewContent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Function to fetch details for the main view
  const fetchMainContent = useCallback(async (internalId: string) => {
    if (internalId === selectedNodeId) return;

    setIsLoading(true);
    setError(null);
    setSelectedNodeId(internalId); // Update ID immediately for responsiveness

    try {
        // Fetch detail and breadcrumbs concurrently (requires api.getBreadcrumbs)
      const [data, crumbs] = await Promise.all([
            api.getProvisionDetail(internalId),
            api.getBreadcrumbs(internalId).catch(err => {
                console.warn("Failed to load breadcrumbs (ensure API endpoint exists):", err);
                return []; // Fallback if the API fails
            })
        ]);

      setMainContentData(data);
        setBreadcrumbs(crumbs);
    } catch (err) {
      console.error("Error fetching main content:", err);
      setError(`Failed to load provision: ${(err as Error).message}`);
      setMainContentData(null);
    } finally {
      setIsLoading(false);
    }
  }, [selectedNodeId]);

  // Function to fetch details for the side panel (DetailView) by Internal ID
  const fetchDetailContent = useCallback(async (internalId: string, type: 'reference' | 'term', termText?: string) => {
    try {
      const data = await api.getProvisionDetail(internalId);

      if (type === 'term' && termText) {
        setDetailViewContent({ type: 'term', data, termText });
      } else {
        // Default to reference type if not a specific term click
        setDetailViewContent({ type: 'reference', data });
      }

    } catch (err) {
      console.error("Error fetching detail content:", err);
      const errorMessage = (err as Error).message;
      if (errorMessage.includes("404") || errorMessage.includes("not found")) {
        setDetailViewContent({ type: 'error', data: `Details not found for ID ${internalId}.` });
      } else {
        setDetailViewContent({ type: 'error', data: `Failed to load details: ${errorMessage}` });
      }
    }
  }, []);

  // Function to fetch details by Ref ID (for InteractiveContent references)
  const fetchDetailContentByRefId = useCallback(async (refId: string) => {
    // Use the context of the currently viewed Act for the lookup, fallback to primary
    const actId = mainContentData?.act_id || PRIMARY_ACT_ID;

    try {
        // Requires the api.getProvisionByRefId endpoint
        const data = await api.getProvisionByRefId(refId, actId);
        setDetailViewContent({ type: 'reference', data });
    } catch (err) {
        console.error("Error fetching detail content by Ref ID:", err);
        setDetailViewContent({ type: 'error', data: `Reference could not be resolved: "${refId}". It might be external (another Act), or the lookup API failed. Error: ${(err as Error).message}` });
    }
  }, [mainContentData]);

  // Initial Load
  useEffect(() => {
    const initializeView = async () => {
      if (selectedNodeId) return;

      setIsLoading(true);
      try {
        const topLevelNodes = await api.getHierarchy(PRIMARY_ACT_ID);
        if (topLevelNodes.length > 0) {
          const initialNode = topLevelNodes[0];
          fetchMainContent(initialNode.internal_id);
        } else {
          setError("No data found for Act: " + PRIMARY_ACT_ID + ".");
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Error initializing view:", err);
        setError("Failed to connect to the backend API. Ensure containers are running and required endpoints (see utils/api.ts) are implemented.");
        setIsLoading(false);
      }
    };
    initializeView();
  }, [fetchMainContent, selectedNodeId]);


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


  // Render Global Error state
  if (error && !isLoading && (!mainContentData || !selectedNodeId)) {
    return (
      <div className="flex h-screen bg-gray-900 text-gray-200 justify-center items-center">
      <div className="text-red-400 p-8 border border-red-700 bg-gray-800 rounded-lg max-w-xl">
      <h2 className="text-2xl font-bold mb-4">Application Error</h2>
      <p>{error}</p>
      <p className="mt-4 text-sm text-gray-400">Please check the backend service status. Full functionality requires endpoints for search, breadcrumbs, and reference lookup.</p>
      </div>
      </div>
    );
  }

  // Main Layout (Design restored from original)
  return (
    <div className="flex h-screen bg-gray-900 text-gray-200 font-sans">
      {/* Side Navigation Panel */}
    <div className="w-full md:w-1/4 h-full flex flex-col border-r border-gray-700 bg-gray-800">
    <header className="p-4 border-b border-gray-700 flex items-center space-x-2 shrink-0">
    <LogoIcon className="w-8 h-8 text-blue-400"/>
    <h1 className="text-xl font-bold text-gray-100">Tax Code Explorer</h1>
    </header>
    <SideNav
    actId={PRIMARY_ACT_ID}
    onSelectNode={handleSelectNode}
    selectedNodeId={selectedNodeId}
    />
    </div>

    {/* Main Content Panel */}
    <main className="w-full md:w-1/2 h-full overflow-y-auto bg-gray-900">
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
    <aside className="hidden lg:block lg:w-1/4 h-full border-l border-gray-700 bg-gray-800 overflow-y-auto">
    <DetailView
    content={detailViewContent}
    onTermClick={handleTermClick}
      onReferenceByRefIdClick={handleReferenceByRefIdClick}
      onReferenceClick={handleReferenceClick} // For 'Referenced By' links (internal IDs known)
    onSetMainView={handleSelectNode}
    />
    </aside>
    </div>
  );
};

export default App;