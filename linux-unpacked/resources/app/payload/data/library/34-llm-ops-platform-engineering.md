# 🤖 LLM Ops & AI Platform Engineering

> Reference for building production AI platforms — LLM serving, RAG pipelines, fine-tuning, prompt engineering, model evaluation, and AI governance.
> Extracted from The Programming Bible's AI/ML Platforms & LLM Ops level.

---

## 1. AI Platform Architecture

### Platform Layers

```
┌──────────────────────────────────────────────┐
│          APPLICATION LAYER                    │
│  Chat   Search   Copilot   Agent   Workflow   │
├──────────────────────────────────────────────┤
│          ORCHESTRATION LAYER                  │
│  RAG Pipeline   Agent Framework   Chain       │
├──────────────────────────────────────────────┤
│          MODEL INFERENCE LAYER                │
│  vLLM   TensorRT-LLM   Ollama   OpenAI API   │
├──────────────────────────────────────────────┤
│          MODEL DEVELOPMENT LAYER              │
│  Fine-tuning   LoRA   RLHF   Eval            │
├──────────────────────────────────────────────┤
│          INFRASTRUCTURE LAYER                 │
│  GPU Cluster   Vector DB   Model Registry    │
└──────────────────────────────────────────────┘
```

### When to Build AI Platforms

| Scenario | Approach | Complexity |
|---|---|---|
| **Simple LLM proxy** | OpenAI/Anthropic API wrapper | Low |
| **RAG chatbot over documents** | Embedding + vector DB + LLM | Medium |
| **Custom fine-tuned model** | LoRA/QLoRA on base model | High |
| **Multi-agent system** | Agent orchestration + tool use | High |
| **Real-time inference server** | vLLM, TensorRT-LLM with batching | Very High |

---

## 2. LLM Serving & Inference

### vLLM Architecture

```python
# vLLM — high-throughput LLM serving with PagedAttention
from vllm import LLM, SamplingParams

# Initialize model (loads once, serves many)
llm = LLM(
    model="meta-llama/Llama-3.1-8B-Instruct",
    tensor_parallel_size=2,       # Split across 2 GPUs
    max_model_len=8192,           # Context window
    gpu_memory_utilization=0.9,   # Leave room for KV cache
    quantization="fp8",           # FP8 inference
)

# Sampling parameters
sampling_params = SamplingParams(
    temperature=0.7,
    top_p=0.9,
    max_tokens=1024,
    stop=["<|eot_id|>"],
)

# Batch inference (vLLM handles dynamic batching)
outputs = llm.generate(
    ["What is RAG?", "Explain attention mechanisms"],
    sampling_params,
)

for output in outputs:
    print(output.outputs[0].text)
```

### Serving Architecture Patterns

| Pattern | Description | Use Case |
|---|---|---|
| **Stateless proxy** | Forward requests to API | Simple chat apps |
| **Batched inference** | Dynamic batching of concurrent requests | High throughput |
| **Continuous batching** | Add/remove sequences mid-generation | Real-time serving |
| **Speculative decoding** | Draft model + target model | Lower latency |
| **KV cache offloading** | GPU → CPU → Disk for long contexts | Long-document processing |

### FastAPI LLM Serving

```python
# Production LLM serving endpoint
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio

app = FastAPI()

class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.7
    stream: bool = False

class ChatResponse(BaseModel):
    message: str
    usage: dict[str, int]

# Global model instance (loaded once at startup)
model = None

@app.on_event("startup")
async def load_model():
    global model
    # Load model here (vLLM, Ollama, or API client)
    model = LLM("meta-llama/Llama-3.1-8B-Instruct")

@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completion(request: ChatRequest):
    if not model:
        raise HTTPException(503, "Model not loaded")

    try:
        if request.stream:
            return StreamingResponse(stream_response(model, request))

        result = await model.generate(request.messages, request)
        return ChatResponse(
            message=result.text,
            usage={"prompt_tokens": result.prompt_tokens,
                   "completion_tokens": result.completion_tokens,
                   "total_tokens": result.prompt_tokens + result.completion_tokens},
        )
    except Exception as e:
        raise HTTPException(500, f"Inference failed: {e}")

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}
```

