// components/DetailView.tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DetailViewContent, TaxDataObject } from '../types';

interface DetailViewProps {
  content: DetailViewContent | null;
  // We use internal IDs for interaction now
  onReferenceClick: (internalId: string) => void;
  onTermClick: (definitionInternalId: string) => void;
  onSetMainView: (nodeId: string) => void;
}

const DetailView: React.FC<DetailViewProps> = ({ content, onReferenceClick, onTermClick, onSetMainView }) => {
  if (!content) {
    return (
      <div className="p-4 text-gray-400 text-sm">
      Click on a defined term (e.g., <span className="defined-term">*term</span>) in the main content to see details here.
      </div>
    );
  }

  if (content.type === 'error') {
    return (
      <div className="p-4 text-red-400">
      <h2 className="font-bold mb-2">Error</h2>
      <p>{content.data}</p>
      </div>
    );
  }

  const node: TaxDataObject = content.data;

  return (
    <div className="p-6">
    <header className="mb-4 pb-4 border-b border-gray-700">
    <h2 className="text-xl font-bold text-gray-100 mb-2">{node.title}</h2>
    {node.ref_id && (
      <p className="text-sm text-gray-500">{node.ref_id} ({node.type})</p>
    )}
    <button
    onClick={() => onSetMainView(node.internal_id)}
    className="mt-3 text-blue-400 hover:text-blue-300 text-sm font-medium"
    >
    Open in Main View
    </button>
    </header>

    <div className="prose prose-invert max-w-none text-sm mb-6">
    {/* Note: We don't process defined terms recursively in the DetailView. */}
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
    {node.content_md || "No content available."}
    </ReactMarkdown>
    </div>

    {/* Referenced By (Incoming Links) */}
    {node.referenced_by.length > 0 && (
      <section className="mt-6 pt-4 border-t border-gray-700">
      <h3 className="text-lg font-semibold text-gray-100 mb-3">Referenced By ({node.referenced_by.length})</h3>
      <ul className="space-y-2 text-sm">
      {node.referenced_by.map((ref, index) => (
        <li key={index}>
        <button
        // Clicking a 'Referenced By' link loads it into the DetailView panel
        onClick={() => onReferenceClick(ref.source_internal_id)}
        className="text-blue-400 hover:text-blue-300 text-left"
        >
        {ref.source_ref_id}: {ref.source_title}
        </button>
        </li>
      ))}
      </ul>
      </section>
    )}
    </div>
  );
};

export default DetailView;
