import path from 'path';
import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
	plugins: [react()],
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'frontend'),
		},
	},
	test: {
		environment: 'jsdom',
		setupFiles: ['tests/frontend/setupTests.ts'],
		include: ['tests/frontend/**/*.test.{ts,tsx}'],
		pool: 'threads', // Avoid fork worker crashes on Node 20+/25 sandbox hosts
	},
});
