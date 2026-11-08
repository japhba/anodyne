import {build} from 'esbuild';
import {copyFile, mkdir, readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
await mkdir(new URL('../assets/vendor/', import.meta.url), {recursive: true});
const result = await build({
  absWorkingDir: root,
  entryPoints: ['sources/tex-converter.js'],
  outfile: 'assets/vendor/mathjax-tex-4.1.3.min.js',
  bundle: true,
  minify: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
  legalComments: 'eof',
  metafile: true,
  banner: {js: '/*! MathJax 4.1.3, Apache-2.0; copyright notices in MathJax-NOTICE.txt; license in MathJax-LICENSE.txt. Unicode mapping data: Copyright 1991-2026 Unicode, Inc.; Unicode-LICENSE.txt. TeX input only. */'},
});
await copyFile(new URL('../node_modules/@mathjax/src/LICENSE', import.meta.url),
               new URL('../assets/vendor/MathJax-LICENSE.txt', import.meta.url));
// Published JS modules omit their source headers. Retain the exact copyright
// notices from every bundled MathJax TypeScript source in the distribution.
const notices = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.startsWith('node_modules/@mathjax/src/mjs/')) continue;
  const source = new URL('../' + input.replace('/mjs/', '/ts/').replace(/\.js$/, '.ts'), import.meta.url);
  const text = await readFile(source, 'utf8');
  for (const match of text.matchAll(/^\s*\*\s*(Copyright[^\n]*)/gm)) notices.add(match[1].trim());
}
await writeFile(new URL('../assets/vendor/MathJax-NOTICE.txt', import.meta.url),
  'MathJax 4.1.3 — https://github.com/mathjax/MathJax-src\n\n' +
  Array.from(notices).sort().join('\n') + '\n\n' +
  'Licensed under the Apache License, Version 2.0. See MathJax-LICENSE.txt.\n' +
  'This distribution bundles the base, AMS and boldsymbol TeX input packages and the MathML\n' +
  'serializer. Anodyne adds a bounded TeX-to-MathML wrapper and renders the\n' +
  'result with the browser’s native MathML engine. No MathJax font assets or\n' +
  'HTML/SVG output engines are included.\n');
