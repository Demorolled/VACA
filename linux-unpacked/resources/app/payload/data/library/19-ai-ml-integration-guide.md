# 🤖 AI/ML Integration Guide

> Reference for integrating AI/ML capabilities into generated applications — model serving, training pipelines, evaluation, and LLM patterns.
> Extracted from The Programming Bible's AI/ML and LLM Guide levels.

---

## 1. ML Engineering Stack

```
┌─────────────────────────────────────────────┐
│            APPLICATION LAYER                  │
│  NLP   Vision   Speech   Robotics   Gaming   │
├─────────────────────────────────────────────┤
│         MODEL ARCHITECTURE LAYER              │
│  Transformers   CNNs   GNNs   Diffusion       │
├─────────────────────────────────────────────┤
│          TRAINING FRAMEWORK LAYER             │
│  PyTorch   JAX   TensorFlow   MXNet           │
├─────────────────────────────────────────────┤
│              COMPUTE LAYER                    │
│  CUDA   ROCm   oneAPI   Vulkan   CPU          │
└─────────────────────────────────────────────┘
```

### When to Use AI in Generated Apps

| Use Case | Approach | Complexity |
|---|---|---|
| **Classification** (spam, sentiment, category) | Linear models, decision trees, small transformers | Low |
| **Recommendation** | Collaborative filtering, embeddings, matrix factorization | Medium |
| **Content Generation** | LLMs, diffusion models | High |
| **Image/Audio Analysis** | CNNs, spectrograms, pretrained models | Medium |
| **Anomaly Detection** | Isolation forest, autoencoders, statistical methods | Low |
| **Natural Language** | Transformers, LSTMs, BERT-family | Medium-High |

---

## 2. Model Serving & Deployment

### Serving Architecture

```
Client → Load Balancer → [Model Server 1]
                          [Model Server 2]  → Model (ONNX/TensorRT)
                          [Model Server N]
                              │
                              ▼
                         Pre/Post Processing
                              │
                              ▼
                         Response Cache (Redis)
```

### ONNX Model Export & Serving

```python
# Export PyTorch model to ONNX
import torch
import torch.onnx
import onnxruntime

class TextClassifier(torch.nn.Module):
    def __init__(self, vocab_size: int, hidden_dim: int, num_classes: int):
        super().__init__()
        self.embedding = torch.nn.Embedding(vocab_size, hidden_dim)
        self.classifier = torch.nn.Linear(hidden_dim, num_classes)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(input_ids).mean(dim=1)
        return self.classifier(embedded)

# Export to ONNX
model = TextClassifier(vocab_size=10000, hidden_dim=128, num_classes=5)
model.eval()
dummy_input = torch.randint(0, 10000, (1, 64))  # (batch, seq_len)

torch.onnx.export(
    model,
    dummy_input,
    "model.onnx",
    input_names=["input_ids"],
    output_names=["logits"],
    dynamic_axes={"input_ids": {0: "batch_size"}, "logits": {0: "batch_size"}},
    opset_version=17,
)

# Serve with ONNX Runtime
class ModelServer:
    def __init__(self, model_path: str):
        self.session = onnxruntime.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def predict(self, input_ids: list[list[int]]) -> list[list[float]]:
        result = self.session.run(
            [self.output_name],
            {self.input_name: input_ids}
        )
        return result[0].tolist()

    def predict_batch(self, inputs: list[list[int]]) -> list[list[float]]:
        import numpy as np
        # Batching with padding
        max_len = max(len(inp) for inp in inputs)
        padded = [inp + [0] * (max_len - len(inp)) for inp in inputs]
        return self.predict(np.array(padded, dtype=np.int64))
```

### REST API for Model Serving

