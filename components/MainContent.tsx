import React, { useCallback, useMemo, useState, useRef, useEffect } from 'react';
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
  const [visibleChildrenCount, setVisibleChildrenCount] = useState(10);
  const observer = useRef<IntersectionObserver>();

  const children = useMemo(() => {
    if (!node) return [];

    const getAllDescendants = (nodeId: string): TaxDataObject[] => {
      const directChildrenIds = processedData.childrenMap.get(nodeId) || [];
      const directChildren = directChildrenIds.map(id => processedData.nodeMapByInternalId.get(id)!).filter(Boolean);

      let allChildren: TaxDataObject[] = [];
      directChildren.forEach(child => {
        allChildren.push(child);
        allChildren = allChildren.concat(getAllDescendants(child.internal_id));
      });
      return allChildren;
    };

    return getAllDescendants(node.internal_id);
  }, [node, processedData]);

  useEffect(() => {
    setVisibleChildrenCount(10);
  }, [node]);

  const lastChildElementRef = useCallback(node => {
    if (observer.current) observer.current.disconnect();
    observer.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && visibleChildrenCount < children.length) {
        setVisibleChildrenCount(prevCount => prevCount + 10);
      }
    });
    if (node) observer.current.observe(node);
  }, [visibleChildrenCount, children.length]);

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
          {children.slice(0, visibleChildrenCount).map((child, index) => (
            <div
              key={child.internal_id}
              className="mt-4"
              ref={index === visibleChildrenCount - 1 ? lastChildElementRef : null}
            >
              <div className="prose prose-invert prose-sm sm:prose-base max-w-none">
                <h2 className="text-xl md:text-2xl font-bold text-gray-100 mt-1">{child.title}</h2>
                {child.ref_id && <p className="text-xs text-gray-500 font-mono mt-2">{child.ref_id}</p>}
              </div>
              <div className="mt-4 text-gray-300 leading-relaxed">
                <InteractiveContent
                  key={child.internal_id}
                  node={child}
                  onReferenceClick={onReferenceClick}
                  onTermClick={onTermClick}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MainContent;
