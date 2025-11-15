import React, {
    createContext,
    type ReactNode,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from 'react';

type ToastVariant = 'success' | 'error' | 'info';

interface Toast {
    id: number;
    title: string;
    description?: string;
    variant: ToastVariant;
}

interface ToastContextValue {
    showToast: (options: {
        title: string;
        description?: string;
        variant?: ToastVariant;
        durationMs?: number;
    }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastCounter = 0;

const variantClasses: Record<ToastVariant, string> = {
    success: 'bg-green-600 border-green-400 text-white',
    error: 'bg-red-600 border-red-400 text-white',
    info: 'bg-gray-800 border-gray-600 text-white',
};

export const ToastProvider: React.FC<{ children: ReactNode }> = ({children}) => {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const timeoutMapRef = useRef<Map<number, number>>(new Map());

    const dismissToast = useCallback((id: number) => {
        const timeoutId = timeoutMapRef.current.get(id);
        if (timeoutId) {
            window.clearTimeout(timeoutId);
            timeoutMapRef.current.delete(id);
        }
        setToasts(prev => prev.filter(toast => toast.id !== id));
    }, []);

    const showToast = useCallback<ToastContextValue['showToast']>(
        ({title, description, variant = 'info', durationMs = 4000}) => {
            const id = ++toastCounter;
            setToasts(prev => [...prev, {id, title, description, variant}]);
            const timeoutId = window.setTimeout(() => dismissToast(id), durationMs);
            timeoutMapRef.current.set(id, timeoutId);
        },
        [dismissToast],
    );

    useEffect(() => {
        return () => {
            timeoutMapRef.current.forEach(timeoutId => window.clearTimeout(timeoutId));
            timeoutMapRef.current.clear();
        };
    }, []);

    const contextValue = useMemo(() => ({showToast}), [showToast]);

    return (
        <ToastContext.Provider value={contextValue}>
            {children}
            <div className="fixed inset-x-0 top-4 z-50 flex flex-col items-center space-y-2 px-4 pointer-events-none">
                {toasts.map(toast => (
                    <div
                        key={toast.id}
                        className={`pointer-events-auto w-full max-w-sm rounded-lg border shadow-lg p-4 flex gap-3 ${variantClasses[toast.variant]}`}
                    >
                        <div className="flex-1">
                            <p className="text-sm font-semibold">{toast.title}</p>
                            {toast.description && (
                                <p className="mt-1 text-sm text-gray-100">{toast.description}</p>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={() => dismissToast(toast.id)}
                            className="text-sm font-semibold text-white/80 hover:text-white focus:outline-none"
                            aria-label="Dismiss notification"
                        >
                            ×
                        </button>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
};

export const useToast = (): ToastContextValue => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};
