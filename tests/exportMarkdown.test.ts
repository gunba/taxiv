import {beforeEach, afterAll, describe, expect, it, vi} from 'vitest';
import {exportMarkdownToClipboard} from '../utils/exportMarkdown';

const originalFetch = global.fetch;
const originalClipboard = Object.getOwnPropertyDescriptor(window.navigator, 'clipboard');

const createResponse = (overrides: Partial<Response> & {json?: () => Promise<unknown>; text?: () => Promise<string>}) => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => ({}),
    text: async () => '',
    ...overrides,
}) as Response;

beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn();
    Object.defineProperty(window.navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: vi.fn(),
        },
    });
});

afterAll(() => {
    if (originalClipboard) {
        Object.defineProperty(window.navigator, 'clipboard', originalClipboard);
    } else {
        delete (window.navigator as unknown as {clipboard?: unknown}).clipboard;
    }
    global.fetch = originalFetch;
});

const getClipboardMock = () => (window.navigator.clipboard as {writeText: ReturnType<typeof vi.fn>}).writeText;

describe('exportMarkdownToClipboard', () => {
    it('copies markdown to the clipboard and reports success', async () => {
        const markdown = '# Exported';
        (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
            createResponse({json: async () => ({markdown})}),
        );

        const onStart = vi.fn();
        const onSuccess = vi.fn();
        const result = await exportMarkdownToClipboard({
            internalId: 'abc',
            onStart,
            onSuccess,
        });

        expect(onStart).toHaveBeenCalledTimes(1);
        expect(onSuccess).toHaveBeenCalledWith(markdown);
        expect(getClipboardMock()).toHaveBeenCalledWith(markdown);
        expect(result).toEqual({status: 'success', markdown});
    });

    it('provides fallback messaging when clipboard write fails', async () => {
        const markdown = 'content';
        (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
            createResponse({json: async () => ({markdown})}),
        );

        const clipboardError = new Error('denied');
        getClipboardMock().mockRejectedValue(clipboardError);

        const onClipboardFallback = vi.fn();
        const onError = vi.fn();
        const result = await exportMarkdownToClipboard({
            internalId: 'abc',
            onClipboardFallback,
            onError,
        });

        expect(onClipboardFallback).toHaveBeenCalledWith(markdown);
        expect(onError).toHaveBeenCalled();
        expect(result.status).toBe('clipboard-fallback');
        expect(result.markdown).toBe(markdown);
        expect(result.error).toBeInstanceOf(Error);
    });

    it('notifies callers when the API request fails', async () => {
        (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
            createResponse({
                ok: false,
                status: 500,
                statusText: 'Server Error',
                text: async () => 'boom',
            }),
        );

        const onError = vi.fn();
        const result = await exportMarkdownToClipboard({
            internalId: 'abc',
            onError,
        });

        expect(onError).toHaveBeenCalled();
        expect(result.status).toBe('error');
        expect(result.error).toBeInstanceOf(Error);
    });

    it('aborts without calling the API if the request is cancelled early', async () => {
        const controller = new AbortController();
        controller.abort();

        const onCancel = vi.fn();
        const result = await exportMarkdownToClipboard({
            internalId: 'abc',
            signal: controller.signal,
            onCancel,
        });

        expect(global.fetch).not.toHaveBeenCalled();
        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(result).toEqual({status: 'cancelled'});
    });
});
