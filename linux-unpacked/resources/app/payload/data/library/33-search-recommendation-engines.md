# 🔍 Search & Recommendation Engines

> Reference sheet for building search engines, recommendation systems, and personalization platforms. Covers inverted indices, Lucene/Elasticsearch architecture, learning-to-rank, vector search, collaborative filtering, and feature stores. Use this when implementing search, ranking, recommendations, or personalization features.

**Source Bible Level:** 36 — Search, Recommendation & Personalization

---

## 📊 Information Retrieval Metrics

| Metric | Formula | Use Case |
|---|---|---|
| **Precision@K** | `relevant_retrieved / K` | How many top-K results are relevant |
| **Recall@K** | `relevant_retrieved / total_relevant` | What fraction of all relevant docs are in top-K |
| **F1 Score** | `2 * P * R / (P + R)` | Harmonic mean of precision and recall |
| **MAP (Mean Avg Precision)** | `mean(avg precision@each relevant doc)` | Rank-sensitive, rewards early relevant docs |
| **NDCG** | `DCG / IDCG` | Graded relevance, logarithmic rank discount |
| **MRR** | `1 / rank_of_first_relevant` | Navigational queries (find first result) |
| **Hit Rate (HR@K)** | `1 if relevant in top-K else 0` | Binary relevance in top-K |

---

## 🏗️ Lucene Inverted Index Architecture

### Index Structure

```
Document ──► Analysis ──► Inverted Index ──► Segments ──► Merge Policy
                                                        │
                                                        ▼
                                              TieredMergePolicy
                                              (balance: IO vs search)
```

### Segment Structure

```typescript
interface LuceneSegment {
  // Term Dictionary (.tim)
  termDict: FST<number>;  // Finite State Transducer mapping term → block offset

  // Postings List (.doc) — delta-encoded doc IDs + frequencies
  postings: Map<number, DeltaEncodedList>;

  // Positions (.pos) — term positions within each document
  positions: Map<number, number[]>;

  // Payloads + Offsets (.pay) — for highlighting
  payloads: Map<number, Buffer>;

  // Norms (.nrm) — length normalization factors
  norms: Float32Array;

  // Stored Fields (.fdt, .fdx) — original document fields
  storedFields: BlockCompressedReader;
}

// BlockTree Term Index (FST-based)
class BlockTreeTermsWriter {
  // Build FST from term → block offset mappings
  // Terms are written in sorted order
  writeTermDictionary(terms: Map<string, TermBlock>): FST {
    const fst = new FST();
    let lastTerm = '';

    for (const [term, block] of terms) {
      // Share common prefix with previous term
      const prefixLen = commonPrefixLength(lastTerm, term);

      // Encode as: prefixLen, suffix, block metadata
      fst.addTransition(lastTerm, term, {
        prefixLen,
        suffix: term.slice(prefixLen),
        blockOffset: block.offset,
        blockSize: block.size,
      });

      lastTerm = term;
    }

    return fst;
  }
}

// Postings Encoding (FOR — Frame of Reference)
class FORCodec {
  encode(docIds: number[]): Buffer {
    // Delta-encode documents
    const deltas = new Array(docIds.length);
    let prev = 0;
    for (let i = 0; i < docIds.length; i++) {
      deltas[i] = docIds[i] - prev;
      prev = docIds[i];
    }

    // Pack into smallest bit width (PForDelta)
    const maxDelta = Math.max(...deltas);
    const bitsPerValue = Math.ceil(Math.log2(maxDelta + 1));

    // Bit-pack deltas
    return bitPack(deltas, bitsPerValue);
  }

  decode(data: Buffer, count: number, bitsPerValue: number): number[] {
    const deltas = bitUnpack(data, count, bitsPerValue);
    const docIds = new Array(count);
    let current = 0;
    for (let i = 0; i < count; i++) {
      current += deltas[i];
      docIds[i] = current;
    }
    return docIds;
  }
}
```

### Search Query Execution

