import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//
// GitHub Pages serves a project site under /<repo>/, not /: everything else
// (local `npm run dev`, `npm run build`) must keep base "/", so the GH Pages
// deploy workflow is the only caller that passes `--mode gh-pages`.
export default defineConfig(({ mode }) => ({
  base: mode === 'gh-pages' ? '/WealthGuard/' : '/',
  plugins: [react()],
}))
