import React, {useCallback, useEffect, useRef, useState} from 'react';
import {api, unifiedSearch, type UnifiedSearchItem} from '../utils/api';
import {CloseIcon, ClipboardIcon, SearchIcon} from './Icons';
import {copyToClipboard} from '../utils/clipboard';

interface SemanticSearchModalProps {
	isOpen: boolean;
	onClose: () => void;
	onSelectProvision: (internalId: string) => void;
	state: {
		query: string;
		results: UnifiedSearchItem[];
	};
	onStateChange: (nextState: { query: string; results: UnifiedSearchItem[] }) => void;
}

const SemanticSearchModal: React.FC<SemanticSearchModalProps> = ({isOpen, onClose, onSelectProvision, state, onStateChange}) => {
	const [query, setQuery] = useState(state.query);
	const [results, setResults] = useState<UnifiedSearchItem[]>(state.results);
	const [isLoading, setIsLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [copiedJsonId, setCopiedJsonId] = useState<string | null>(null);
	const [copyingJsonId, setCopyingJsonId] = useState<string | null>(null);
	const [copiedMarkdownId, setCopiedMarkdownId] = useState<string | null>(null);
	const [copyingMarkdownId, setCopyingMarkdownId] = useState<string | null>(null);
	const inputRef = useRef<HTMLInputElement | null>(null);
	const jsonCopyTimeoutRef = useRef<number | null>(null);
	const markdownCopyTimeoutRef = useRef<number | null>(null);

	useEffect(() => {
		if (isOpen) {
			setQuery(state.query);
			setResults(state.results);
			requestAnimationFrame(() => inputRef.current?.focus());
		} else {
			setError(null);
			setIsLoading(false);
			setCopiedJsonId(null);
			setCopyingJsonId(null);
			setCopiedMarkdownId(null);
			setCopyingMarkdownId(null);
		}
	}, [isOpen, state.query, state.results]);

	useEffect(() => {
		if (!isOpen) {
			return;
		}
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') {
				onClose();
			}
		};
		window.addEventListener('keydown', handleKeyDown);
		return () => window.removeEventListener('keydown', handleKeyDown);
	}, [isOpen, onClose]);

	useEffect(() => {
		return () => {
			if (jsonCopyTimeoutRef.current) {
				window.clearTimeout(jsonCopyTimeoutRef.current);
			}
			if (markdownCopyTimeoutRef.current) {
				window.clearTimeout(markdownCopyTimeoutRef.current);
			}
		};
	}, []);

	const runSearch = useCallback(async () => {
		const trimmed = query.trim();
		if (!trimmed) {
			setError('Enter a query to search provisions.');
			setResults([]);
			onStateChange({query: '', results: []});
			return;
		}
		setIsLoading(true);
		setError(null);
		try {
			const response = await unifiedSearch(trimmed, 25);
			const newResults = response.results ?? [];
			setResults(newResults);
			onStateChange({query, results: newResults});
		} catch (err) {
			console.error('Semantic search failed:', err);
			setError('Semantic search failed. Ensure the backend MCP API is reachable.');
			setResults([]);
			onStateChange({query, results: []});
		} finally {
			setIsLoading(false);
		}
	}, [onStateChange, query]);

	const handleSubmit = useCallback(
		(event: React.FormEvent) => {
			event.preventDefault();
			void runSearch();
		},
		[runSearch],
	);

	const handleCopyJson = useCallback(async (result: UnifiedSearchItem) => {
		setCopyingJsonId(result.id);
		setError(null);
		try {
			const detail = await api.getProvisionDetail(result.id);
			await copyToClipboard(JSON.stringify(detail, null, 2));
			setCopiedJsonId(result.id);
			if (jsonCopyTimeoutRef.current) {
				window.clearTimeout(jsonCopyTimeoutRef.current);
			}
			jsonCopyTimeoutRef.current = window.setTimeout(() => setCopiedJsonId(null), 2000);
		} catch (err) {
			console.error('Failed to copy provision detail JSON:', err);
			setError('Unable to copy provision detail JSON. Ensure the backend is reachable and clipboard permissions are granted.');
		} finally {
			setCopyingJsonId(null);
		}
	}, []);

	const handleCopyMarkdown = useCallback(async (result: UnifiedSearchItem) => {
		setCopyingMarkdownId(result.id);
		setError(null);
		try {
			const markdown = await api.getProvisionDetailMarkdown(result.id);
			await copyToClipboard(markdown);
			setCopiedMarkdownId(result.id);
			if (markdownCopyTimeoutRef.current) {
				window.clearTimeout(markdownCopyTimeoutRef.current);
			}
			markdownCopyTimeoutRef.current = window.setTimeout(() => setCopiedMarkdownId(null), 2000);
		} catch (err) {
			console.error('Failed to copy provision detail markdown:', err);
			setError('Unable to copy provision detail markdown. Ensure the backend is reachable and clipboard permissions are granted.');
		} finally {
			setCopyingMarkdownId(null);
		}
	}, []);

	const handleResultSelect = useCallback((result: UnifiedSearchItem) => {
		onSelectProvision(result.id);
		onClose();
	}, [onClose, onSelectProvision]);

	if (!isOpen) {
		return null;
	}

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={onClose}>
			<div
				className="w-full max-w-3xl rounded-xl bg-gray-900 border border-gray-700 shadow-2xl text-gray-100"
				role="dialog"
				aria-modal="true"
				onClick={event => event.stopPropagation()}
			>
			<header className="flex items-center justify-between border-b border-gray-700 px-6 py-4">
					<div>
						<p className="text-sm uppercase tracking-wide text-gray-400">Semantic search</p>
						<h2 className="text-xl font-semibold text-white">Explore the act with semantic search</h2>
					</div>
					<button
						type="button"
						onClick={onClose}
						className="p-2 rounded-full hover:bg-gray-800 text-gray-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
						aria-label="Close semantic search"
					>
						<CloseIcon className="w-5 h-5"/>
					</button>
				</header>

				<form onSubmit={handleSubmit} className="px-6 py-4 border-b border-gray-800 space-y-3">
					<label className="text-sm text-gray-300 font-medium" htmlFor="semantic-search-input">
						Query
					</label>
					<div className="relative">
						<input
							id="semantic-search-input"
							ref={inputRef}
							type="text"
							value={query}
							onChange={event => {
								const value = event.target.value;
								setQuery(value);
								onStateChange({query: value, results});
							}}
							placeholder='e.g. "s 6-5 active asset"'
							className="w-full bg-gray-800 border border-gray-600 rounded-md py-3 pl-11 pr-4 focus:ring-2 focus:ring-blue-500 focus:outline-none text-white"
						/>
						<SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" aria-hidden="true"/>
					</div>
					<div className="flex items-center justify-between">
					<p className="text-xs text-gray-400">
						Headers + snippets: click a row to load it in the main view, or copy MCP JSON / markdown payloads.
					</p>
						<button
							type="submit"
							className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-400 focus-visible:ring-offset-gray-900"
						>
							{isLoading ? 'Searching…' : 'Search'}
						</button>
					</div>
				</form>

				<div className="max-h-[60vh] overflow-y-auto px-6 py-4 space-y-4 scrollbar-stable">
					{error && <div className="text-sm text-red-400">{error}</div>}
				{!error && results.length === 0 && !isLoading && (
					<p className="text-sm text-gray-400">Enter a query to see semantic results.</p>
				)}
					{isLoading && <p className="text-sm text-gray-400">Running semantic search…</p>}
					{results.map(result => (
						<div key={result.id} className="rounded-lg border border-gray-700 bg-gray-800 p-4 space-y-3">
					<button
						type="button"
						onClick={() => handleResultSelect(result)}
						className="text-left w-full space-y-2"
					>
						<div>
							<p className="text-lg font-semibold text-white">{result.title || 'Untitled provision'}</p>
							<p className="text-sm text-gray-300 mt-1">{result.ref_id}</p>
							<p className="text-xs text-gray-400 mt-1">
								Type: {result.type} • URS {result.score_urs}
							</p>
						</div>
						<p className="text-sm text-gray-400">{result.content_snippet}</p>
					</button>
						<div className="flex flex-wrap items-center justify-end gap-2">
							<button
								type="button"
								onClick={() => handleCopyJson(result)}
								disabled={copyingJsonId === result.id}
								className={`inline-flex items-center gap-2 rounded-md border border-gray-600 px-3 py-1.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${copyingJsonId === result.id ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-800'}`}
							>
								<ClipboardIcon className="w-3.5 h-3.5"/>
								{copyingJsonId === result.id ? 'Copying…' : copiedJsonId === result.id ? 'Copied!' : 'Copy MCP JSON'}
							</button>
							<button
								type="button"
								onClick={() => handleCopyMarkdown(result)}
								disabled={copyingMarkdownId === result.id}
								className={`inline-flex items-center gap-2 rounded-md border border-gray-600 px-3 py-1.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${copyingMarkdownId === result.id ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-800'}`}
							>
								<ClipboardIcon className="w-3.5 h-3.5"/>
								{copyingMarkdownId === result.id ? 'Copying…' : copiedMarkdownId === result.id ? 'Copied!' : 'Copy MCP MD'}
							</button>
						</div>
						</div>
					))}
				</div>
			</div>
		</div>
	);
};

export default SemanticSearchModal;
