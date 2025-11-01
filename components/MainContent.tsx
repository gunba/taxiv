// components/MainContent.tsx
import React, { useMemo, useEffect } from 'react';
import { TaxDataObject } from '../types';

interface MainContentProps {
  node: TaxDataObject | null;
  isLoading: boolean;
  // We pass internal IDs directly for interaction
  onReferenceClick: (internalId: string) => void;
  onTermClick: (definitionInternalId: string) => void;
  onSelectNode: (nodeId: string) => void;
}

const MainContent: React.FC<MainContentProps> = ({ node, isLoading, onReferenceClick, onTermClick, onSelectNode }) => {

  // Scroll to top when the node changes
  useEffect(() => {
    const mainElement = document.querySelector('main');
    if (mainElement) {
      mainElement.scrollTo(0, 0);
    }
  }, [node]);

  // Process content to make defined terms clickable (using regex replacement)
  const processedContent = useMemo(() => {
    if (!node || !node.content_md) return "";

    let content = node.content_md;
    const terms = node.defined_terms_used;

    if (terms.length === 0) return content;

    // Create a map for quick lookup: term text (lowercase) -> definition internal ID
    const termMap = new Map<string, string | null>();
    terms.forEach(t => termMap.set(t.term_text.toLowerCase(), t.definition_internal_id));

    // Regex to find asterisked terms. Must match the pattern used during ingestion.
    const regex = /(?:^|[\s\(])\*(?<term>[a-zA-Z0-9\s\-\(\)]+?)(?=[\s,.;:)]|$)/g;

    // Replacement function
    content = content.replace(regex, (match) => {
      // Determine the prefix (if any) and the actual term text
      const prefix = match.startsWith('*') ? '' : match[0];
      const actualTermText = match.substring(prefix.length + 1);

      const normalizedTerm = actualTermText.trim().toLowerCase();

      // Check if this term instance is defined and has an internal ID
      if (termMap.has(normalizedTerm)) {
        const definitionId = termMap.get(normalizedTerm);
        if (definitionId) {
          // Create a clickable span using a custom data attribute for event delegation
          // The CSS for .defined-term is in index.html
          return `${prefix}<span class="defined-term" data-definition-id="${definitionId}">*${actualTermText}</span>`;
        }
      }
      // If not defined or no ID, return the original match
      return match;
    });

    return content;
  }, [node]);


  const handleContentClick = (event: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
    const target = event.target as HTMLElement;

    // Handle clicks on defined terms (event delegation)
    if (target.classList.contains('defined-term') && target.dataset.definitionId) {
      event.preventDefault();
      onTermClick(target.dataset.definitionId);
    }
  };


  if (isLoading) {
    return <div className="p-8 text-center text-gray-400">Loading provision details...</div>;
  }

  if (!node) {
    return <div className="p-8 text-center text-gray-400">Select a provision from the side navigation.</div>;
  }

  return (
    <article className="p-8 max-w-4xl mx-auto">

    <header className="mb-6">
    <h1 className="text-3xl font-bold text-gray-100 mb-2">{node.title}</h1>
    {node.ref_id && (
      <p className="text-sm text-gray-500">{node.ref_id} ({node.type})</p>
    )}
    </header>

    {/* Render the processed content as HTML (required for the interactive spans) */}
    <div className="prose prose-invert max-w-none mb-8" onClick={handleContentClick} dangerouslySetInnerHTML={{ __html: processedContent }} />

    {/* Display References (Updated structure) */}
    {node.references_to.length > 0 && (
      <section className="mt-8 pt-6 border-t border-gray-700">
      <h2 className="text-xl font-semibold text-gray-100 mb-4">References To ({node.references_to.length})</h2>
      <ul className="space-y-3">
      {node.references_to.map((ref, index) => (
        <li key={index} className="text-sm bg-gray-800 p-3 rounded">
        {/* Interaction is complex here as we don't have the target internal_id, only the ref_id.
          We display the info; actual navigation requires lookup which is better handled in DetailView if needed. */}
          <span className="font-medium text-blue-400">
          {ref.target_ref_id}
          </span>
          <span className="text-gray-400 ml-2">({ref.target_title || "External/Missing Reference"})</span>
          {ref.snippet && (
            <p className="text-gray-500 mt-1 italic">Context: "{ref.snippet}"</p>
          )}
          </li>
      ))}
      </ul>
      </section>
    )}
    </article>
  );
};

export default MainContent;
