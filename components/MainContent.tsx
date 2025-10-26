import React, { useCallback, useMemo } from 'react';
import type { TaxDataObject } from '../types';
import { ProcessedData } from '../utils/dataProcessor';
import InteractiveContent from './InteractiveContent';
import { ClipboardIcon, ChevronRightIcon } from './Icons';

interface MainContentProps {
  node: TaxDataObject | null;
  processedData: ProcessedData;
  onReferenceClick: (refId: string) => void;
  onTermClick: (term: string) => void;
  onSelectNode: (nodeId: string) => void;
}

const MainContent: React.FC<MainContentProps> = ({ node, processedData, onReferenceClick, onTermClick, onSelectNode }) => {
  const children = useMemo(() => {
    if (!node) return [];
    const childIds = processedData.childrenMap.get(node.internal_id) || [];
    return childIds.map(id => processedData.nodeMapByInternalId.get(id)!).filter(Boolean);
  }, [node, processedData]);

  const breadcrumbs = useMemo(() => {
    if (!node) return [];
    const path = [];
    let current = node;
    while(current) {
        path.unshift(current);
        if(!current.parent_internal_id) break;
        current = processedData.nodeMapByInternalId.get(current.parent_internal_id)!;
    }
    return path;
  }, [node, processedData]);

  const copyToClipboard = useCallback(() => {
    if (!node) return;
    let markdown = `# ${node.title}\n\n${node.content_md}\n\n`;
    if (children.length > 0) {
      markdown += `## Subsections\n\n`;
      children.forEach(child => {
        markdown += `### ${child.title}\n\n${child.content_md}\n\n`;
      });
    }
    navigator.clipboard.writeText(markdown).then(() => {
      // Maybe show a small "copied!" notification
    }).catch(err => console.error('Failed to copy text: ', err));
  }, [node, children]);

  if (!node) {
    return (
      <div className="p-8 text-center text-gray-400">
        <h2 className="text-2xl font-semibold">Welcome to the Tax Code Explorer</h2>
        <p className="mt-2">Select an item from the navigation panel on the left to view its content here.</p>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8">
      <div className="flex items-center justify-between pb-4 mb-4 border-b border-gray-700">
        <div className="flex items-center text-sm text-gray-400 overflow-hidden">
            {breadcrumbs.map((crumb, index) => (
                <React.Fragment key={crumb.internal_id}>
                    <button onClick={() => onSelectNode(crumb.internal_id)} className="truncate hover:underline whitespace-nowrap">
                        {crumb.name}
                    </button>
                    {index < breadcrumbs.length - 1 && <ChevronRightIcon className="w-4 h-4 mx-1 shrink-0" />}
                </React.Fragment>
            ))}
        </div>
        <button onClick={copyToClipboard} className="p-2 rounded-md hover:bg-gray-700 text-gray-400 hover:text-white transition-colors" aria-label="Copy content to clipboard">
          <ClipboardIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="prose prose-invert prose-sm sm:prose-base max-w-none">
        <p className="text-sm font-semibold text-blue-400">{node.type}</p>
        <h1 className="text-2xl md:text-3xl font-bold text-gray-100 mt-1">{node.title}</h1>
        {node.ref_id && <p className="text-xs text-gray-500 font-mono mt-2">{node.ref_id}</p>}
      </div>

      <div className="mt-4 text-gray-300 leading-relaxed">
        <InteractiveContent 
          key={node.internal_id}
          node={node}
          onReferenceClick={onReferenceClick}
          onTermClick={onTermClick}
        />
      </div>

      {children.length > 0 && (
        <div className="mt-8 pt-6 border-t border-gray-700">
          <h2 className="text-xl font-semibold text-gray-200 mb-4">In this {node.type}:</h2>
          <div className="space-y-4">
            {children.map(child => (
              <div key={child.internal_id} className="p-4 rounded-lg bg-gray-800 border border-gray-700">
                <button onClick={() => onSelectNode(child.internal_id)} className="w-full text-left">
                  <h3 className="text-lg font-bold text-blue-400 hover:underline">{child.title}</h3>
                  <p className="text-xs text-gray-500 font-mono mt-1">{child.ref_id}</p>
                  <p className="mt-2 text-sm text-gray-400 line-clamp-3">{child.content_md.replace(/(\r\n|\n|\r)/gm, " ").substring(0, 200)}...</p>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default MainContent;
