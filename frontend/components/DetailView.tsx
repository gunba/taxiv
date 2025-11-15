import React from 'react';
import type {DetailViewContent} from '../types';
import InteractiveContent from './InteractiveContent';

interface DetailViewProps {
    content: DetailViewContent | null;
    onTermClick: (definitionInternalId: string, termText: string) => void;
    onReferenceClick: (internalId: string) => void;
    onReferenceByRefIdClick: (refId: string) => void;
    onSetMainView: (nodeId: string) => void;
}

const DetailView: React.FC<DetailViewProps> = ({
                                                   content,
                                                   onTermClick,
                                                   onReferenceClick,
                                                   onReferenceByRefIdClick,
                                                   onSetMainView,
                                               }) => {
    if (!content) {
        return (
            <div className="h-full flex items-center justify-center text-gray-400 text-center px-6">
                <p>Select a reference, definition, or link in the main content to view details here.</p>
            </div>
        );
    }

    if (content.type === 'error') {
        return (
            <div className="h-full flex items-center justify-center px-6">
                <div className="bg-gray-900 border border-red-700 text-red-300 rounded-lg p-6 text-sm leading-relaxed">
                    {content.data}
                </div>
            </div>
        );
    }

    const {data} = content;
    const isTermView = content.type === 'term';

    return (
        <div className="flex flex-col h-full text-gray-200">
            <header className="border-b border-gray-700 px-4 py-3">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-gray-400">
                            {isTermView ? 'Defined Term' : 'Provision Detail'}
                        </p>
                        <h2 className="text-lg font-semibold text-gray-100">{data.title}</h2>
                        <p className="text-sm text-gray-400">{data.ref_id}</p>
                        {isTermView && (
                            <p className="text-sm text-green-400 mt-1">Definition for “{content.termText}”</p>
                        )}
                    </div>
                    <button
                        onClick={() => onSetMainView(data.internal_id)}
                        className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-3 py-1.5 rounded-md"
                    >
                        Open in Main View
                    </button>
                </div>
            </header>

            <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6 scrollbar-stable">
                <section>
                    <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-2">Content</h3>
                    {data.content_md ? (
                        <InteractiveContent
                            node={data}
                            onTermClick={onTermClick}
                            onReferenceByRefIdClick={onReferenceByRefIdClick}
                        />
                    ) : (
                        <p className="text-sm text-gray-400">No content available.</p>
                    )}
                </section>

                <section>
                    <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-2">References</h3>
                    {data.references_to.length > 0 ? (
                        <ul className="space-y-2">
                            {data.references_to.map(reference => (
                                <li key={`${reference.target_ref_id}-${reference.snippet ?? 'snippet'}`}
                                    className="bg-gray-900 border border-gray-700 rounded-md p-3">
                                    <p className="text-sm text-gray-200">
                                        {reference.target_title ?? 'Referenced provision'}
                                    </p>
                                    <p className="text-xs text-gray-400 mt-1">{reference.target_ref_id}</p>
                                    {reference.snippet && (
                                        <p className="text-xs text-gray-400 mt-2">“…{reference.snippet}…”</p>
                                    )}
                                    <div className="mt-3 flex gap-2">
                                        <button
                                            onClick={() => onReferenceByRefIdClick(reference.target_ref_id)}
                                            className="text-xs font-medium text-blue-300 hover:text-blue-200"
                                        >
                                            View referenced provision
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-sm text-gray-400">No outbound references.</p>
                    )}
                </section>

                <section>
                    <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-2">Referenced By</h3>
                    {data.referenced_by.length > 0 ? (
                        <ul className="space-y-2">
                            {data.referenced_by.map(item => (
                                <li key={item.source_internal_id}
                                    className="bg-gray-900 border border-gray-700 rounded-md p-3">
                                    <p className="text-sm text-gray-200">{item.source_title}</p>
                                    <p className="text-xs text-gray-400 mt-1">{item.source_ref_id}</p>
                                    <div className="mt-3 flex gap-2">
                                        <button
                                            onClick={() => onReferenceClick(item.source_internal_id)}
                                            className="text-xs font-medium text-blue-300 hover:text-blue-200"
                                        >
                                            View detail
                                        </button>
                                        <button
                                            onClick={() => onSetMainView(item.source_internal_id)}
                                            className="text-xs font-medium text-gray-300 hover:text-gray-100"
                                        >
                                            Open in main view
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-sm text-gray-400">No inbound references.</p>
                    )}
                </section>

                <section>
                    <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide mb-2">Defined Terms</h3>
                    {data.defined_terms_used.length > 0 ? (
                        <ul className="space-y-2">
                            {data.defined_terms_used.map(term => (
                                <li key={`${term.term_text}-${term.definition_internal_id ?? 'unknown'}`}
                                    className="bg-gray-900 border border-gray-700 rounded-md p-3">
                                    <p className="text-sm text-gray-200">{term.term_text}</p>
                                    <div className="mt-2 flex gap-2">
                                        {term.definition_internal_id ? (
                                            <button
                                                onClick={() => onTermClick(term.definition_internal_id!, term.term_text)}
                                                className="text-xs font-medium text-green-300 hover:text-green-200"
                                            >
                                                View definition
                                            </button>
                                        ) : (
                                            <span className="text-xs text-gray-400">Definition not available.</span>
                                        )}
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-sm text-gray-400">No defined terms.</p>
                    )}
                </section>
            </div>
        </div>
    );
};

export default DetailView;
