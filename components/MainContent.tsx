// components/MainContent.tsx
import React, { useEffect, useCallback } from 'react';
import { TaxDataObject } from '../types';
import InteractiveContent from './InteractiveContent';
import { ClipboardIcon, ChevronRightIcon } from './Icons';

interface MainContentProps {
  node: TaxDataObject | null;
  // Added breadcrumbs prop
  breadcrumbs: { internal_id: string; title: string }[];
  isLoading: boolean;
  // Handlers for InteractiveContent
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
    onSelectNode
}) => {

  // Scroll to top when the node changes
  useEffect(() => {
    const mainElement = document.querySelector('main');
    if (mainElement) {
      mainElement.scrollTo(0, 0);
    }
  }, [node]);

  // Copy to Clipboard functionality (Restored from original)
  const copyToClipboard = useCallback(() => {
    if (!node || !node.content_md) return;
    // Note: Unlike the original, this only copies the current provision content, as descendant data is not fetched here due to the new architecture.
    const markdown = `# ${node.title}\n\n${node.content_md}\n\n`;
    navigator.clipboard.writeText(markdown).then(() => {
      // Optional: Show a "copied!" notification
    }).catch(err => console.error('Failed to copy text: ', err));
  }, [node]);


  if (isLoading) {
    return <div className="p-8 text-center text-gray-400">Loading provision details...</div>;
  }

  if (!node) {
    // Welcome message restored from original
    return (
      <div className="p-8 text-center text-gray-400">
        <h2 className="text-2xl font-semibold">Welcome to the Tax Code Explorer</h2>
        <p className="mt-2">Select an item from the navigation panel on the left to view its content here.</p>
      </div>
    );
  }

  // Layout restored from original
  return (
    <div className="p-6 md:p-8">
      {/* Header area with Breadcrumbs and Copy button */}
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-gray-700">
        <div className="flex items-center text-sm text-gray-400 overflow-hidden">
            {/* Breadcrumbs display */}
            {breadcrumbs.length > 0 ? breadcrumbs.map((crumb, index) => (
                <React.Fragment key={crumb.internal_id}>
                    <button onClick={() => onSelectNode(crumb.internal_id)} className="truncate hover:underline whitespace-nowrap">
                        {crumb.title}
                    </button>
                    {index < breadcrumbs.length - 1 && <ChevronRightIcon className="w-4 h-4 mx-1 shrink-0" />}
                </React.Fragment>
            )) : (
                <span className="text-gray-500 text-xs">(Loading breadcrumbs or API unavailable)</span>
            )}
        </div>
        <button onClick={copyToClipboard} className="p-2 rounded-md hover:bg-gray-700 text-gray-400 hover:text-white transition-colors shrink-0 ml-4" aria-label="Copy content to clipboard">
          <ClipboardIcon className="w-5 h-5" />
        </button>
      </div>

      {/* Title area */}
      <div className="prose prose-invert prose-sm sm:prose-base max-w-none">
        <p className="text-sm font-semibold text-blue-400">{node.type}</p>
        <h1 className="text-2xl md:text-3xl font-bold text-gray-100 mt-1">{node.title}</h1>
        {node.ref_id && <p className="text-xs text-gray-500 font-mono mt-2">{node.ref_id}</p>}
      </div>

      {/* Content Rendering using InteractiveContent */}
      <div className="mt-4 text-gray-300 leading-relaxed prose prose-invert max-w-none">
        <InteractiveContent
          key={node.internal_id}
          node={node}
          onTermClick={onTermClick}
          onReferenceByRefIdClick={onReferenceByRefIdClick}
        />
      </div>

      {/* Note: The original infinite scroll display of children is omitted as it is incompatible with the API's single-provision detail endpoint architecture. */}

    </div>
  );
};

export default MainContent;