import importlib.util, sys
spec = importlib.util.spec_from_file_location('r2', 'scripts/repair2-ts-errors.py')
mod = importlib.util.module_from_spec(spec)
sys.modules['r2'] = mod
spec.loader.exec_module(mod)
norm = mod.normalize_ts_imports

cases = [
    # extension-bearing auto-import (the real on-disk case) -> ../dep/dep.ts
    ("import { StateStore } from './state-store.ts';\nexport const x = 1;",
     "import { StateStore } from '../state-store/state-store.ts';\nexport const x = 1;"),
    # extensionless AI import -> ../dep/dep.ts
    ("import { Palette, main } from './palette-store';\nexport const x = 1;",
     "import { Palette, main } from '../palette-store/palette-store.ts';\nexport const x = 1;"),
    # index.ts multi-segment -> untouched (merged named import re-emitted first; order is cosmetic)
    ("import './src/state-store/state-store.ts';\nimport { StateStore } from './src/state-store/state-store.ts';\nexport { StateStore };",
     "import { StateStore } from './src/state-store/state-store.ts';\nimport './src/state-store/state-store.ts';\nexport { StateStore };"),
    # self-declared symbol dropped from import
    ("import { main } from './palette-store';\nexport default function main() {}\n",
     "export default function main() {}\n"),
    # ALREADY-BROKEN form (from earlier clean pass): dir kept the extension
    ("import { StateStore } from '../state-store.ts/state-store.ts';\nexport const x = 1;",
     "import { StateStore } from '../state-store/state-store.ts';\nexport const x = 1;"),
    # correct ../dep/dep.ts form -> untouched
    ("import { StateStore } from '../state-store/state-store.ts';\nexport const x = 1;",
     "import { StateStore } from '../state-store/state-store.ts';\nexport const x = 1;"),
]
ok = True
for i, (src, want) in enumerate(cases):
    got = norm(src)
    status = 'OK' if got == want else 'FAIL'
    if got != want:
        ok = False
    print(f'CASE {i+1}: {status}')
    if got != want:
        print('  WANT:', repr(want))
        print('  GOT: ', repr(got))
print('ALL PASS' if ok else 'SOME FAILED')
