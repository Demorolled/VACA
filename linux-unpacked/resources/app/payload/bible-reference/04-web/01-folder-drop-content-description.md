# 04 — Web — Deep Technical Guide: Folder Drop & Content Description

> A comprehensive technical guide for reading dropped files/folders in the
> browser and describing folder contents with an LLM. Part of the 42-level
> Programming Bible. Consumed by the VACA app builder's library-context
> injector when a request maps to the web/browser/frontend domain.

## Overview

A web app can read the **contents** of files and folders the user drags onto
it — but never an OS path handle. The correct, standards-track approach is
the DataTransfer item's `webkitGetAsEntry()` → `FileSystemEntry` traversal:
recursively walk `FileSystemDirectoryEntry` via `createReader()`, read each
`FileSystemFileEntry` with `.file()`, and read text via `FileReader` /
`.text()`. Never invent APIs (e.g. `webkitGet2DData()` / `webkitGet2DFile()`
do not exist — that is a hallucinated pattern to avoid).

## Core Topics

- **drag & drop** — `dataTransfer.items`, `webkitGetAsEntry()`
- **folder traversal** — `FileSystemDirectoryEntry.createReader()`, recursion
- **file content capture** — `FileSystemFileEntry.file()` → `.text()`
- **folder manifest** — root detection, extension histogram, size, samples
- **LLM description** — prompt-built manifest → plain-text summary

## Key Patterns

```typescript
// Canonical drop handler — folder + file aware
function readFiles(items: DataTransferItemList): Promise<DroppedFile[]> {
  const results: DroppedFile[] = [];
  const queue: FileSystemEntry[] = [];

  for (const item of items) {
    const entry = item.webkitGetAsEntry?.();
    if (entry) queue.push(entry);
    else if (item.getAsFile()) results.push(fileToDropped(item.getAsFile()!));
  }

  async function walk(entry: FileSystemEntry): Promise<void> {
    if (entry.isFile) {
      const file = await (entry as FileSystemFileEntry).file();
      results.push(fileToDropped(file));
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      // readEntries returns batches — loop until empty
      let batch = await readBatch(reader);
      while (batch.length > 0) {
        await Promise.all(batch.map(walk));
        batch = await readBatch(reader);
      }
    }
  }
  return Promise.all(queue.map(walk)).then(() => results);
}
```

### Folder Manifest for LLM Injection

Cap everything so a huge folder never blows the model context window:

| Cap | Value | Why |
|---|---|---|
| Files listed in tree | 200 | keep the file tree readable |
| Files content-sampled | 8 | representative, not exhaustive |
| Chars per sample | 800 | enough to classify code, not flood |

Manifest shape: folder root, file count, total size, extension histogram,
file tree (paths), truncated samples of key files. The LLM prompt then asks
for: (1) project type, (2) main modules + roles, (3) tech stack, (4) notable
files — in plain text, no markdown fences (TTS-friendly).

## Code-Generation Guidance

When an app intent maps to this level: prefer real `webkitGetAsEntry()`
recursion over fake APIs; dedupe directory batches; cap sampled content; and
instruct the describing model to answer in plain text so speech output never
reads code-fence symbols aloud.

## Related Reference

- `data/library/14-web-application-architecture.md` — frontend architecture
- `data/library/22-browser-engineering.md` — browser APIs & drag-and-drop
- `bible-reference/04-web/00-index.md` — level index
- MASTER-INDEX.txt at the curriculum root

---
*Deep guide | August 3, 2026 | Feature: Folder Drop & Content Description (wiki section 37)*
