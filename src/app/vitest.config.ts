import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// vitest's `test` key isn't type-safe on plain `vite`'s `defineConfig` (and this
// repo has two `vite` versions installed — the root `vite` and the one bundled
// under `vitest`'s own node_modules — so importing `defineConfig` from
// 'vitest/config' directly in vite.config.ts causes a worse Plugin/UserConfig
// type conflict). Keeping the test config in its own file, merged onto the base
// vite config, avoids both problems while still picking up `plugins`/`base`.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }),
)