```typescript
class IndexSearcher {
  segments: SegmentReader[];

  search(query: Query, topK: number): SearchResult[] {
    // Create a priority queue per segment
    const hitQueue = new PriorityQueue<{ doc: number; score: number }>(
      (a, b) => b.score - a.score  // Max-heap by score
    );

    for (const segment of this.segments) {
      // 1. Rewrite query — normalize synonyms, expand wildcards
      const rewritten = query.rewrite(segment);

      // 2. Create scorer — BM25 or custom similarity
      const scorer = this.createScorer(rewritten, segment);

      // 3. Leaf traversal — iterate matching documents
      let doc: number;
      while ((doc = scorer.next()) !== -1) {
        hitQueue.push({ doc, score: scorer.score() });
      }
    }

    // Collect top-K from all segments
    const results: SearchResult[] = [];
    for (let i = 0; i < topK && hitQueue.size() > 0; i++) {
      const hit = hitQueue.pop()!;
      results.push({
        docId: hit.doc,
        score: hit.score,
        fields: this.getStoredFields(hit.doc),
      });
    }

    return results;
  }
}

// BM25 Scoring
function bm25(
  termFreq: number,        // TF in document
  docLength: number,       // Document length (in tokens)
  avgDocLength: number,    // Average document length in collection
  docFreq: number,         // Document frequency (docs containing term)
  totalDocs: number,       // Total documents in index
  k1 = 1.2,               // Saturation parameter
  b = 0.75                 // Length normalization parameter
): number {
  const idf = Math.log(1 + (totalDocs - docFreq + 0.5) / (docFreq + 0.5));
  const tfNorm = (termFreq * (k1 + 1)) / (termFreq + k1 * (1 - b + b * docLength / avgDocLength));
  return idf * tfNorm;
}
```

### Analysis Chain

```typescript
class AnalysisChain {
  // CharFilter — pre-processing (HTML strip, pattern replace)
  charFilters: CharFilter[] = [];

  // Tokenizer — splits text into tokens
  tokenizer: Tokenizer;

  // TokenFilter — processes tokens (lowercase, stem, stop words)
  tokenFilters: TokenFilter[] = [];

  analyze(input: string): Token[] {
    let text = input;

    // Apply character filters
    for (const filter of this.charFilters) {
      text = filter.filter(text);
    }

    // Tokenize
    let tokens = this.tokenizer.tokenize(text);

    // Apply token filters
    for (const filter of this.tokenFilters) {
      tokens = filter.filter(tokens);
    }

    return tokens;
  }
}

// Standard analyzer components
const standardAnalyzer: AnalysisChain = {
  charFilters: [new HTMLStripCharFilter()],
  tokenizer: new StandardTokenizer(),  // Unicode Text Segmentation
  tokenFilters: [
    new LowercaseFilter(),
    new StopWordFilter(stopWords),
    new PorterStemFilter(),            // English stemming
  ],
};
```

---

## 🧠 Learning to Rank (LTR)

### Feature Engineering

```typescript
interface RankingFeature {
  name: string;
  category: 'query_doc' | 'query' | 'doc' | 'context';
  compute(query: Query, doc: Document, context: SearchContext): number;
}

// Example features
const rankingFeatures: RankingFeature[] = [
  // Query-Document features
  { name: 'bm25_title', category: 'query_doc', compute: (q, d) => bm25Score(q, d.title) },
  { name: 'bm25_body', category: 'query_doc', compute: (q, d) => bm25Score(q, d.body) },
  { name: 'exact_phrase_match', category: 'query_doc', compute: exactPhraseScore },
  { name: 'proximity_score', category: 'query_doc', compute: termProximity } ,

  // Query features
  { name: 'query_length', category: 'query', compute: (q) => q.terms.length },
  { name: 'query_intent', category: 'query', compute: queryIntentClassifier },

  // Document features
  { name: 'page_rank', category: 'doc', compute: (q, d) => d.pageRank },
  { name: 'document_freshness', category: 'doc', compute: (q, d) => daysSince(d.publishDate) },
  { name: 'document_length', category: 'doc', compute: (q, d) => d.body.length },

  // Context features
  { name: 'user_click_history', category: 'context', compute: (q, d, c) => c.userHistory.get(d.url) },
  { name: 'geo_match', category: 'context', compute: (q, d, c) => geoDistance(c.location, d.location) },
];
```

### LambdaMART (Gradient Boosted Decision Trees)

