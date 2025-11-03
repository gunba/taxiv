// components/InteractiveContent.tsx
import React, {Children, useMemo} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type {TaxDataObject} from '../types';

type IndentationResult = {
    children: React.ReactNode;
    className: string;
    style?: React.CSSProperties;
    consumed: boolean;
};

const TAILWIND_INDENT_VALUES = new Set([
    4,
    8,
    12,
    16,
    20,
    24,
    28,
    32,
    36,
    40,
    44,
    48,
    52,
    56,
    60,
    64,
    72,
    80,
    96,
]);

const escapeForRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const computePaddingFromSpaces = (spaces: number): Pick<IndentationResult, 'className' | 'style'> => {
    if (spaces <= 0) {
        return {className: '', style: undefined};
    }

    const usesTailwindClass = spaces % 4 === 0 && TAILWIND_INDENT_VALUES.has(spaces);
    if (usesTailwindClass) {
        return {className: `pl-${spaces}`, style: undefined};
    }

    const remValue = Number((spaces * 0.25).toFixed(4));
    return {className: '', style: {paddingLeft: `${remValue}rem`}};
};

const normalizeIndentation = (childNodes: React.ReactNode): IndentationResult => {
    const arrayChildren = Children.toArray(childNodes);
    const firstTextIndex = arrayChildren.findIndex(node => typeof node === 'string');
    if (firstTextIndex === -1) {
        return {children: childNodes, className: '', style: undefined, consumed: false};
    }

    const firstText = arrayChildren[firstTextIndex] as string;
    const indentMatch = firstText.match(/^(?:\n*)([ \t]+)/);
    if (!indentMatch) {
        return {children: childNodes, className: '', style: undefined, consumed: false};
    }

    const rawIndent = indentMatch[1];
    const spaces = rawIndent.replace(/\t/g, '    ').length;
    if (spaces === 0) {
        return {children: childNodes, className: '', style: undefined, consumed: false};
    }

    const indentPattern = escapeForRegex(rawIndent);
    const trimmedText = firstText.replace(new RegExp(`(^|\n)${indentPattern}`, 'g'), (_match, prefix) => prefix);
    const updatedChildren = [...arrayChildren];
    updatedChildren[firstTextIndex] = trimmedText;

    const padding = computePaddingFromSpaces(spaces);
    return {
        children: updatedChildren,
        className: padding.className,
        style: padding.style,
        consumed: true,
    };
};

interface InteractiveContentProps {
    node: TaxDataObject;
    // Handler for defined terms (uses internal ID)
    onTermClick: (definitionInternalId: string, termText: string) => void;
    // Handler for references (uses Ref ID as internal ID is not available in ReferenceInfo)
    onReferenceByRefIdClick: (refId: string) => void;
}

