// Run the Lab 01 analyses (sdr-lab/lab-01/lab01-analysis.js) on the I/Q excerpts in Node
// and write sdr-lab/lab-01/results.json, which the lab page shows before anyone presses
// "Recompute". The browser runs exactly the same code on the same files.
//
//   node tools/precompute_lab01.mjs
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const lab = join(here, '..', 'sdr-lab', 'lab-01');
const D = require('../assets/js/sdr-dsp.js');
const Lab01 = require('../sdr-lab/lab-01/lab01-analysis.js');

const manifest = JSON.parse(readFileSync(join(lab, 'data', 'manifest.json'), 'utf8'));
const load = async (rec) => {
  const b = readFileSync(join(lab, rec.data));
  return D.decodeCs16(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), rec.scale);
};

const t0 = Date.now();
const results = await Lab01.run(manifest, load, (p, msg) => process.stdout.write(`\r${(100 * p).toFixed(0).padStart(3)}%  ${msg.padEnd(60)}`));
writeFileSync(join(lab, 'results.json'), JSON.stringify(results));
console.log(`\nwrote results.json in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
