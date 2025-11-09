// vite.config.ts
import path from 'path';
import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => ({
    server: {
        port: 3000,
        host: '0.0.0.0',
        allowedHosts: ['raja-block.bnr.la'],
        // NEW: Proxy configuration
        proxy: {
            // Proxy requests starting with /api
            '/api': {
                // 'backend' is the service name defined in docker-compose.yml
                target: 'http://backend:8000',
                changeOrigin: true,
                secure: false,
                // The backend expects the /api prefix.
            },
            // Serve ingestion assets directly from FastAPI
            '/media': {
                target: 'http://backend:8000',
                changeOrigin: true,
                secure: false,
            }
        }
    },
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, '.'),
        }
    }
}));
