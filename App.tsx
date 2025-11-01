// App.tsx
import React, { useState, useEffect, useCallback } from 'react';
// Removed static data imports and dataProcessor
import type { TaxDataObject, DetailViewContent } from './types';
import SideNav from './components/SideNav';
import MainContent from './components/MainContent';
import DetailView from './components/DetailView';
import { LogoIcon } from './components/Icons';
import { api } from './utils/api'; // Import the new API utility

// Hardcode the primary Act ID for now.
const PRIMARY_ACT_ID = 'ITAA1997';

const App: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [mainContentData, setMainContentData] = useState<TaxDataObject | null>(null);
  const [detailViewContent, setDetailViewContent] = useState<DetailViewContent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Function to fetch details for the main view
  const fetchMainContent = useCallback(async (internalId: string) => {
    // Prevent re-fetching if already selected
    if (internalId === selectedNodeId) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getProvisionDetail(internalId);
      setMainContentData(data);
      setSelectedNodeId(internalId);
    } catch (err) {
      console.error("Error fetching main content:", err);
      setError(`Failed to load provision: ${(err as Error).message}`);
      setMainContentData(null);
    } finally {
      setIsLoading(false);
    }
  }, [selectedNodeId]);

  // Function to fetch details for the side panel (DetailView)
  const fetchDetailContent = useCallback(async (internalId: string, type: 'reference' | 'term') => {
    try {
      // Do not set the main loading spinner for side panel requests
      const data = await api.getProvisionDetail(internalId);
      setDetailViewContent({ type, data });
    } catch (err) {
      console.error("Error fetching detail content:", err);
      // Handle specific errors (e.g., 404 for external references)
      if ((err as Error).message.includes("404")) {
        setDetailViewContent({ type: 'error', data: `Details not found for ID ${internalId}. This may be an external reference or a missing provision.` });
      } else {
        setDetailViewContent({ type: 'error', data: `Failed to load details: ${(err as Error).message}` });
      }
    }
  }, []);

  // Initial Load: Fetch the first available top-level item
  useEffect(() => {
    const initializeView = async () => {
      if (selectedNodeId) return; // Prevent re-initialization

      setIsLoading(true);
      try {
        // Fetch top-level hierarchy
        const topLevelNodes = await api.getHierarchy(PRIMARY_ACT_ID);
        if (topLevelNodes.length > 0) {
          // Heuristic: Start with the first available node.
          const initialNode = topLevelNodes[0];
          fetchMainContent(initialNode.internal_id);
        } else {
          setError("No data found for Act: " + PRIMARY_ACT_ID + ". Ensure ingestion pipeline has run.");
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Error initializing view:", err);
        setError("Failed to connect to the backend API. Ensure Docker containers are running.");
        setIsLoading(false);
      }
    };
    initializeView();
  }, [fetchMainContent, selectedNodeId]);


  const handleSelectNode = useCallback((nodeId: string) => {
    // When a node is selected in the SideNav, fetch its full details
    fetchMainContent(nodeId);
  }, [fetchMainContent]);

  // Handlers now expect internal IDs (provided by the API data)
  const handleReferenceClick = useCallback((internalId: string) => {
    fetchDetailContent(internalId, 'reference');
  }, [fetchDetailContent]);

  const handleTermClick = useCallback((definitionInternalId: string) => {
    fetchDetailContent(definitionInternalId, 'term');
  }, [fetchDetailContent]);


  // Render Global Error state
  if (error && !isLoading && !mainContentData) {
    return (
      <div className="flex h-screen bg-gray-900 text-gray-200 justify-center items-center">
      <div className="text-red-400 p-8 border border-red-700 bg-gray-800 rounded-lg max-w-xl">
      <h2 className="text-2xl font-bold mb-4">Application Error</h2>
      <p>{error}</p>
      <p className="mt-4 text-sm text-gray-400">Please check the backend service status (docker-compose logs) and browser console for details.</p>
      </div>
      </div>
    );
  }

  // Main Layout
  return (
    <div className="flex h-screen bg-gray-900 text-gray-200 font-sans">
    <div className="w-full md:w-1/4 h-full flex flex-col border-r border-gray-700 bg-gray-800">
    <header className="p-4 border-b border-gray-700 flex items-center space-x-2 shrink-0">
    <LogoIcon className="w-8 h-8 text-blue-400"/>
    <h1 className="text-xl font-bold text-gray-100">Tax Code Explorer ({PRIMARY_ACT_ID})</h1>
    </header>
    {/* SideNav fetches its own data dynamically */}
    <SideNav
    actId={PRIMARY_ACT_ID}
    onSelectNode={handleSelectNode}
    selectedNodeId={selectedNodeId}
    />
    </div>
    <main className="w-full md:w-1/2 h-full overflow-y-auto bg-gray-900">
    <MainContent
    node={mainContentData}
    isLoading={isLoading}
    onReferenceClick={handleReferenceClick}
    onTermClick={handleTermClick}
    onSelectNode={handleSelectNode}
    />
    </main>
    <aside className="hidden lg:block lg:w-1/4 h-full border-l border-gray-700 bg-gray-800 overflow-y-auto">
    <DetailView
    content={detailViewContent}
    onReferenceClick={handleReferenceClick}
    onTermClick={handleTermClick}
    onSetMainView={handleSelectNode}
    />
    </aside>
    </div>
  );
};

export default App;
