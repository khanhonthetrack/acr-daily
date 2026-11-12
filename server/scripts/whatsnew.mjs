// The GitHub Release's "What's new" for one app version, from src/changelog.js (the release workflow runs it).
//   node server/scripts/whatsnew.mjs 0.0.31 [whatsnew.md]   (to that file as UTF-8, else to the output)
// No entry for that version: says what to do and exits 1, so the release stops before anything is built.
import { writeFileSync } from 'node:fs';
import { releaseNotes } from '../src/changelog.js';

const [version, out] = process.argv.slice(2);
const notes = version && releaseNotes(version);
if (!notes) {
  console.error(`No changelog entry for ${version || '(no version given)'}: add one at the top of server/src/changelog.js ` +
    '(what drivers will notice, in plain words) in the commit that sets the version, then release again.');
  process.exit(1);
}
if (out) writeFileSync(out, notes, 'utf8'); else process.stdout.write(notes);
