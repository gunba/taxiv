import {api} from './api';

export type ExportMarkdownStatus = 'success' | 'clipboard-fallback' | 'cancelled' | 'error';

export interface ExportMarkdownCallbacks {
    onStart?: () => void;
    onSuccess?: (markdown: string) => void;
    onError?: (error: Error) => void;
    onCancel?: () => void;
    onClipboardFallback?: (markdown: string) => void;
}

export interface ExportMarkdownOptions extends ExportMarkdownCallbacks {
    internalId: string;
    includeDescendants?: boolean;
    signal?: AbortSignal;
}

export interface ExportMarkdownResult {
    status: ExportMarkdownStatus;
    markdown?: string;
    error?: Error;
}

const normalizeError = (error: unknown, fallbackMessage: string): Error => {
    if (error instanceof Error) {
        return error;
    }
    return new Error(fallbackMessage);
};

export const exportMarkdownToClipboard = async ({
                                                    internalId,
                                                    includeDescendants = false,
                                                    signal,
                                                    onStart,
                                                    onSuccess,
                                                    onError,
                                                    onCancel,
                                                    onClipboardFallback,
                                                }: ExportMarkdownOptions): Promise<ExportMarkdownResult> => {
    if (signal?.aborted) {
        onCancel?.();
        return {status: 'cancelled'};
    }

    let aborted = false;
    const onAbort = () => {
        aborted = true;
    };
    signal?.addEventListener('abort', onAbort, {once: true});

    const cleanup = () => {
        if (signal) {
            signal.removeEventListener('abort', onAbort);
        }
    };

    onStart?.();

    try {
        const markdown = await api.exportMarkdown({
            internalId,
            includeDescendants,
            signal,
        });

        if (aborted || signal?.aborted) {
            onCancel?.();
            return {status: 'cancelled'};
        }

        try {
            if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
                throw new Error('Clipboard API is unavailable');
            }

            await navigator.clipboard.writeText(markdown);
            onSuccess?.(markdown);
            return {status: 'success', markdown};
        } catch (clipboardError) {
            const normalized = normalizeError(clipboardError, 'Failed to copy markdown to the clipboard.');
            onClipboardFallback?.(markdown);
            const wrappedError = new Error(`Clipboard copy failed: ${normalized.message}`);
            onError?.(wrappedError);
            return {
                status: 'clipboard-fallback',
                markdown,
                error: wrappedError,
            };
        }
    } catch (error) {
        if (aborted || signal?.aborted) {
            onCancel?.();
            return {status: 'cancelled'};
        }

        const normalized = normalizeError(error, 'Failed to export markdown.');
        onError?.(normalized);
        return {
            status: 'error',
            error: normalized,
        };
    } finally {
        cleanup();
    }
};