```typescript
// LambdaMART — Listwise ranking via gradient boosted trees
class LambdaMART {
  trees: DecisionTree[];
  learningRate = 0.1;

  train(dataset: QueryDocPair[], labels: number[]): void {
    // Initialize with average score
    let predictions = dataset.map(() => 0);

    for (let round = 0; round < this.numTrees; round++) {
      // Compute λ-gradients (pairwise swap probabilities)
      const lambdas = this.computeLambdas(predictions, dataset, labels);

      // Fit regression tree to λ-gradients
      const tree = new DecisionTree();
      tree.fit(dataset.map(d => d.features), lambdas);

      // Update predictions
      for (let i = 0; i < predictions.length; i++) {
        predictions[i] += this.learningRate * tree.predict(dataset[i].features);
      }

      this.trees.push(tree);

      // Early stopping if NDCG doesn't improve
    }
  }

  private computeLambdas(predictions: number[], dataset: QueryDocPair[], labels: number[]): number[] {
    const lambdas = new Array(predictions.length).fill(0);

    // Group by query
    const queries = groupByQuery(dataset);

    for (const [qid, pairs] of queries) {
      // For each pair (i, j) where label[i] > label[j]:
      for (const i of pairs) {
        for (const j of pairs) {
          if (labels[i] <= labels[j]) continue;

          const deltaNDCG = this.deltaNDCG(i, j, labels);
          const scoreDiff = predictions[i] - predictions[j];
          const lambda = deltaNDCG / (1 + Math.exp(scoreDiff));

          lambdas[i] += lambda;
          lambdas[j] -= lambda;
        }
      }
    }

    return lambdas;
  }

  predict(features: number[]): number {
    let score = 0;
    for (const tree of this.trees) {
      score += this.learningRate * tree.predict(features);
    }
    return score;
  }
}
```

---

## 🌊 Vector Search & Embeddings

```typescript
interface VectorIndex {
  dimension: number;
  insert(id: string, vector: number[]): void;
  search(vector: number[], topK: number): VectorSearchResult[];
}

// HNSW (Hierarchical Navigable Small World)
class HNSWIndex implements VectorIndex {
  dimension: number;
  private layers: LevelGraph[] = [];
  private entryPoint: number | null = null;
  private M = 16;          // Number of connections per node
  private M_max = 32;      // Max connections at higher layers
  private efConstruction = 200;

  insert(id: string, vector: number[]): void {
    const node: HNSWNode = { id, vector, neighbors: [] };
    const level = this.randomLevel();
    const entry = this.entryPoint;

    for (let l = this.layers.length - 1; l >= 0; l--) {
      // Greedy search to find closest node at each level
      entry = this.greedySearch(entry, vector, layer: l);
    }

    // At level 0, do efConstruction search
    const candidates = this.searchLayer(vector, entry, this.efConstruction, 0);

    // Connect to M nearest neighbors
    node.neighbors[0] = candidates.slice(0, this.M);

    // For higher levels, connect to M_max neighbors
    for (let l = 1; l <= level; l++) {
      node.neighbors[l] = candidates.slice(0, this.M_max);
    }

    // Update entry point if needed
    if (level > this.layers.length - 1) {
      this.entryPoint = node;
    }

    // Connect selected neighbors back to this node (bidirectional)
    for (const neighbor of candidates) {
      neighbor.neighbors[0].push(node);
      if (neighbor.neighbors[0].length > this.M_max) {
        // Prune — keep closest M_max neighbors
        this.pruneNeighbors(neighbor, 0);
      }
    }
  }

  search(query: number[], topK: number): VectorSearchResult[] {
    let entry = this.entryPoint;
    if (entry === null) return [];

    // Traverse from top layer to layer 1
    for (let l = this.layers.length - 1; l >= 1; l--) {
      entry = this.greedySearch(entry, query, l);
    }

    // Search layer 0 with ef = max(topK, efSearch)
    const efSearch = Math.max(topK, 50);
    const candidates = this.searchLayer(query, entry, efSearch, 0);

    // Sort by distance and take topK
    candidates.sort((a, b) => a.distance - b.distance);
    return candidates.slice(0, topK).map(c => ({ id: c.id, score: 1 / (1 + c.distance) }));
  }
}
```

---

## 📊 Recommendation Systems

### Collaborative Filtering — Matrix Factorization

