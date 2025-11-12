import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, '.'),
        },
    },
	test: {
		environment: 'jsdom',
		setupFiles: ['tests/setupTests.ts'],
		pool: 'threads', // Avoid fork worker crashes on Node 20+/25 sandbox hosts
	},
});
