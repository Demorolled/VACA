# 04-Web — App Merging Guide (Merge Two Generated Apps)

> Deep technical guide — part of the 42-level Programming Bible curriculum.
> Level: 04 — Web. Topic: merging two existing applications into one codebase.
> VACA feature: merge-apps (wiki section 38, VACA-MASTER Part N).

---

## Overview

Merging two applications — one already built, one being built or just finished —
is a code-integration task, not a code-generation task. The result must be a
single runnable app that preserves both source apps' behavior, without name
collisions, lost dependencies, or broken entry points. This guide gives the
merge strategy to apply whenever a user asks VACA (or any builder) to combine
two projects.

## When to use this guide

Use when the user request matches any of these intents:

- "Merge these two apps together"
- "Combine project A and project B into one"
- "Add the feature/module from one app into another"
- "Import a project into the current one"

## Merge algorithm

```
1. LOAD      Read both projects: node graphs (nodes, edges, metadata)
             + generated file trees + package/config manifests.
2. DETECT    Find conflicts:
             • duplicate node ids
             • same node labels / module names
             • colliding file names (src/main.ts in both)
             • shared dependencies with conflicting versions
3. RESOLVE   Fix conflicts:
             • re-id colliding nodes (deterministic prefix per source)
             • namespace or rename modules (e.g. src/ → src/app-a/, app-b/)
             • unify entry points (single main/index)
             • merge package manifests (union of deps, keep newer version,
               record conflicts that need a human decision)
4. INTEGRATE Wire cross-app edges (e.g. app B's API nodes into app A's UI),
             merge asset folders, combine config files, de-duplicate shared
             vendor code.
5. VALIDATE  Regenerate/merge code, run typecheck + unit tests on the merged
             output, report a diff summary of what changed.
```

## Rules

- **Never hand-write a toy example.** A response like "app1.py imports app2.py"
  does not merge two real apps — it demonstrates nothing about the actual
  projects. Describe/perform the real merge flow on the actual projects.
- **Preserve behavior.** Do not silently drop nodes, edges, or files from
  either source. Every removed item must be reported.
- **Deterministic conflict resolution.** Collisions must resolve the same way
  every run (prefix by source project, then ask when ambiguous).
- **Verify on disk.** The chat model has no file access — a claimed "I wrote
  it" or a printed file tree is not a write. Always verify against the real
  filesystem.

## Anti-patterns

| Anti-pattern | Why it fails |
|--------------|--------------|
| Toy `app1.py`/`app2.py` import demo | Doesn't touch real graphs, files, or deps |
| Overwrite one app with the other | Loses behavior silently |
| Merge files only, ignore the node graph | Canvas no longer matches the code |
| Ignore dependency version conflicts | Runtime breakage after merge |
| Claiming a wiki/file write from chat output | Hallucination — no write occurred |

## Related

- `01-folder-drop-content-description.md` — reading app source material in
- `data/library/14-web-application-architecture.md` — architecture patterns
- `data/library/03-code-generation-rules.md` — code quality rules for the
  merged output
- VACA wiki section 38 + `VACA-MASTER-KNOWLEDGE.md` Part N — feature record