const InteractiveContent: React.FC<InteractiveContentProps> = ({node, onTermClick, onReferenceByRefIdClick}) => {

    // Identify clickable elements based on API data
    const {clickables, clickablesRegex} = useMemo(() => {
        type ClickableBase = { text: string; key: string; handler: () => void; type: 'ref' | 'term' };
        type ClickableExternal = { text: string; key: string; handler: () => void; type: 'external'; href: string };
        type ClickableItem = ClickableBase | ClickableExternal;

        const items: ClickableItem[] = [];

        // 1. Handle References (using snippet and target_ref_id)
        node.references_to.forEach(ref => {
            // We rely on the snippet being the exact text to highlight.
            if (ref.snippet && ref.target_ref_id) {
                const targetsSameAct = ref.target_ref_id.startsWith(node.act_id);

                if (targetsSameAct && !ref.target_title) {
                    // Skip unresolved internal references lacking target title data.
                    return;
                }

                if (!targetsSameAct) {
                    const query = encodeURIComponent(ref.target_ref_id.replace(/[:_-]+/g, ' '));
                    const href = `https://www.google.com/search?q=${query}`;

                    items.push({
                        text: ref.snippet,
                        key: ref.snippet.toLowerCase(),
                        handler: () => {
                            if (typeof window !== 'undefined') {
                                window.open(href, '_blank', 'noopener,noreferrer');
                            }
                        },
                        type: 'external',
                        href,
                    });
                    return;
                }

                items.push({
                    text: ref.snippet,
                    key: ref.snippet.toLowerCase(),
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
                    key: term.term_text.toLowerCase(),
                    handler: handler,
                    type: 'term',
                });

                // Robustness: Also add the asterisked version, as markdown source often uses them
                const asteriskedText = `*${term.term_text}*`;
                if (asteriskedText !== term.term_text) {
                    items.push({
                        text: asteriskedText,
                        key: asteriskedText.toLowerCase(),
                        handler: handler,
                        type: 'term',
                    });
                }
            }
        });

        // Sort by length descending (crucial for prioritizing longer matches)
        items.sort((a, b) => b.text.length - a.text.length);
        const uniquePatterns = Array.from(new Set(items.map(item => item.text)))
            .map(text => `(?<!\\w)${escapeForRegex(text)}(?!\\w)`);

        const pattern = uniquePatterns.join('|');
        const regex = pattern ? new RegExp(`(${pattern})`, 'gi') : null;

        return {clickables: items, clickablesRegex: regex};
    }, [node, onTermClick, onReferenceByRefIdClick]);

    // Function to render text with interactive elements
    const renderInteractiveText = (text: string) => {
        if (!text || clickables.length === 0 || !clickablesRegex) {
            return text;
        }

        const parts = text.split(clickablesRegex);

        return parts.map((part, i) => {
            if (!part) return null;
            const lowerPart = part.toLowerCase();
            const clickable = clickables.find(c => c.key === lowerPart);
            if (clickable) {
                const baseClass =
                    'inline font-medium transition-colors hover:underline focus-visible:underline focus-visible:outline-none';

                if (clickable.type === 'external') {
                    return (
                        <a
                            key={i}
                            href={clickable.href}
                            onClick={event => {
                                event.preventDefault();
                                clickable.handler();
                            }}
                            target="_blank"
                            rel="noopener noreferrer"
                            data-interactive-token="true"
                            className={`${baseClass} text-amber-400 hover:text-amber-300 focus-visible:text-amber-200`}
                        >
                            {part}
                        </a>
                    );
                }

                return (
                    <button
                        key={i}
                        onClick={clickable.handler}
                        type="button"
                        data-interactive-token="true"
                        className={`${baseClass} ${
                            clickable.type === 'ref'
                                ? 'text-blue-400 hover:text-blue-300 focus-visible:text-blue-200'
                                : 'text-green-400 hover:text-green-300 focus-visible:text-green-200'
                        }`}
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
                if (child.type === 'button' && (child.props as any)['data-interactive-token']) {
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
        const indentation = normalizeIndentation(children);
        const processedChildren = indentation.consumed ? indentation.children : children;
        const textContent = Children.toArray(processedChildren).join('');

        let markerIndentClass = '';
        if (!indentation.consumed) {
            if (/^\s*\(\d+\)/.test(textContent)) markerIndentClass = 'pl-6'; // (1)
            if (/^\s*\([a-z]\)/.test(textContent)) markerIndentClass = 'pl-12'; // (a)
            if (/^\s*\([ivx]+\)/.test(textContent)) markerIndentClass = 'pl-[4.5rem]'; // (i)
        }

        const classNames = ['mb-2'];
        if (indentation.className) classNames.push(indentation.className);
        if (markerIndentClass) classNames.push(markerIndentClass);

        return (
            <p className={classNames.join(' ')} style={indentation.style}>
                {processChildren(processedChildren)}
            </p>
        );
    };

    // Apply processing to list items and table cells as well
    const CustomListItem = ({children}: { children: React.ReactNode }) => {
        const indentation = normalizeIndentation(children);
        const processedChildren = indentation.consumed ? indentation.children : children;
        const className = indentation.className ? indentation.className : undefined;

        return (
            <li className={className} style={indentation.style}>
                {processChildren(processedChildren)}
            </li>
        );
    };
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