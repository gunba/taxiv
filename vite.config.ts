// vite.config.ts
import path from 'path';
import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({mode}) => {
    const env = loadEnv(mode, '.', '');
    return {
        server: {
            port: 3000,
            host: '0.0.0.0',
            // NEW: Proxy configuration
            proxy: {
                // Proxy requests starting with /api
                '/api': {
                    // 'backend' is the service name defined in docker-compose.yml
                    target: 'http://backend:8000',
                    changeOrigin: true,
                    secure: false,
                    // The backend expects the /api prefix.
                }
            }
        },
        plugins: [react()],
        define: {
            'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
            'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
        },
        resolve: {
            alias: {
                '@': path.resolve(__dirname, '.'),
            }
        }
    };
});