```python
# FastAPI model serving endpoint
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
model_server = ModelServer("model.onnx")

class PredictionRequest(BaseModel):
    text: str
    max_length: int = 64

class PredictionResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict[str, float]

LABELS = ["negative", "neutral", "positive", "mixed", "other"]

def tokenize(text: str, max_length: int) -> list[int]:
    # Simplified tokenization — use your actual tokenizer
    return [hash(word) % 10000 for word in text.split()[:max_length]]

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    try:
        tokens = tokenize(request.text, request.max_length)
        logits = model_server.predict([tokens])[0]
        import numpy as np
        probs = np.exp(logits) / np.sum(np.exp(logits))

        predicted_idx = int(np.argmax(probs))
        return PredictionResponse(
            label=LABELS[predicted_idx],
            confidence=float(probs[predicted_idx]),
            probabilities={LABELS[i]: float(p) for i, p in enumerate(probs)}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model_server.session is not None}
```

---

## 3. Training Pipeline Architecture

```
Data Sources
    │
    ▼
┌──────────────┐
│ Data Loading  │  PyTorch DataLoader, StreamingDataset
└──────┬───────┘
       ▼
┌──────────────┐
│ Augmentation  │  Random crop, flip, noise, mixup
└──────┬───────┘
       ▼
┌──────────────┐
│ Training      │  Forward → Loss → Backward → Optimize
└──────┬───────┘
       ▼
┌──────────────┐
│ Evaluation    │  Validation metrics, early stopping
└──────┬───────┘
       ▼
┌──────────────┐
│ Export        │  ONNX, TorchScript, quantized
└──────┬───────┘
       ▼
    Model Registry
```

### Data Loading Patterns

```python
import torch
from torch.utils.data import Dataset, DataLoader, IterableDataset

# Standard dataset
class TextDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int]):
        self.texts = texts
        self.labels = labels

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        tokens = tokenize(self.texts[idx])
        return torch.tensor(tokens, dtype=torch.long), torch.tensor(self.labels[idx])

# Streaming dataset (for large data)
class StreamingTextDataset(IterableDataset):
    def __init__(self, file_paths: list[str], shard_id: int = 0, num_shards: int = 1):
        self.file_paths = file_paths[shard_id::num_shards]

    def __iter__(self):
        for path in self.file_paths:
            with open(path, 'r') as f:
                for line in f:
                    yield process_line(line)

# Efficient DataLoader
dataloader = DataLoader(
    dataset,
    batch_size=32,
    shuffle=True,
    num_workers=4,          # Parallel loading
    pin_memory=True,         # Faster GPU transfer
    prefetch_factor=2,       # Prefetch batches
)
```

### Training Loop Pattern

```python
import torch
import torch.nn as nn
from torch.cuda.amp import autocast, GradScaler

def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    use_amp: bool = False,
) -> float:
    model.train()
    total_loss = 0
    scaler = GradScaler(enabled=use_amp)

    for batch_idx, (inputs, labels) in enumerate(dataloader):
        inputs, labels = inputs.to(device), labels.to(device)

        optimizer.zero_grad()

        # Mixed precision training
        with autocast(enabled=use_amp):
            outputs = model(inputs)
            loss = nn.functional.cross_entropy(outputs, labels)

        # Backward pass with gradient scaling
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        total_loss += loss.item()

        if batch_idx % 100 == 0:
            print(f"Batch {batch_idx}: loss = {loss.item():.4f}")

    return total_loss / len(dataloader)
```

---

## 4. LLM Integration Patterns

### LLM API Integration

