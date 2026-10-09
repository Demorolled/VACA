// Loader probe for the scaffolded bible-reference curriculum.
// Run with: npx tsx /tmp/bible-probe.ts  (needs real file — tsx -e lacks import.meta.dirname)
import { getLibraryFileList, getBibleContext, getLibraryContextForNodeType, getCompleteLibrary } from '../ai/libraryContext.js';
const list = getLibraryFileList();
const bible = list.filter(f => f.source === 'bible');
console.log('bible entries:', bible.length);
console.log('first 5:', bible.slice(0, 5).map(b => b.name + ' | topics: ' + b.topics.slice(0, 2).join(',')));
console.log('master-index listed:', bible.some(b => b.name.includes('MASTER-INDEX')));
const ctx = getBibleContext('kubernetes deployment and container orchestration');
console.log('\nbible context chars:', ctx.length);
console.log(ctx.split('\n').slice(0, 10).join('\n'));
const nodeCtx = getLibraryContextForNodeType('logic', 'python');
console.log('\nnode-type context chars:', nodeCtx.length);
console.log('has bible section:', nodeCtx.includes('📜'));
const complete = getCompleteLibrary();
console.log('\ncomplete library chars:', complete.length);
console.log('mentions bible levels loaded:', complete.split('\n').find(l => l.includes('Bible levels loaded')));
