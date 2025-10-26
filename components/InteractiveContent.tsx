import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { TaxDataObject } from '../types';

interface InteractiveContentProps {
  node: TaxDataObject;
  onReferenceClick: (refId: string) => void;
  onTermClick: (term: string) => void;
}

const InteractiveContent: React.FC<InteractiveContentProps> = ({ node, onReferenceClick, onTermClick }) => {
  const contentParts = useMemo(() => {
    let content = node.content_md;
    
    // Create a combined list of all items to link
    const clickables: { text: string; handler: () => void; type: 'ref' | 'term' }[] = [];

    // Add references
    node.references_with_snippets_normalized.forEach(ref => {
      clickables.push({
        text: ref.snippet,
        handler: () => onReferenceClick(ref.normalized_ref_id),
        type: 'ref',
      });
    });

    // Add defined terms (which are wrapped in asterisks in the markdown)
    node.defined_terms_used.forEach(term => {
      clickables.push({
        text: `*${term}*`,
        handler: () => onTermClick(term),
        type: 'term',
      });
    });

    // Sort by length descending to avoid partial matches (e.g., matching "section 1" before "section 1-A")
    clickables.sort((a, b) => b.text.length - a.text.length);
    
    // Create a regex to find all occurrences of these strings
    const regex = new RegExp(clickables.map(c => c.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
    const matches = Array.from(content.matchAll(regex));

    if (matches.length === 0) {
      return [content];
    }
    
    const result: (string | React.ReactNode)[] = [];
    let lastIndex = 0;

    matches.forEach((match, i) => {
      const foundText = match[0];
      const clickable = clickables.find(c => c.text === foundText);
      
      // FIX: Add type check for match.index, as it can be undefined.
      if (typeof match.index !== 'number') {
        return;
      }

      // Add the text before the match
      if (match.index > lastIndex) {
        result.push(content.substring(lastIndex, match.index));
      }

      // Add the clickable element
      if (clickable) {
          result.push(
            <button
                key={`${clickable.type}-${i}`}
                onClick={clickable.handler}
                className={`font-medium rounded px-1 py-0.5 ${clickable.type === 'ref' ? 'text-blue-400 hover:bg-blue-900' : 'text-green-400 hover:bg-green-900'} hover:underline transition-colors`}
            >
                {clickable.type === 'term' ? clickable.text.slice(1, -1) : clickable.text}
            </button>
          );
      }
      
      lastIndex = match.index + foundText.length;
    });

    // Add any remaining text after the last match
    if (lastIndex < content.length) {
      result.push(content.substring(lastIndex));
    }

    return result;

  }, [node, onReferenceClick, onTermClick]);
  
  return (
    <div>
      {contentParts.map((part, i) =>
        typeof part === 'string' ? (
          <ReactMarkdown
            key={i}
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({node, ...props}) => <table className="table-auto w-full my-4 border-collapse border border-gray-600" {...props} />,
              thead: ({node, ...props}) => <thead className="bg-gray-800" {...props} />,
              th: ({node, ...props}) => <th className="border border-gray-600 px-4 py-2 text-left" {...props} />,
              td: ({node, ...props}) => <td className="border border-gray-600 px-4 py-2" {...props} />,
              p: ({node, ...props}) => {
                const textContent = (node.children[0] as any)?.value || '';
                let indentClass = '';
                if (/^\s*\(\d+\)/.test(textContent)) indentClass = 'pl-6'; // (1)
                if (/^\s*\([a-z]\)/.test(textContent)) indentClass = 'pl-12'; // (a)
                if (/^\s*\([ivx]+\)/.test(textContent)) indentClass = 'pl-18'; // (i)
                return <p className={`mb-4 ${indentClass}`} {...props} />;
              },
            }}
          >
            {part}
          </ReactMarkdown>
        ) : (
          part
        )
      )}
    </div>
  );
};

export default InteractiveContent;