---

## 3. RAG (Retrieval-Augmented Generation)

### RAG Pipeline Architecture

```
User Query
    │
    ▼
┌────────────────┐
│ Query Rewrite   │  ← Optimize query for retrieval
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Embedding       │  ← Convert to vector (e.g., text-embedding-3-small)
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Vector Search   │  ← ANN search in vector DB (top-K)
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Reranking       │  ← Cross-encoder reranking (top-3)
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Context Build   │  ← Assemble retrieved chunks + prompt template
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ LLM Generation  │  ← Generate answer with context
└───────┬────────┘
        │
        ▼
    Final Answer
```

### RAG Implementation

```python
# Complete RAG pipeline
from typing import List, Dict, Any
import numpy as np

class RAGPipeline:
    def __init__(self, embed_model, llm, vector_db, reranker=None):
        self.embed_model = embed_model
        self.llm = llm
        self.vector_db = vector_db
        self.reranker = reranker

    async def retrieve(self, query: str, top_k: int = 10) -> List[Dict]:
        """Retrieve relevant chunks from vector store."""
        query_embedding = await self.embed_model.embed(query)
        results = await self.vector_db.search(
            query_embedding, top_k=top_k
        )
        return results

    async def rerank(self, query: str, chunks: List[Dict], top_k: int = 3) -> List[Dict]:
        """Rerank retrieved chunks with cross-encoder."""
        if not self.reranker or len(chunks) <= top_k:
            return chunks[:top_k]

        scores = self.reranker.rerank(query, [c["text"] for c in chunks])
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ranked[:top_k]]

    def build_prompt(self, query: str, chunks: List[Dict]) -> str:
        """Assemble context and query into prompt."""
        context = "\n\n".join([
            f"[Source {i+1}]: {c['text'][:2000]}"
            for i, c in enumerate(chunks)
        ])
        return f"""You are a helpful assistant. Use the following context to answer the user's question.
If the context doesn't contain enough information, say so.

Context:
{context}

Question: {query}

Answer:"""

    async def generate(self, query: str, stream: bool = False):
        """Run full RAG pipeline."""
        # 1. Retrieve
        chunks = await self.retrieve(query)

        # 2. Rerank
        chunks = await self.rerank(query, chunks)

        # 3. Build prompt
        prompt = self.build_prompt(query, chunks)

        # 4. Generate
        return await self.llm.generate(prompt, stream=stream)
```

### Chunking Strategies

| Strategy | Description | Chunk Size | Overlap |
|---|---|---|---|
| **Fixed-size** | Split by token count | 256-1024 tokens | 10-20% |
| **Semantic** | Split at sentence/paragraph boundaries | Variable | — |
| **Recursive** | Recursively split by separators | 512 tokens | 128 tokens |
| **Document-aware** | Respect headers, sections, lists | Variable | 1-2 sentences |
| **Agentic** | LLM decides split points | Variable | — |

---

## 4. Fine-Tuning & Adaptation

### LoRA Fine-Tuning

```python
# LoRA fine-tuning with Hugging Face
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
)
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

# 1. Prepare model with LoRA
base_model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-3.1-8B-Instruct",
    torch_dtype="bfloat16",
    device_map="auto",
)

lora_config = LoraConfig(
    r=16,                       # Rank — higher = more capacity
    lora_alpha=32,              # Scaling factor
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.1,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()  # ~0.1-1% of params

# 2. Prepare dataset
def format_example(example):
    return {
        "text": f"<|user|>\n{example['question']}\n<|assistant|>\n{example['answer']}"
    }

dataset = Dataset.from_list(training_data).map(format_example)

# 3. Training arguments
training_args = TrainingArguments(
    output_dir="./lora-checkpoints",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=8,     # Effective batch = 32
    learning_rate=2e-4,
    num_train_epochs=3,
    logging_steps=10,
    save_steps=200,
    bf16=True,                         # bfloat16 for A100/H100
    optim="adamw_8bit",                # Memory-efficient optimizer
)

# 4. Train
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
)
trainer.train()

# 5. Save (only LoRA weights — ~10MB)
model.save_pretrained("./lora-weights")
```