```typescript
// Generic LLM client for generated apps
interface LLMConfig {
  provider: 'openai' | 'anthropic' | 'ollama' | 'custom';
  apiKey?: string;
  baseUrl?: string;
  model: string;
  maxTokens?: number;
  temperature?: number;
}

interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

class LLMClient {
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
  }

  async chat(messages: LLMMessage[]): Promise<string> {
    switch (this.config.provider) {
      case 'openai':
        return this.callOpenAI(messages);
      case 'anthropic':
        return this.callAnthropic(messages);
      case 'ollama':
        return this.callOllama(messages);
      case 'custom':
        return this.callCustom(messages);
    }
  }

  private async callOpenAI(messages: LLMMessage[]): Promise<string> {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.config.apiKey}`,
      },
      body: JSON.stringify({
        model: this.config.model,
        messages,
        max_tokens: this.config.maxTokens ?? 1024,
        temperature: this.config.temperature ?? 0.7,
      }),
    });

    if (!response.ok) throw new Error(`LLM API error: ${response.status}`);
    const data = await response.json();
    return data.choices[0].message.content;
  }

  private async callOllama(messages: LLMMessage[]): Promise<string> {
    const response = await fetch(`${this.config.baseUrl ?? 'http://localhost:11434'}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.config.model,
        messages,
        stream: false,
      }),
    });

    if (!response.ok) throw new Error(`Ollama error: ${response.status}`);
    const data = await response.json();
    return data.message.content;
  }

  // Streaming helper
  async* chatStream(messages: LLMMessage[]): AsyncGenerator<string> {
    const response = await fetch(`${this.config.baseUrl ?? 'http://localhost:11434'}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.config.model,
        messages,
        stream: true,
      }),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value);
      for (const line of text.split('\n').filter(Boolean)) {
        try {
          const json = JSON.parse(line);
          if (json.message?.content) yield json.message.content;
        } catch { /* skip malformed lines */ }
      }
    }
  }
}
```

### Embedding & Vector Search

```typescript
// Simple vector store for semantic search
interface Embedding {
  vector: number[];
  metadata: Record<string, unknown>;
}

class VectorStore {
  private items: Embedding[] = [];

  add(vector: number[], metadata: Record<string, unknown>): void {
    this.items.push({ vector, metadata });
  }

  async search(queryVector: number[], topK: number = 5): Promise<{ metadata: Record<string, unknown>; score: number }[]> {
    const scores = this.items.map((item) => ({
      metadata: item.metadata,
      score: cosineSimilarity(queryVector, item.vector),
    }));

    scores.sort((a, b) => b.score - a.score);
    return scores.slice(0, topK);
  }
}

// Cosine similarity
function cosineSimilarity(a: number[], b: number[]): number {
  let dotProduct = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}
```

---

## 5. MLOps Maturity Levels

| Level | Description | Practices |
|---|---|---|
| **L0: Manual** | Notebook-based, no automation | Manual training, no versioning, no monitoring |
| **L1: Pipeline Automation** | Automated training pipelines | Experiment tracking, model versioning, data validation, feature store |
| **L2: CI/CD for ML** | Full automation + testing | A/B testing, evaluation gates, rollback, monitoring |

### Evaluation Metrics

```python
import numpy as np
from typing import Sequence

def accuracy(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    return np.mean(np.array(y_true) == np.array(y_pred))

def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int], num_classes: int) -> np.ndarray:
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    return cm

def precision_recall_f1(y_true: Sequence[int], y_pred: Sequence[int], average: str = 'macro') -> dict:
    cm = confusion_matrix(y_true, y_pred, len(set(y_true)))
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp

    precision = tp / (tp + fp + 1e-10)
    recall = tp / (tp + fn + 1e-10)
    f1 = 2 * precision * recall / (precision + recall + 1e-10)

    if average == 'macro':
        return {
            'precision': float(precision.mean()),
            'recall': float(recall.mean()),
            'f1': float(f1.mean()),
        }
    return {'precision': precision.tolist(), 'recall': recall.tolist(), 'f1': f1.tolist()}
```

---

## Quick Reference: AI/ML by Node Type

| Node Type | AI/ML Mapping |
|---|---|
| **Input** | Feature extraction, embedding, tokenization, data validation |
| **Logic** | Model inference, training loop, evaluation, RAG pipeline |
| **Database** | Feature store, vector DB, model registry, experiment tracking |
| **UI** | Prediction display, confidence visualization, chat interface |
| **API** | Model serving endpoint, embedding API, LLM proxy |

---

*For deeper AI/ML concepts, see Bible levels `07-ai-ml/`, `07-llm-guide/`, `10-machine-learning/`, and `37-aiml-platforms-llmops/`.*
