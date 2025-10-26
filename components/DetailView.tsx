import React from 'react';
import type { DetailViewContent, TaxDataObject } from '../types';
import InteractiveContent from './InteractiveContent';
import { PinIcon } from './Icons';

interface DetailViewProps {
  content: DetailViewContent | null;
  onReferenceClick: (refId: string) => void;
  onTermClick: (term: string) => void;
  onSetMainView: (nodeId: string) => void;
}

const DetailView: React.FC<DetailViewProps> = ({ content, onReferenceClick, onTermClick, onSetMainView }) => {
  if (!content) {
    return (
      <div className="p-6 text-center text-gray-500">
        <p className="mt-4">Click on a <span className="text-blue-400 font-semibold">section reference</span> or a <span className="text-green-400 font-semibold">*defined term*</span> in the main content to see details here.</p>
      </div>
    );
  }

  return (
    <div className="p-6 text-gray-300">
      {content.type === 'reference' && (
        <div>
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-semibold text-blue-400">{content.data.type}</p>
              <h2 className="text-xl font-bold text-gray-100 mt-1">{content.data.title}</h2>
            </div>
            <button 
                onClick={() => onSetMainView(content.data.internal_id)}
                className="p-2 rounded-md hover:bg-gray-700 text-gray-400 hover:text-white transition-colors ml-2 shrink-0" 
                aria-label="Set as main view"
                title="Set as main view"
            >
              <PinIcon className="w-5 h-5" />
            </button>
          </div>

          {content.data.ref_id && <p className="text-xs text-gray-500 font-mono mt-2 mb-4">{content.data.ref_id}</p>}
          <div className="mt-4 prose prose-invert prose-sm max-w-none leading-relaxed">
            <InteractiveContent 
                key={content.data.internal_id}
                node={content.data}
                onReferenceClick={onReferenceClick}
                onTermClick={onTermClick}
            />
          </div>
        </div>
      )}
      {content.type === 'term' && (
        <div>
          <p className="text-sm font-semibold text-green-400">Defined Term</p>
          <h2 className="text-xl font-bold text-gray-100 mt-1 capitalize">{content.data.raw_term}</h2>
          <div className="mt-4 prose prose-invert prose-sm max-w-none leading-relaxed">
             <InteractiveContent 
                key={content.data.internal_id}
                node={content.data}
                onReferenceClick={onReferenceClick}
                onTermClick={onTermClick}
            />
          </div>
        </div>
      )}
      {content.type === 'error' && (
         <div>
          <p className="text-sm font-semibold text-red-400">Error</p>
          <p className="mt-2 text-red-300">{content.data}</p>
        </div>
      )}
    </div>
  );
};

export default DetailView;