```typescript
class MatrixFactorization {
  // User-factors and item-factors
  userFactors: Map<string, number[]>;  // user_id → latent vector
  itemFactors: Map<string, number[]>;  // item_id → latent vector
  numFactors = 20;
  learningRate = 0.01;
  regularization = 0.02;

  train(ratings: Rating[]): void {
    // Initialize factors with small random values
    for (const rating of ratings) {
      if (!this.userFactors.has(rating.userId)) {
        this.userFactors.set(rating.userId, this.randomVector());
      }
      if (!this.itemFactors.has(rating.itemId)) {
        this.itemFactors.set(rating.itemId, this.randomVector());
      }
    }

    for (let epoch = 0; epoch < 50; epoch++) {
      let totalLoss = 0;

      for (const rating of ratings) {
        const user = this.userFactors.get(rating.userId)!;
        const item = this.itemFactors.get(rating.itemId)!;

        // Predict: dot product + biases
        const biasU = this.userBias.get(rating.userId) ?? 0;
        const biasI = this.itemBias.get(rating.itemId) ?? 0;
        const biasG = this.globalBias;
        const prediction = this.dotProduct(user, item) + biasU + biasI + biasG;

        const error = rating.score - prediction;
        totalLoss += error * error;

        // SGD update
        const gradU = -2 * error * item.map(x => x);
        const gradI = -2 * error * user.map(x => x);

        for (let f = 0; f < this.numFactors; f++) {
          user[f] -= this.learningRate * (gradU[f] + this.regularization * user[f]);
          item[f] -= this.learningRate * (gradI[f] + this.regularization * item[f]);
        }
      }

      // Early stopping on convergence
      if (totalLoss / ratings.length < 0.001) break;
    }
  }

  predict(userId: string, itemId: string): number {
    const user = this.userFactors.get(userId);
    const item = this.itemFactors.get(itemId);
    if (!user || !item) return this.globalBias;
    return this.dotProduct(user, item) + this.globalBias;
  }

  recommend(userId: string, candidates: string[], topK: number): string[] {
    const scores = candidates.map(itemId => ({
      itemId,
      score: this.predict(userId, itemId),
    }));
    scores.sort((a, b) => b.score - a.score);
    return scores.slice(0, topK).map(s => s.itemId);
  }
}
```

### Two-Tower Neural Network

```typescript
// Two-Tower model for retrieval
class TwoTowerModel {
  queryEncoder: Sequential;   // Encoder for query features
  docEncoder: Sequential;     // Encoder for document features (shared or separate)
  scoreFunction = 'dot_product';

  forward(query: Tensor, doc: Tensor): Tensor {
    const queryEmbedding = this.queryEncoder.forward(query);
    const docEmbedding = this.docEncoder.forward(doc);

    // Normalize embeddings for cosine similarity
    const queryNorm = queryEmbedding.l2Normalize();
    const docNorm = docEmbedding.l2Normalize();

    // Dot product score
    return queryNorm.dot(docNorm);
  }

  // Training with sampled softmax
  loss(batch: Batch): Tensor {
    const queryEmbeddings = this.queryEncoder.forward(batch.queries);
    const docEmbeddings = this.docEncoder.forward(batch.positiveDocs);
    const negativeEmbeddings = this.docEncoder.forward(batch.negativeDocs);

    // In-batch negatives: treat other docs in batch as negatives
    const scores = queryEmbeddings.matMul(docEmbeddings.transpose());

    // Cross-entropy loss with temperature
    const temperature = 0.05;
    const logits = scores.div(temperature);
    const labels = identityMatrix(batch.size);

    return crossEntropyLoss(logits, labels);
  }
}
```

---

## 📊 Quick Reference: Search & Recommendation by Node Type

| Node Type | Relevant Concepts | Implementation Notes |
|---|---|---|
| **Input** | Query parsing, autocomplete, spell correction, query intent classification | Implement prefix/edge-gram indexing for autocomplete; use edit distance for spell correction |
| **Logic** | BM25 scoring, LambdaMART ranking, matrix factorization, two-tower models | Use BM25 as baseline ranker; deploy LambdaMART for production; precompute embeddings for real-time |
| **Database** | Inverted index segments, FST term dictionary, HNSW vector index, feature store | Use Lucene/Segment for text; pgvector/elasticsearch for vectors; Redis for feature store caching |
| **UI** | Search results snippet generation, faceted navigation, infinite scroll | Highlight matched terms in snippets; use faceted counts from field cache; implement lazy load for infinite scroll |
| **API** | Search-as-you-type, personalization headers, A/B test framework, dedup | Implement debounced search endpoint; pass user context headers; use contextual bandits for A/B tests |
| **Output** | Ranked results, recommendations carousel, personalized feed, explainable AI scores | Return NDCG-optimized ranking; explain recommendations via feature importance; deduplicate across result sets |

---

*For deeper technical details on any search or recommendation concept, see Bible Level 36 — Search, Recommendation & Personalization, including Elasticsearch/Lucene internals, vector search indexing strategies, and personalization experimentation frameworks.*
