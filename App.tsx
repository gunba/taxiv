import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { taxDatabase } from './data/taxData';
import type { TaxDataObject, DetailViewContent } from './types';
import SideNav from './components/SideNav';
import MainContent from './components/MainContent';
import DetailView from './components/DetailView';
import { processRawData, ProcessedData } from './utils/dataProcessor';
import { LogoIcon } from './components/Icons';

const App: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [detailViewContent, setDetailViewContent] = useState<DetailViewContent | null>(null);
  
  const processedData: ProcessedData = useMemo(() => processRawData(taxDatabase), []);

  useEffect(() => {
    // Set initial selected node to the first proper section we can find
    if (processedData.tree.length > 0) {
        const findFirstSection = (nodes: TaxDataObject[]): TaxDataObject | null => {
            for (const node of nodes) {
                if (node.type === 'Section') return node;
                const children = (processedData.childrenMap.get(node.internal_id) || []).map(id => processedData.nodeMapByInternalId.get(id)!);
                const found = findFirstSection(children);
                if(found) return found;
            }
            return null;
        }
        const firstSection = findFirstSection(processedData.tree);
        if(firstSection) {
            setSelectedNodeId(firstSection.internal_id);
        }
    }
  }, [processedData]);

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
  }, []);

  const handleReferenceClick = useCallback((refId: string) => {
    const node = processedData.nodeMapByRefId.get(refId);
    if (node) {
      setDetailViewContent({ type: 'reference', data: node });
    } else {
      setDetailViewContent({ type: 'error', data: `Reference not found: ${refId}` });
    }
  }, [processedData]);

  const handleTermClick = useCallback((term: string) => {
    const definitionNode = processedData.definitionMapByTerm.get(term.toLowerCase());
    if (definitionNode) {
      setDetailViewContent({ type: 'term', data: definitionNode });
    } else {
      setDetailViewContent({ type: 'error', data: `Definition not found for "${term}".` });
    }
  }, [processedData]);

  const selectedNode = selectedNodeId ? processedData.nodeMapByInternalId.get(selectedNodeId) : null;

  return (
    <div className="flex h-screen bg-gray-900 text-gray-200 font-sans">
      <div className="w-full md:w-1/4 h-full flex flex-col border-r border-gray-700 bg-gray-800">
        <header className="p-4 border-b border-gray-700 flex items-center space-x-2 shrink-0">
          <LogoIcon className="w-8 h-8 text-blue-400"/>
          <h1 className="text-xl font-bold text-gray-100">Tax Code Explorer</h1>
        </header>
        <SideNav 
          nodes={processedData.tree} 
          onSelectNode={handleSelectNode} 
          selectedNode={selectedNode}
          processedData={processedData}
        />
      </div>
      <main className="w-full md:w-1/2 h-full overflow-y-auto bg-gray-900">
        <MainContent 
          node={selectedNode} 
          processedData={processedData}
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
