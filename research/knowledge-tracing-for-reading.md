# Knowledge Tracing for Reading: Adapting Educational Models to Track Reader Knowledge State

Deep research into how Knowledge Tracing (BKT, DKT, and modern variants) from educational technology can be adapted for modeling a reader's knowledge state from reading articles. This is a foundational architectural investigation for Petrarca's knowledge model.

*Last updated: 2026-03-07*

---

## Table of Contents

1. [The Core Analogy](#1-the-core-analogy)
2. [Bayesian Knowledge Tracing (BKT)](#2-bayesian-knowledge-tracing-bkt)
3. [Deep Knowledge Tracing (DKT)](#3-deep-knowledge-tracing-dkt)
4. [Modern Variants: SAKT, AKT, SAINT, DKVMN](#4-modern-variants)
5. [The Passive Learning Problem](#5-the-passive-learning-problem)
6. [Knowledge Component Granularity](#6-knowledge-component-granularity)
7. [Forgetting and Decay Models](#7-forgetting-and-decay-models)
8. [Multi-Source Learning and Transfer](#8-multi-source-learning-and-transfer)
9. [Preference Tracing: KT Applied to Recommendations](#9-preference-tracing)
10. [Novelty Detection in Information Retrieval](#10-novelty-detection-in-information-retrieval)
11. [Practical Implementations](#11-practical-implementations)
12. [Synthesis: A Knowledge Tracing Architecture for Petrarca](#12-synthesis-architecture-for-petrarca)
13. [Sources](#13-sources)

---

## 1. The Core Analogy

The fundamental insight connecting educational knowledge tracing to reading is:

| Education | Reading (Petrarca) |
|-----------|-------------------|
| Student does exercises | User reads articles |
| System tracks which skills/concepts are mastered | System tracks which knowledge contributions are absorbed |
| Knowledge Component (KC) = atomic skill | Knowledge Contribution = atomic information unit |
| Quiz response (correct/incorrect) = observation | Reading behavior + explicit signals = observation |
| Predict: "Will they get the next question right?" | Predict: "Is this article's content new to them?" |

The fundamental unit is the **concept/contribution**, not the lesson/article. A student who learns fractions from both a textbook and a video has the same knowledge state. Similarly, a reader who encounters "git worktrees enable parallel agent execution" from Article 7 or from a synthesis report has the same knowledge state.

This reframing is crucial: articles are not the unit of tracking. The extracted knowledge contributions are.

---

## 2. Bayesian Knowledge Tracing (BKT)

### Overview

BKT, introduced by Corbett & Anderson (1995), is the foundational model for tracking student knowledge. It formalizes learning as a **Hidden Markov Model (HMM)** where knowledge is a latent binary variable (mastered / not mastered) that transitions over time.

### The Four Parameters

| Parameter | Symbol | Meaning |
|-----------|--------|---------|
| **Prior Knowledge** | P(L_0) | Probability the skill was already known before any interaction |
| **Learn Rate** | P(T) | Probability of transitioning from "not mastered" to "mastered" after a practice opportunity |
| **Guess Rate** | P(G) | Probability of a correct response when the skill is NOT mastered |
| **Slip Rate** | P(S) | Probability of an incorrect response when the skill IS mastered |
| **Forget Rate** | P(F) | Probability of transitioning from "mastered" to "not mastered" (traditionally set to 0) |

### Core Update Equations

**Posterior update after observing a correct response:**

```
P(L_t | obs=correct) = P(L_t) * (1 - P(S)) / [P(L_t) * (1 - P(S)) + (1 - P(L_t)) * P(G)]
```

**Posterior update after observing an incorrect response:**

```
P(L_t | obs=wrong) = P(L_t) * P(S) / [P(L_t) * P(S) + (1 - P(L_t)) * (1 - P(G))]
```

**State transition (learning step):**

```
P(L_{t+1}) = P(L_t | obs) + (1 - P(L_t | obs)) * P(T)
```

**Performance prediction:**

```
P(Correct_{t+1}) = P(L_{t+1}) * (1 - P(S)) + (1 - P(L_{t+1})) * P(G)
```

### Validity Constraints

For the model to be meaningful:
- `1 - P(S) >= P(G)` (a knower must perform at least as well as a guesser)
- All probabilities in (0, 1)

### Key Properties for Petrarca

1. **Simplicity**: Only 4 parameters per knowledge component. This is tractable even for thousands of KCs.
2. **Interpretability**: Each parameter has a clear meaning. Users can understand why the system thinks they know something.
3. **Bayesian updating**: New evidence updates beliefs incrementally. No need to retrain.
4. **Per-KC tracking**: Each knowledge component has its own mastery probability, enabling fine-grained novelty detection.

### Limitations

- **Binary knowledge state**: You either know it or you don't. No partial knowledge.
- **Requires observations**: Designed for quiz-style interactions (correct/incorrect). Reading is passive.
- **No forgetting** (in standard formulation): Once learned, always learned.
- **No inter-KC relationships**: Learning concept A doesn't affect concept B.
- **Single-skill per item**: Each exercise maps to exactly one KC.

### Extensions Relevant to Petrarca

**Individualized BKT** (Yudelson et al., CMU): Fits different P(L_0) and P(T) parameters per student. In Petrarca's case, some users might learn from reading more effectively than others.

**BKT with Forgetting**: Relaxes the P(F)=0 assumption. Research shows that "response correctness decreased based on time elapsed since the last response, with this decrease better modeled in BKT with conditional forget rates than with increased slip rates." This is critical for reading -- knowledge decays without reinforcement.

**Multi-resource BKT**: Different resources (textbook vs. video vs. tutor) have different learn rates. In Petrarca: different article types (tutorial vs. news vs. analysis) may produce different learning rates for the same KC.

---

## 3. Deep Knowledge Tracing (DKT)

### Overview

DKT (Piech et al., 2015, Stanford) replaces BKT's hand-crafted HMM with an **LSTM recurrent neural network**. The hidden state of the LSTM implicitly represents the student's knowledge state. DKT achieved a 25% improvement over BKT on the Assistments dataset (AUC 0.86 vs 0.69).

### Architecture

```
Input:  (exercise_id, response) at each time step
        -> One-hot encoding (or random embedding for large KC sets)
        -> LSTM layer(s) with hidden dim ~200
        -> Fully connected layer
        -> Sigmoid activation
Output: P(correct) for each possible next exercise
```

### Key Properties

1. **No explicit KC definition needed**: DKT can learn latent skill representations from data alone. The hidden state captures relationships between skills that BKT cannot.
2. **Handles multi-skill interactions**: The LSTM hidden state can encode dependencies between skills (learning fractions helps with ratios).
3. **Scalable**: Works on datasets with thousands of exercises.

### Limitations for Petrarca

1. **Requires large training data**: DKT needs thousands of student interaction sequences to train. A single-user app like Petrarca will never have enough data to train a DKT from scratch.
2. **Black box**: The hidden state is not interpretable. You cannot ask "what does this user know about topic X?"
3. **Still quiz-based**: Input is (exercise, correct/incorrect). Reading provides no such clean signal.

### Variants

- **DKT+** (Yeung & Yeung, 2018): Addresses reconstruction and waviness problems in original DKT. Adds regularization to ensure consistent predictions.
- **HELP-DKT**: Interpretable variant that maps hidden state dimensions to named concepts.

---

## 4. Modern Variants

### SAKT (Self-Attentive Knowledge Tracing)

Replaces LSTM with a **Transformer self-attention mechanism**. The entire sequence of past interactions is available at each step (vs. LSTM's compressed hidden state). However, SAKT "struggles with capturing long-term dependencies between distant interactions" in practice, despite the theoretical advantage.

### AKT (Attentive Knowledge Tracing)

Context-Aware AKT (Ghosh et al., UMass, KDD 2020) integrates **psychometric principles with attention**:
- Uses a **monotonically and exponentially decaying attention** mechanism -- recent interactions matter more than distant ones
- Incorporates **Rasch model-like** question difficulty embeddings
- Achieves strong performance by combining IRT (Item Response Theory) psychometrics with deep learning

**Relevance to Petrarca**: AKT's decaying attention is directly analogous to knowledge decay from reading. More recent reading should weigh more heavily in estimating current knowledge state.

### SAINT (Separated Self-Attentive Neural Knowledge Tracing)

Uses a **Transformer encoder-decoder** architecture. The encoder processes exercise sequences; the decoder processes response sequences. SAINT+ adds temporal features (elapsed time, lag time). The separation lets the model learn different representations for "what was attempted" vs. "how it was answered."

### DKVMN (Dynamic Key-Value Memory Networks)

The most architecturally interesting variant for Petrarca. DKVMN (Zhang et al., 2017) uses **two separate memory matrices**:

| Matrix | Role | Behavior |
|--------|------|----------|
| **Key matrix M^k** (static) | Stores N latent knowledge concept representations | Does NOT change during learning. Represents the "concept space." |
| **Value matrix M^v** (dynamic) | Stores mastery levels for each concept | Updated after each interaction via read/write operations. |

**Read operation**: Given exercise q_t, compute attention weights w_t over concept slots using dot product with key matrix. Then read from value matrix: `r_t = sum(w_t * M_v)`.

**Write operation**: After observing response, compute erase vector e_t and add vector a_t. Update value matrix:
```
M_v[i] = M_v[i] * (1 - w_t[i] * e_t) + w_t[i] * a_t
```

**Why this matters for Petrarca**: DKVMN's architecture maps almost perfectly to what we need:
- **Key matrix** = the universe of knowledge contributions extracted from articles (static, grows as new articles are processed)
- **Value matrix** = the user's current mastery level of each contribution (dynamic, updates as they read)
- **Read operation** = given a new article, look up which concepts it covers and check current mastery
- **Write operation** = after reading, update mastery estimates for covered concepts

The DKVMN architecture provides an explicit, inspectable knowledge state (unlike DKT's black-box hidden state) while still capturing inter-concept relationships through the attention mechanism.

### Recent Developments (2024-2025)

- **Graph-based KT**: Models prerequisite structures between concepts using Graph Neural Networks. Structure-based Knowledge Tracing (SKT) captures "influence propagation among concepts" -- learning one concept affects mastery estimates for related concepts.
- **LLM-enhanced KT**: From 2024 onward, models that use LLMs for knowledge tracing are emerging. These use LLMs for concept extraction, question understanding, and even direct knowledge state estimation.
- **Hybrid models**: Account for 23.8% of recent literature. Combine multiple paradigms (attention + graph + memory).
- A 2025 domain knowledge-informed attention-based KT method achieves an AUC of 0.975.

---

## 5. The Passive Learning Problem

This is the critical gap between educational KT and reading-based knowledge modeling. KT was designed for systems where students answer questions (binary correct/incorrect). Reading is passive -- how do we get signal?

### The Observation Problem

In BKT:
```
Observation = student answers question -> correct/incorrect
```

In reading:
```
Observation = user reads article -> ???
```

There is no binary correct/incorrect signal. The system must infer learning from **indirect evidence**.

### Comprehension Factor Analysis (CFM)

The most directly relevant prior work. Thaker, Carvalho & Koedinger (2019, LAK) proposed **Comprehension Factor Analysis** for MOOCs:

- **Problem**: Traditional ITS systems only use quiz/problem-solving interactions. Reading interactions are entirely ignored in student modeling.
- **Solution**: CFM is a **logistic regression model** that takes both previous quiz performance AND reading behaviors to predict success on questions.
- **Key insight**: A "reading opportunity" begins when the student visits a page and ends when they start doing practice or leave. Each page is mapped to Knowledge Components.
- **Result**: CFM outperforms models that only use quiz data, proving that reading behavior carries genuine signal about knowledge acquisition.

**Implications for Petrarca**: CFM validates the core premise -- reading behavior IS informative about knowledge state. But CFM still has quizzes as ground truth. Petrarca has no quizzes.

### Signals That Substitute for Quiz Responses

Drawing from CFM, implicit feedback research, and eye-tracking studies, here are the signals available in a reading context:

| Signal | Strength | What it implies |
|--------|----------|-----------------|
| **Article opened** | Weak positive | User was exposed to the content |
| **Time spent reading** | Medium | Longer reading suggests engagement (but could be distraction) |
| **Scroll depth** | Medium | Reaching the end suggests consumption of content |
| **Paragraph highlighted** | Strong positive | User found this specific content noteworthy |
| **"I knew this" signal** | Strong explicit | User confirms prior knowledge of a claim |
| **"New to me" signal** | Strong explicit | User confirms this is novel information |
| **Article completed ("Done")** | Medium positive | User consumed the full content |
| **Article dismissed (swipe away)** | Weak negative | Content wasn't interesting or was already known |
| **Interest chip positive (+)** | Strong explicit | User explicitly endorses a topic |
| **Interest chip negative (-)** | Strong explicit | User explicitly rejects a topic |
| **Re-reading** | Strong | Returning to content suggests incomplete mastery |
| **Reading speed** | Medium | Very fast reading may indicate familiarity; slow reading may indicate new material |
| **Combination of scroll + time** | Medium-strong | Better than either alone (validated by research) |

Research by Kelly & Teevan shows that "a combination of time and scrolling activity gave a better prediction than time spent on a particular webpage alone." Reading time is "a good indicator for measuring relevance" and can serve as "a proxy to quantify how likely a content item is relevant to a particular user."

Eye-tracking research further validates this: "prior knowledge played a crucial role in how readers allocated visual attention during reading, resulting in more comprehensive memory for perspective-relevant information."

### Proposed Observation Model for Petrarca

Instead of binary correct/incorrect, we can define a **continuous observation** for each KC encountered in an article:

```
P(absorbed | KC, signals) = weighted combination of:
  - article_completed * 0.3      (base: did they finish?)
  - time_on_article_normalized * 0.2  (relative to expected reading time)
  - explicit_signal_if_any * 0.5  (highlight, "new to me", "knew it")
```

This replaces the binary observation in BKT with a soft probability. The BKT update equations can be modified:

```
// Instead of:
P(L_t | obs=correct) = ...

// Use:
P(L_t | absorption_probability) =
  absorption_probability * P(L_t) * (1-P(S)) / [P(L_t)*(1-P(S)) + (1-P(L_t))*P(G)]
  + (1 - absorption_probability) * P(L_t) * P(S) / [P(L_t)*P(S) + (1-P(L_t))*(1-P(G))]
```

This is a **soft BKT update** -- a weighted average of the "correct" and "incorrect" update equations, weighted by the absorption probability.

---

## 6. Knowledge Component Granularity

### The Extraction Problem

In education, KCs are predefined by curriculum designers: "addition of fractions," "solving quadratic equations," "photosynthesis." In reading, we must **extract them automatically** from article text.

This is the Q-matrix construction problem transferred to a new domain. The Q-matrix maps exercises to KCs. Our version: mapping article paragraphs to knowledge contributions.

### How Educational Systems Handle KC Discovery

**Expert-designed Q-matrices**: Traditionally, domain experts manually tag each exercise with the skills it requires. This is expensive but high-quality.

**Automated Q-matrix refinement (dAFM)**: Barnes (2005) and subsequent work use data-driven methods to refine expert Q-matrices. The key finding: "variants that attempted to learn the Q-matrix from scratch underperformed models which started with an expert-defined Q-matrix that was then refined." **Expert knowledge enhanced through data-driven refinement remains the best approach.**

**KCluster (Wei, Carvalho & Stamper, EDM 2025)**: The most relevant recent work. Uses LLMs for automated KC discovery:

1. **Question congruity metric**: Uses an LLM (Phi-2) as a "probability machine" to measure how likely two questions are to co-occur. This captures whether questions test the same underlying concept.
   ```
   Congruity(q_s, q_t) = 1/2 [Delta(q_s, q_t) + Delta(q_t, q_s)]
   ```
   where Delta is the change in log-probability when conditioning one question on another.

2. **Affinity propagation clustering**: Groups congruent questions into KC clusters without needing to pre-specify the number of clusters.

3. **KC label generation**: LLM generates descriptive labels for each cluster.

4. **Results**: KCluster "discovers KC models that predict student performance better than the best expert-designed models available."

**Implication for Petrarca**: We can use a similar LLM-based approach to automatically extract and cluster knowledge contributions from articles. The LLM's probability scores can measure whether two claims from different articles are "about the same thing."

### The Granularity Problem

"AI" is too broad. "GPT-4's context window limit of 128K tokens" is too narrow. What is the right level for a knowledge contribution?

Research on educational KC granularity shows:

| Level | Example | Problem |
|-------|---------|---------|
| **Too broad** | "Machine Learning" | Everything maps to it. No useful tracking. |
| **Right level** | "Transformer attention mechanisms enable parallel processing" | Specific enough to track, general enough to appear across articles |
| **Too narrow** | "GPT-4 has 128K token context window" | Only appears once. No tracking value. |

The KCluster research found that "decomposing 'apply evidence' into four specific variants like 'the practice or testing effect' and 'generative processing'" improved learning predictions. This suggests that **mid-level specificity** is optimal -- roughly the level of a claim or insight that could appear in multiple articles.

### LLM-Based KC Extraction for Articles

Recent research (MDPI 2025) on "Leveraging LLMs for Automated Extraction and Structuring of Educational Concepts" shows:

- LLMs "generate high-quality knowledge concepts and accurate inter-conceptual relations"
- A two-level hierarchy works: **Topics** (broad) and **Sub-Topics** (specific concepts within a topic)
- "LLMs exhibit uncertainty due to differences in granularity during extraction" -- some models extract too fine, others too coarse
- "Relation identification involves extracting semantic relations between concepts from curriculum content"

**For Petrarca**: The pipeline should extract knowledge contributions at roughly the "sub-topic" level -- specific enough to track, but general enough to recur across articles. The current `NoveltyClaim` type in the codebase (with `claim`, `specificity`, and `topic` fields) is a reasonable starting point but needs the addition of:
- A normalized/canonical form for deduplication
- Relationship links to other KCs (prerequisite, extends, contradicts)
- A stable ID for tracking across time

---

## 7. Forgetting and Decay Models

### BKT's Forgetting Extension

Standard BKT assumes no forgetting (P(F) = 0). Extensions add a forgetting parameter:

```
P(L_{t+1}) = P(L_t | obs) * (1 - P(F)) + (1 - P(L_t | obs)) * P(T)
```

Research shows "response correctness decreased based on time elapsed since the last response, with this decrease better modeled in BKT with conditional forget rates than with increased slip rates." Forgetting is real and must be modeled.

### The Forgetting Curve

Ebbinghaus (1885) established the foundational model. Modern research shows:

- **Exponential decay**: The basic model. `R = exp(-t/S)` where R is retrievability, t is time since learning, S is stability.
- **Power law of forgetting**: When memories of different complexity are mixed, forgetting follows a power law: `R = 0.9906 * t^(-0.07)`. This is empirically better than pure exponential.
- **FSRS finding**: "In FSRS v3, an exponential function was used, but in FSRS v4 it was replaced by a power function, which provided a better fit to the data."

### FSRS: The State of the Art in Memory Modeling

FSRS (Free Spaced Repetition Scheduler) is the most sophisticated open-source memory model, now used in Anki. It tracks three variables per item:

| Variable | Meaning | Range |
|----------|---------|-------|
| **Difficulty (D)** | How hard it is to strengthen memory stability | 1-10 |
| **Stability (S)** | Time in days for retrievability to drop from 100% to 90% | Days |
| **Retrievability (R)** | Current probability of successful recall | 0-1 |

Key formulas:

```
# Retrievability (power law forgetting curve)
R = (1 + factor * elapsed_days / S)^(-1/factor)
# where factor is personalized parameter w20 (0.1-0.8)

# Stability update after successful review:
S_new = S * S_increase
# where S_increase depends on:
#   f(D): Linear function (11-D), harder items grow stability slower
#   f(S): Larger S produces smaller increase (saturation effect)
#   f(R): Lower R at review time produces larger increase (desirable difficulty)

# Difficulty update:
D_new = D + delta * damping + mean_reversion_toward_default
# where delta depends on grade (Again/Hard/Good/Easy)
```

**Critical insight**: FSRS's stability concept maps perfectly to knowledge persistence from reading. After reading about "AI orchestration," the memory has some initial stability. Without re-encounter, retrievability decays. If the reader encounters the concept again in another article, stability increases (more for lower retrievability at time of re-encounter -- the "desirable difficulty" effect).

### Knowledge Decay from Reading vs. Flashcard Review

This is a crucial gap in the literature. Almost all forgetting research uses active recall (flashcards, quizzes). Reading is passive exposure, which produces weaker initial memory traces.

Key findings from passive learning research:

- "Memory retention drops exponentially shortly after learning, with up to 50% of newly acquired information lost within an hour if no effort is made to reinforce it"
- "Compared to passive repetitive learning, retrieval practice creates stronger and more durable memory traces"
- "Students using digital flashcards for retrieval practice outperformed students who only reread materials by over 50% on delayed tests"

**Implication for Petrarca**: Knowledge acquired through reading alone decays faster than knowledge acquired through active recall. Our model should use **shorter initial stability** for passively-read concepts compared to concepts the user explicitly interacted with (highlighted, marked as "new to me," etc.).

Proposed stability initialization:

| Interaction level | Initial stability (days) | Rationale |
|-------------------|--------------------------|-----------|
| Article skimmed (scroll-through, < 30% reading time) | 3 | Minimal processing |
| Article read normally | 7 | Standard passive reading |
| Specific claim highlighted | 14 | Active engagement with specific content |
| "New to me" signal on claim | 21 | Explicit conscious processing |
| Connected to existing knowledge (research note) | 30 | Deep processing, elaborative encoding |

---

## 8. Multi-Source Learning and Transfer

### Multiple Encounters Across Articles

When a reader encounters the same concept across multiple articles, each encounter should strengthen the knowledge trace. This is analogous to multi-resource learning in education.

BKT handles this through the transition probability P(T): each "practice opportunity" (reading encounter) gives a chance to move from unmastered to mastered. Multiple encounters simply provide multiple opportunities.

But the reading context adds a nuance: **diminishing returns**. The 6th article about "AI orchestration" adds less knowledge than the 1st. This is captured by:

1. **BKT's natural saturation**: As P(L_t) approaches 1.0, additional updates have less effect.
2. **FSRS's stability saturation**: "Larger S values produce smaller S_increase (saturation effect)."

### Learning Transfer and Prerequisites

Graph-based KT models (GKT, SKT) explicitly model how learning one concept affects others:

- **Structure-based Knowledge Tracing (SKT)**: Captures "influence propagation among concepts," motivated by the "transfer of knowledge" theory -- "students' knowledge states on relevant knowledge concepts will change when practicing on a specific concept due to potential knowledge structure."

- **Concept prerequisite graphs**: Research shows that "students who study concept pairs in a prerequisite order determined by these methodologies have a better overall success rate."

**For Petrarca**: If the user has read extensively about "Transformer architecture," their knowledge of "attention mechanisms" should be partially inferred even if they haven't read a dedicated article on attention. The knowledge graph of concepts should encode these prerequisite/transfer relationships.

Proposed transfer model:
```
// When concept A is learned, partially update related concept B:
P(L_B) += transfer_weight(A, B) * delta_P(L_A)

// where transfer_weight is derived from:
// - Co-occurrence in articles (concepts that appear together are related)
// - Hierarchical relationship (parent topic -> child topic)
// - LLM-assessed prerequisite relationship
```

---

## 9. Preference Tracing: KT Applied to Recommendations

### The Breakthrough Paper

"From Knowledge Tracing to Preference Tracing" (2025, Electronic Commerce Research and Applications) directly applies BKT to recommendation systems:

- **Core idea**: Just as KT tracks which skills a student has mastered, preference tracing tracks which content attributes a user currently prefers.
- **Knowledge components become preference components**: In the movie domain, these are genres, directors, actors, themes.
- **Knowledge state becomes preference state**: P(L_t) for each preference component represents the user's current interest level.
- **Observation**: Instead of correct/incorrect, the signal is rating or engagement (liked/not liked).

### Results

- BKT-based preference tracing "not only delivers comparable predictive performance but also effectively captures users' preferences at a **component-wise level**."
- DLKT-based preference tracing (operating without predefined components) "outperforms recent deep learning-based recommendation models."
- Evaluated on MovieLens 1M dataset.

### Dual Application for Petrarca

Petrarca needs BOTH:
1. **Knowledge tracing**: What does the user KNOW? (drives novelty scoring)
2. **Preference tracing**: What does the user CARE ABOUT? (drives interest scoring)

These are separate but interacting models:
- A user may KNOW a lot about "machine learning" but still be INTERESTED (expert wanting to stay current)
- A user may KNOW nothing about "medieval history" and be INTERESTED (new curiosity)
- A user may KNOW nothing about "cryptocurrency" and NOT be interested (irrelevant)

The preference tracing paper validates using BKT-style models for both tracking dimensions.

---

## 10. Novelty Detection in Information Retrieval

### Novelty as Anti-Redundancy

The TREC Novelty Track and related IR research provides a complementary perspective:

- "Novelty of a document is defined as the opposite of its redundancy, which can be calculated as the average distance between the current document and those the user previously consumed."
- "Detecting redundancy at the semantic level is not straightforward because the text may have less lexical overlap yet convey the same information."
- "Non-novel/redundant information in a document may have been assimilated from multiple source documents, not just one."

### NewsJunkie and Personalized Novelty

NewsJunkie (2004) pioneered personalized novelty in news: it "provides personalized newsfeeds via analysis of information novelty" -- exactly Petrarca's goal, though without a knowledge model.

### Knowledge-Aware News Recommendation

Recent work on knowledge-aware recommendation systems (Iana, Alam & Paulheim, 2024 survey) shows:

- "Injecting external knowledge into news recommender systems has been proposed to enhance recommendations by capturing information and patterns not contained in the text and metadata of articles."
- Over-specialization is a real risk: "Users are suggested articles semantically similar to ones already read, which can reduce the diversity and novelty of content."
- The combination of "knowledge graph embeddings and first-order logic rules led to improvements in both accuracy and novelty of recommendations."

### Connecting Novelty Detection to Knowledge Tracing

The key synthesis: if we track the user's knowledge state via KT, then **novelty scoring becomes a direct function of the knowledge state**:

```
novelty(article) = 1 - average(P(L_kc) for kc in article.knowledge_components)
```

An article is novel if the user's mastery of its constituent KCs is low. An article is redundant if the user already has high mastery of most of its KCs.

This is more principled than current approaches (embedding distance, keyword matching) because it:
1. Accounts for knowledge acquired from ALL previous articles (not just similar ones)
2. Handles partial novelty (article is 30% new, 70% known)
3. Naturally handles forgetting (knowledge decays, so old articles become partially "novel" again)
4. Separates WHAT the user knows from HOW they know it

---

## 11. Practical Implementations

### pyBKT

The reference implementation of BKT and extensions.

- **Language**: Python (with C++/Eigen backend for performance)
- **API**: Scikit-learn-style fit/predict interface
- **Variants**: Core BKT, forgetting, multi-guess/slip, multi-learn, individualized
- **Performance**: ~30,000x faster than BNT (Bayes Net Toolbox), ~3-4x faster than xBKT
- **Data format**: Pandas DataFrames with columns for student_id, skill_name, correct
- **Output**: Per-skill parameters (P(L_0), P(T), P(G), P(S)) and per-student-skill mastery estimates
- **Repository**: https://github.com/CAHLR/pyBKT

### DKT Implementations

- **PyTorch DKT**: LSTM-based, hidden dimension ~200, one-hot or embedding input
- **Training**: Binary cross-entropy loss, predicting P(correct) for next exercise
- **Repository**: https://github.com/shinyflight/Deep-Knowledge-Tracing

### DKVMN Implementation

- **TensorFlow/PyTorch**: Key matrix N x D_k, Value matrix N x D_v
- **N**: Number of concept slots (typically 20-200)
- **Repository**: https://github.com/jennyzhang0215/DKVMN

### FSRS

- **Python**: `pip install fsrs` (PyPI package)
- **Rust**: `rs-fsrs` crate
- **JavaScript/TypeScript**: `@squeakyrobot/fsrs` (npm)
- **Parameters**: 21 trainable parameters, optimized via gradient descent on review history
- **Can be implemented in ~100 lines** (see Fernando Borretti's implementation)
- **Repository**: https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler

### Performance Characteristics

All of these can run in real-time for a single user:

| Model | Prediction time | Training time | Memory |
|-------|----------------|---------------|--------|
| BKT | <1ms per KC | Minutes for 1000 KCs | KB per KC |
| DKT | ~10ms per sequence | Hours on GPU | MB for model |
| DKVMN | ~10ms per sequence | Hours on GPU | MB for model |
| FSRS | <1ms per item | Minutes for 10K items | Bytes per item |

For Petrarca (single user, thousands of KCs), BKT or FSRS-style per-KC tracking is most practical. No GPU needed. Can run entirely on-device.

---

## 12. Synthesis: A Knowledge Tracing Architecture for Petrarca

### The Proposed Model

Combining insights from all the research above, here is a concrete architecture for Petrarca's knowledge model:

### Layer 1: Knowledge Contribution Extraction (Pipeline)

**What**: Extract atomic knowledge contributions from each article during pipeline processing.

**How**: LLM (Gemini Flash) extracts structured contributions:

```typescript
interface KnowledgeContribution {
  id: string;                    // Stable hash of normalized claim
  claim_text: string;            // The actual knowledge claim
  normalized_form: string;       // Canonical form for deduplication
  topic_broad: string;           // "Artificial Intelligence"
  topic_specific: string;        // "LLM Agent Orchestration"
  specificity: 'high' | 'medium' | 'low';
  source_article_ids: string[];  // All articles containing this KC
  related_kcs: string[];         // IDs of related KCs
  prerequisite_kcs: string[];    // IDs of prerequisite KCs
}
```

**Granularity target**: ~5-15 KCs per article. Each should be a claim that could plausibly appear across multiple articles. Use KCluster-style deduplication to merge equivalent claims from different articles.

### Layer 2: KC Mastery Tracking (Modified BKT)

**What**: For each KC, maintain a mastery estimate that updates as the user reads articles containing that KC.

**Data structure per KC**:

```typescript
interface KCMasteryState {
  kc_id: string;

  // BKT-inspired state
  mastery_probability: number;    // P(L_t), 0-1

  // FSRS-inspired memory model
  stability_days: number;         // How long until P(recall) drops to 90%
  difficulty: number;             // 1-10, affects stability growth rate

  // Tracking
  encounter_count: number;        // How many times encountered across articles
  first_encountered: number;      // Timestamp
  last_encountered: number;       // Timestamp
  last_explicit_signal: number;   // Timestamp of last highlight/"new to me"/etc.

  // Signal history
  signals: Array<{
    timestamp: number;
    article_id: string;
    signal_type: 'read' | 'skimmed' | 'highlighted' | 'marked_new' | 'marked_known' | 'dismissed';
    absorption_score: number;     // 0-1, computed from signal combination
  }>;
}
```

### Layer 3: Observation Model (Signal-to-Absorption)

**What**: Convert reading behavior signals into an absorption probability for each KC encountered.

```typescript
function computeAbsorption(kc: KnowledgeContribution, article: Article, signals: UserSignals): number {
  let absorption = 0.0;

  // Base: did they read the article?
  if (signals.completed) absorption += 0.3;
  else if (signals.scroll_depth > 0.5) absorption += 0.15;

  // Time engagement
  const expectedMs = article.estimated_read_minutes * 60000;
  const timeRatio = Math.min(signals.time_spent_ms / expectedMs, 1.5);
  absorption += timeRatio * 0.15;

  // Explicit signals on this specific KC
  if (signals.highlighted_claims.includes(kc.id)) absorption += 0.3;
  if (signals.marked_new.includes(kc.id)) absorption += 0.4;
  if (signals.marked_known.includes(kc.id)) {
    // They already knew it -- this is a "correct" response, confirms mastery
    return 0.95;
  }

  // Cap at reasonable maximum for passive reading
  return Math.min(absorption, 0.85);
}
```

### Layer 4: Mastery Update (Soft BKT + FSRS Decay)

**What**: Update KC mastery after each reading encounter, incorporating forgetting.

```typescript
function updateMastery(state: KCMasteryState, absorption: number): void {
  // Step 1: Apply forgetting since last encounter (FSRS-style power law decay)
  const daysSinceLastEncounter = (Date.now() - state.last_encountered) / 86400000;
  if (daysSinceLastEncounter > 0) {
    const factor = 0.3; // Personalized decay factor
    const retrievability = Math.pow(
      1 + factor * daysSinceLastEncounter / state.stability_days,
      -1 / factor
    );
    state.mastery_probability *= retrievability;
  }

  // Step 2: Soft BKT update using absorption probability
  const P_L = state.mastery_probability;
  const P_T = 0.3;  // Learn rate (could vary by KC difficulty)
  const P_G = 0.1;  // Guess rate (low for reading -- passive exposure)
  const P_S = 0.05; // Slip rate (low -- if you know it, reading confirms)

  // Weighted average of correct/incorrect posterior updates
  const posterior_correct = P_L * (1 - P_S) / (P_L * (1 - P_S) + (1 - P_L) * P_G);
  const posterior_incorrect = P_L * P_S / (P_L * P_S + (1 - P_L) * (1 - P_G));
  const posterior = absorption * posterior_correct + (1 - absorption) * posterior_incorrect;

  // Step 3: Learning transition
  state.mastery_probability = posterior + (1 - posterior) * P_T * absorption;

  // Step 4: Update FSRS-style stability
  if (absorption > 0.3) {  // Meaningful encounter
    const stability_increase = Math.max(1, (11 - state.difficulty) * 0.5);
    const saturation_factor = Math.pow(state.stability_days, -0.2); // Diminishing returns
    const difficulty_factor = absorption > 0.6 ? 1.0 : 0.5; // Deep engagement matters more
    state.stability_days *= (1 + stability_increase * saturation_factor * difficulty_factor);
  }

  // Step 5: Update metadata
  state.encounter_count++;
  state.last_encountered = Date.now();
}
```

### Layer 5: Novelty Scoring

**What**: Score how novel an incoming article is based on the user's current knowledge state.

```typescript
function scoreNovelty(article: Article, kcStates: Map<string, KCMasteryState>): NoveltyScore {
  const kcs = article.knowledge_contributions;

  // Apply forgetting to all KCs before scoring (current state)
  const currentMasteries = kcs.map(kc => {
    const state = kcStates.get(kc.id);
    if (!state) return 0; // Never encountered = fully novel

    const daysSince = (Date.now() - state.last_encountered) / 86400000;
    const factor = 0.3;
    const retrievability = Math.pow(
      1 + factor * daysSince / state.stability_days,
      -1 / factor
    );
    return state.mastery_probability * retrievability;
  });

  const avgMastery = currentMasteries.reduce((a, b) => a + b, 0) / currentMasteries.length;
  const novelKCs = currentMasteries.filter(m => m < 0.3).length;
  const knownKCs = currentMasteries.filter(m => m > 0.7).length;

  return {
    overall_novelty: 1 - avgMastery,
    novel_kc_count: novelKCs,
    known_kc_count: knownKCs,
    total_kc_count: kcs.length,
    novel_percentage: novelKCs / kcs.length,
    // Human-readable label
    label: avgMastery < 0.2 ? 'Mostly new' :
           avgMastery < 0.5 ? 'Partly familiar' :
           avgMastery < 0.8 ? 'Mostly familiar' : 'Already known',
  };
}
```

### Layer 6: Knowledge Transfer (Graph-Based)

**What**: When a KC's mastery is updated, propagate partial updates to related KCs.

```typescript
function propagateTransfer(
  updatedKC: string,
  masteryDelta: number,
  kcGraph: Map<string, string[]>,
  kcStates: Map<string, KCMasteryState>
): void {
  const relatedKCs = kcGraph.get(updatedKC) || [];
  for (const relatedId of relatedKCs) {
    const relatedState = kcStates.get(relatedId);
    if (!relatedState) continue;

    // Transfer a fraction of the learning
    const transferRate = 0.1; // Conservative -- reading about A doesn't mean you learned B
    relatedState.mastery_probability = Math.min(
      1.0,
      relatedState.mastery_probability + masteryDelta * transferRate
    );
  }
}
```

### Theoretical Challenges

1. **Cold start**: No data on the user's existing knowledge. Must start from P(L_0) = 0.5 (uncertain) for all KCs and rely on explicit signals to bootstrap.

2. **KC explosion**: If every article generates 5-15 KCs, after 1000 articles we have 5,000-15,000 KCs. But with deduplication, the actual unique KC count should be much lower (concepts recur). Need efficient deduplication.

3. **No ground truth**: In education, quizzes validate the model. In reading, we never truly know if the user absorbed the content. The model's accuracy cannot be directly measured -- only indirectly through the quality of novelty predictions.

4. **Observation noise**: Reading time is noisy (phone face-down, multitasking). Scroll depth can be accidental. Only explicit signals (highlight, "new to me") are reliable. The model must be robust to noisy observations.

5. **KC quality**: If the LLM extracts poor KCs (too broad, too narrow, or just wrong), the entire model degrades. KC extraction quality is the foundational bottleneck.

6. **Parameter estimation**: BKT parameters (P(T), P(G), P(S)) are typically estimated via EM from large datasets. With a single user, we cannot fit individual parameters. Must use reasonable defaults and tune conservatively over time.

### Practical Challenges

1. **Computational**: BKT/FSRS per-KC tracking is lightweight. Can run on-device. No GPU needed. The bottleneck is KC extraction in the pipeline (LLM call), not the tracking itself.

2. **Storage**: Each KC state is ~100 bytes. 10,000 KCs = 1MB. Trivial for AsyncStorage.

3. **Real-time**: Scoring an article's novelty requires looking up ~10 KC states and computing retrievability. Sub-millisecond.

4. **Incremental**: New articles add new KCs. No retraining needed. Just add entries to the KC state map.

### Comparison to Current Petrarca Interest Model

The current `interest-model.ts` tracks **topics** (broad/specific/entity) with signal counts and Bayesian-smoothed scores with 30-day decay. The proposed KT model differs in:

| Current Model | Proposed KT Model |
|---------------|-------------------|
| Tracks interest in topics | Tracks mastery of specific knowledge claims |
| Binary signals (positive/negative) | Continuous absorption probability |
| Simple exponential decay | FSRS power-law decay with stability concept |
| No inter-topic relationships | KC graph with prerequisite/transfer relationships |
| One score per topic | Separate interest AND knowledge scores |
| No concept of forgetting modeled properly | Explicit forgetting with retrievability computation |

The two models are **complementary**, not competing:
- **Interest model**: "Does the user WANT to read about this?" (preference tracing)
- **Knowledge model**: "Does the user already KNOW this?" (knowledge tracing)
- **Feed ranking**: combines both -- surface articles that are interesting AND novel

---

## 13. Sources

### BKT and Foundations
- [Bayesian Knowledge Tracing - Wikipedia](https://en.wikipedia.org/wiki/Bayesian_knowledge_tracing)
- [Standard BKT Models](https://iedms.github.io/standard-bkt/)
- [Individualized BKT (Yudelson, Koedinger, Gordon, CMU)](https://www.cs.cmu.edu/~ggordon/yudelson-koedinger-gordon-individualized-bayesian-knowledge-tracing.pdf)
- [pyBKT Library (GitHub)](https://github.com/CAHLR/pyBKT)
- [pyBKT Paper (arXiv)](https://arxiv.org/abs/2105.00385)
- [Introduction to BKT with pyBKT (MDPI)](https://www.mdpi.com/2624-8611/5/3/50)
- [Parametric Constraints for BKT (arXiv)](https://arxiv.org/pdf/2401.09456)
- [BKT Emergent Mind Topic](https://www.emergentmind.com/topics/bayesian-knowledge-tracing-bkt)

### Deep Knowledge Tracing
- [Deep Knowledge Tracing (Piech et al., Stanford)](https://stanford.edu/~cpiech/bio/papers/deepKnowledgeTracing.pdf)
- [DKT PyTorch Implementation (GitHub)](https://github.com/shinyflight/Deep-Knowledge-Tracing)
- [DKT PyTorch Technical Analysis (Oreate AI)](https://www.oreateai.com/blog/implementation-and-technical-analysis-of-the-deep-knowledge-tracing-dkt-model-in-pytorch/4aa126d2ccf975728cc6108737fe4d1f)
- [Practical Evaluation of DKT Models (EDM 2025)](https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.industry-papers.46/index.html)
- [Going Deeper with DKT (EDM 2016)](https://www.educationaldatamining.org/EDM2016/proceedings/paper_133.pdf)

### Modern KT Variants
- [Context-Aware AKT (Ghosh et al., KDD 2020)](https://people.umass.edu/~andrewlan/papers/20kdd-akt.pdf)
- [SAKT Paper (ERIC)](https://files.eric.ed.gov/fulltext/ED599186.pdf)
- [DKVMN Paper (arXiv)](https://arxiv.org/abs/1611.08108)
- [DKVMN GitHub](https://github.com/jennyzhang0215/DKVMN)
- [Domain Knowledge-Informed Attention KT (arXiv 2025)](https://arxiv.org/html/2501.05605v1)
- [ELAKT: Enhancing Locality for AKT (ACM TOIS)](https://dl.acm.org/doi/10.1145/3652601)
- [Towards Robust KT via k-Sparse Attention (arXiv)](https://arxiv.org/html/2407.17097v1)

### Comprehensive Surveys
- [KT Survey: Models, Variants, Applications (arXiv)](https://arxiv.org/html/2105.15106v4)
- [Knowledge Tracing: A Survey (ACM Computing Surveys)](https://dl.acm.org/doi/10.1145/3569576)
- [Deep Learning Based KT: Review of Literature (ACM 2025)](https://dl.acm.org/doi/10.1145/3729605.3729620)
- [Explainable KT Survey (Applied Intelligence)](https://link.springer.com/article/10.1007/s10489-024-05509-8)

### Reading and Passive Learning
- [Comprehension Factor Analysis (Thaker et al., LAK 2019)](https://dl.acm.org/doi/10.1145/3303772.3303817)
- [Dynamic Knowledge Modeling with Heterogeneous Activities (Thaker)](https://sites.pitt.edu/~peterb/indepstudies/2990-KhushbooThaker-Spring2018.pdf)
- [Reading Time, Scrolling and Interaction (Implicit Feedback)](https://www.researchwithnj.com/en/publications/reading-time-scrolling-and-interaction-exploring-implicit-sources/)
- [Implicit Feedback: Using Behavior to Infer Relevance (Springer)](https://link.springer.com/chapter/10.1007/1-4020-4014-8_9)
- [Implicit Feedback Bibliography (Kelly & Teevan)](http://teevan.org/publications/papers/sigir-forum03.pdf)

### Knowledge Component Discovery
- [KCluster: LLM-Based KC Discovery (EDM 2025)](https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.long-papers.64/index.html)
- [KCluster Paper (arXiv)](https://arxiv.org/abs/2505.06469)
- [dAFM: Q-Matrix Refinement (JEDM)](https://jedm.educationaldatamining.org/index.php/JEDM/article/view/314)
- [KC-Finder for Programming (EDM 2023)](https://educationaldatamining.org/EDM2023/proceedings/2023.EDM-long-papers.3/index.html)
- [LLMs for Educational Concept Extraction (MDPI 2025)](https://www.mdpi.com/2504-4990/7/3/103)
- [Core Concept Identification via KGs and LLMs (Springer)](https://link.springer.com/article/10.1007/s42979-024-03341-y)
- [LLMs for KC-Level Labeling (arXiv)](https://arxiv.org/html/2602.17542v1)

### Forgetting and Memory Models
- [Forgetting Curve (Wikipedia)](https://en.wikipedia.org/wiki/Forgetting_curve)
- [FSRS Algorithm Overview (DeepWiki)](https://deepwiki.com/open-spaced-repetition/rs-fsrs/3.1-fsrs-algorithm-overview)
- [FSRS Technical Explanation (Expertium)](https://expertium.github.io/Algorithm.html)
- [FSRS Algorithm Wiki (GitHub)](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm)
- [ABC of FSRS (GitHub Wiki)](https://github.com/open-spaced-repetition/fsrs4anki/wiki/abc-of-fsrs)
- [FSRS Repository (GitHub)](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler)
- [Replication of Ebbinghaus Forgetting Curve (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4492928/)

### Preference Tracing and Recommendation
- [From Knowledge Tracing to Preference Tracing (ScienceDirect 2025)](https://www.sciencedirect.com/science/article/abs/pii/S1567422325000523)
- [KT-like Approach to Dynamic User Preferences (IEEE 2025)](https://ieeexplore.ieee.org/document/10857049/)
- [Knowledge-Aware News Recommendation Survey (Iana et al., 2024)](https://journals.sagepub.com/doi/10.3233/SW-222991)

### Novelty Detection
- [Novelty Detection from NLP Perspective (Computational Linguistics, MIT)](https://direct.mit.edu/coli/article/48/1/77/108847/Novelty-Detection-A-Perspective-from-Natural)
- [Novelty and Redundancy Detection in Adaptive Filtering (SIGIR 2002)](https://dl.acm.org/doi/10.1145/564376.564393)
- [Predicting Document Novelty (KAIS 2023)](https://link.springer.com/article/10.1007/s10115-023-01989-1)

### Graph-Based KT and Prerequisites
- [Structure-based Knowledge Tracing (SKT)](http://home.ustc.edu.cn/~tongsw/files/SKT.pdf)
- [Graph-Enhanced Multi-Activity KT (NSF)](https://par.nsf.gov/servlets/purl/10434441)
- [Concept Graph Learning (CMU)](https://www.cs.cmu.edu/~jgc/publication/conceptgraphs.pdf)
- [GNN for Concept Prerequisite Extraction (ACM CIKM 2023)](https://dl.acm.org/doi/10.1145/3583780.3614761)
- [Inferring Prerequisite Knowledge (arXiv 2025)](https://arxiv.org/pdf/2509.05393)

### Lightweight/Efficient KT
- [FlatFormer: Flat Transformer for KT (arXiv)](https://arxiv.org/pdf/2512.06629)
- [Deep KT with Learning Curves (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10097988/)
