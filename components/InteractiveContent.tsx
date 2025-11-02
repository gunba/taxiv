// components/InteractiveContent.tsx
import React, {Children, useMemo} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {TaxDataObject} from '../types';

interface InteractiveContentProps {
    node: TaxDataObject;
    // Handler for defined terms (uses internal ID)
    onTermClick: (definitionInternalId: string, termText: string) => void;
    // Handler for references (uses Ref ID as internal ID is not available in ReferenceInfo)
    onReferenceByRefIdClick: (refId: string) => void;
}

const InteractiveContent: React.FC<InteractiveContentProps> = ({node, onTermClick, onReferenceByRefIdClick}) => {

    // Identify clickable elements based on API data
    const clickables = useMemo(() => {
        const items: { text: string; handler: () => void; type: 'ref' | 'term' }[] = [];

        // 1. Handle References (using snippet and target_ref_id)
        node.references_to.forEach(ref => {
            // We rely on the snippet being the exact text to highlight.
            if (ref.snippet && ref.target_ref_id) {
                items.push({
                    text: ref.snippet,
                    handler: () => onReferenceByRefIdClick(ref.target_ref_id),
                    type: 'ref',
                });
            }
        });

        // 2. Handle Defined Terms (using term_text and definition_internal_id)
        node.defined_terms_used.forEach(term => {
            if (term.definition_internal_id && term.term_text) {
                const handler = () => onTermClick(term.definition_internal_id!, term.term_text);

                // Add the plain text version
                items.push({
                    text: term.term_text,
                    handler: handler,
                    type: 'term',
                });

                // Robustness: Also add the asterisked version, as markdown source often uses them
                const asteriskedText = `*${term.term_text}*`;
                if (asteriskedText !== term.term_text) {
                    items.push({
                        text: asteriskedText,
                        handler: handler,
                        type: 'term',
                    });
                }
            }
        });

        // Sort by length descending (crucial for prioritizing longer matches)
        items.sort((a, b) => b.text.length - a.text.length);
        return items;
    }, [node, onTermClick, onReferenceByRefIdClick]);

    // Function to render text with interactive elements
    const renderInteractiveText = (text: string) => {
        if (!text || clickables.length === 0) {
            return text;
        }

        // Create the regex pattern safely
        const pattern = clickables.map(c => c.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
        if (!pattern) return text;

        const regex = new RegExp(`(${pattern})`, 'g');
        const parts = text.split(regex);

        return parts.map((part, i) => {
            if (!part) return null;
            const clickable = clickables.find(c => c.text === part);
            if (clickable) {
                return (
                    <button
                        key={i}
                        onClick={clickable.handler}
                        // Styling restored from the original frontend
                        className={`font-medium rounded px-1 py-0.5 ${clickable.type === 'ref' ? 'text-blue-400 hover:bg-blue-900' : 'text-green-400 hover:bg-green-900'} hover:underline transition-colors`}
                    >
                        {part}
                    </button>
                );
            }
            return part;
        });
    };

    // Helper function to process children recursively within Markdown components
    const processChildren = (childNodes: React.ReactNode): React.ReactNode => {
        return Children.map(childNodes, child => {
            if (typeof child === 'string') {
                return renderInteractiveText(child);
            }
            // Recurse into nested elements (like <em>, <strong>)
            if (React.isValidElement(child) && (child.props as any).children) {
                // Prevent reprocessing our own interactive buttons
                if (child.type === 'button' && (child.props as any).className?.includes('font-medium rounded px-1')) {
                    return child;
                }
                return React.cloneElement(child, {
                    ...(child.props as any),
                    children: processChildren((child.props as any).children),
                });
            }
            return child;
        });
    };

    const CustomParagraph = ({children}: { children: React.ReactNode }) => {
        // Indentation logic (restored from original)
        const textContent = Children.toArray(children).join('');
        let indentClass = '';
        if (/^\s*\(\d+\)/.test(textContent)) indentClass = 'pl-6'; // (1)
        if (/^\s*\([a-z]\)/.test(textContent)) indentClass = 'pl-12'; // (a)
        if (/^\s*\([ivx]+\)/.test(textContent)) indentClass = 'pl-18'; // (i)

        return <p className={`mb-4 ${indentClass}`}>{processChildren(children)}</p>;
    };

    // Apply processing to list items and table cells as well
    const CustomListItem = ({children}: { children: React.ReactNode }) => <li>{processChildren(children)}</li>;
    const CustomTableCell = ({children, ...props}: any) => <td
        className="border border-gray-600 px-4 py-2" {...props}>{processChildren(children)}</td>;


    return (
        <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
                p: CustomParagraph,
                li: CustomListItem,
                // Table styling (restored from original)
                table: ({node, ...props}) => <table
                    className="table-auto w-full my-4 border-collapse border border-gray-600" {...props} />,
                thead: ({node, ...props}) => <thead className="bg-gray-800" {...props} />,
                th: ({node, ...props}) => <th className="border border-gray-600 px-4 py-2 text-left" {...props} />,
                td: CustomTableCell,
            }}
        >
            {node.content_md || ""}
        </ReactMarkdown>
    );
};

export default InteractiveContent;