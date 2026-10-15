import { cpSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
// PDF.js auxiliary data stays local and uses the installed library's exact version.
for (const directory of ['cmaps', 'standard_fonts', 'wasm']) {
  const target = new URL(`../public/pdfjs/${directory}`, import.meta.url)
  mkdirSync(fileURLToPath(target), { recursive: true })
  cpSync(new URL(`../node_modules/pdfjs-dist/${directory}`, import.meta.url), target, { recursive: true })
}
