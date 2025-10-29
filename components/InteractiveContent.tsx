import React, { useMemo, Children } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { TaxDataObject } from '../types';

interface InteractiveContentProps {
  node: TaxDataObject;
  onReferenceClick: (refId: string) => void;
  onTermClick: (term: string) => void;
}

const InteractiveContent: React.FC<InteractiveContentProps> = ({ node, onReferenceClick, onTermClick }) => {
  const clickables = useMemo(() => {
    const items: { text: string; handler: () => void; type: 'ref' | 'term' }[] = [];
    node.references_with_snippets_normalized.forEach(ref => {
      items.push({
        text: ref.snippet,
        handler: () => onReferenceClick(ref.normalized_ref_id),
        type: 'ref',
      });
    });
    node.defined_terms_used.forEach(term => {
      items.push({
        text: term,
        handler: () => onTermClick(term),
        type: 'term',
      });
    });
    items.sort((a, b) => b.text.length - a.text.length);
    return items;
  }, [node, onReferenceClick, onTermClick]);

  const renderInteractiveText = (text: string) => {
    if (clickables.length === 0) {
      return text;
    }

    const regex = new RegExp(`(${clickables.map(c => c.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g');
    const parts = text.split(regex);

    return parts.map((part, i) => {
      const clickable = clickables.find(c => c.text === part);
      if (clickable) {
        return (
          <button
            key={i}
            onClick={clickable.handler}
            className={`font-medium rounded px-1 py-0.5 ${clickable.type === 'ref' ? 'text-blue-400 hover:bg-blue-900' : 'text-green-400 hover:bg-green-900'} hover:underline transition-colors`}
          >
            {part}
          </button>
        );
      }
      return part;
    });
  };

  const CustomParagraph = ({ children }: { children: React.ReactNode }) => {
    const processChildren = (childNodes: React.ReactNode): React.ReactNode => {
      return Children.map(childNodes, child => {
        if (typeof child === 'string') {
          return renderInteractiveText(child);
        }
        if (React.isValidElement(child) && child.props.children) {
          return React.cloneElement(child, {
            ...child.props,
            children: processChildren(child.props.children),
          });
        }
        return child;
      });
    };

    const textContent = Children.toArray(children).join('');
    let indentClass = '';
    if (/^\s*\(\d+\)/.test(textContent)) indentClass = 'pl-6'; // (1)
    if (/^\s*\([a-z]\)/.test(textContent)) indentClass = 'pl-12'; // (a)
    if (/^\s*\([ivx]+\)/.test(textContent)) indentClass = 'pl-18'; // (i)

    return <p className={`mb-4 ${indentClass}`}>{processChildren(children)}</p>;
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: CustomParagraph,
        table: ({node, ...props}) => <table className="table-auto w-full my-4 border-collapse border border-gray-600" {...props} />,
        thead: ({node, ...props}) => <thead className="bg-gray-800" {...props} />,
        th: ({node, ...props}) => <th className="border border-gray-600 px-4 py-2 text-left" {...props} />,
        td: ({node, ...props}) => <td className="border border-gray-600 px-4 py-2" {...props} />,
      }}
    >
      {node.content_md}
    </ReactMarkdown>
  );
};

export default InteractiveContent;