### Alignment Methods

| Method | Description | Data Requirement |
|---|---|---|
| **SFT** | Supervised fine-tuning on demonstrations | 100-10K examples |
| **DPO** | Direct Preference Optimization — pairs of preferred/rejected | 1K-50K preferences |
| **RLHF** | Reinforcement Learning from Human Feedback | Reward model + PPO |
| **ORPO** | Odds Ratio Preference Optimization — combines SFT + alignment | 1K-10K preferences |

---

## 5. Model Evaluation

### Evaluation Framework

```python
# LLM evaluation metrics
from typing import List, Dict
import numpy as np

class LLMEvaluator:
    """Evaluate LLM outputs across multiple dimensions."""

    def __init__(self, judge_model=None):
        self.judge_model = judge_model

    async def evaluate_groundedness(
        self, answer: str, context: str
    ) -> Dict[str, float]:
        """Check if answer is grounded in context."""
        prompt = f"""Determine if the answer is supported by the context.
Rate from 0 (not supported) to 1 (fully supported).

Context: {context[:2000]}
Answer: {answer}

Score (0-1):"""
        score = await self.judge_model.generate(prompt)
        return {"groundedness": float(score.strip())}

    async def evaluate_relevance(
        self, question: str, answer: str
    ) -> Dict[str, float]:
        """Check if answer is relevant to the question."""
        # Embed both and compute cosine similarity
        q_emb = await self.embed(question)
        a_emb = await self.embed(answer)
        similarity = np.dot(q_emb, a_emb) / (
            np.linalg.norm(q_emb) * np.linalg.norm(a_emb)
        )
        return {"relevance": float(similarity)}

    def evaluate_rouge(
        self, generated: str, reference: str
    ) -> Dict[str, float]:
        """ROUGE scores for summarization."""
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"])
        scores = scorer.score(reference, generated)
        return {
            "rouge1": scores["rouge1"].fmeasure,
            "rouge2": scores["rouge2"].fmeasure,
            "rougeL": scores["rougeL"].fmeasure,
        }
```

### Key Metrics

| Metric | What It Measures | Range | Target |
|---|---|---|---|
| **Perplexity** | Model confidence | 1-∞ | Lower is better |
| **BLEU** | N-gram overlap with reference | 0-100 | Higher is better |
| **ROUGE** | Recall-oriented overlap | 0-1 | Higher is better |
| **Faithfulness** | Factual accuracy vs context | 0-1 | >0.9 |
| **Latency (TTFT)** | Time to first token | ms | <500ms |
| **Throughput** | Tokens per second | tok/s | >50 tok/s |

---

## Quick Reference: LLM Ops by Node Type

| Node Type | LLM Ops Mapping |
|---|---|
| **Input** | Prompt template, query rewriting, guardrails, input validation |
| **Logic** | RAG pipeline, agent orchestration, fine-tuning, eval, routing |
| **Database** | Vector DB, conversation history, prompt registry, cache |
| **UI** | Chat interface, streaming response, token usage display |
| **API** | LLM proxy, model serving, rate limiting, cost tracking |

---

## Quick Reference: Prompt Engineering Patterns

| Pattern | Description | Example |
|---|---|---|
| **Chain-of-Thought** | Step-by-step reasoning | "Let's think step by step..." |
| **Few-Shot** | Provide examples | "Here are 3 examples..." |
| **Structured Output** | JSON schema enforcement | "Respond in JSON: {schema}" |
| **System Prompt** | Role/constraints | "You are a helpful coding assistant..." |
| **Context Window** | Sliding window of history | Keep last N messages |

---

*For deeper LLM/AI concepts, see Bible levels `37-aiml-platforms-llmops/`, `10-machine-learning/`, `07-ai-ml/`, and `36-search-recs-personalization/` (vector search).*
