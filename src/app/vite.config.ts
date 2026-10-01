import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { cspPlugin } from './csp.ts'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react(), cspPlugin()],
})
