arXiv:2603.01234v1 [cs.CL] 5 Mar 2026

The Geometry of Meaning: Topological Structure in Large Language Model
Representations

Sarah Chen1,2∗, James Liu1, Maria Santos3
1Department of Computer Science, Stanford University
2Google DeepMind
3MIT CSAIL

∗Corresponding author: schen@cs.stanford.edu

Abstract

We present a novel analysis of the internal rep-
resentations of large language models through the
lens of algebraic topology. By applying persis-
tent homology to the activation spaces of trans-
former layers, we discover that semantic meaning
is encoded in topological features that are remark-
ably consistent across model scales. Specifically,
we find that (1) conceptually related tokens form
connected components in activation space, (2) anal-
ogies correspond to 1-dimensional homological fea-
tures, and (3) hierarchical relationships create nested
simplicial complexes. Our findings suggest that
the geometric structure of meaning in neural net-
works mirrors mathematical structures identified
in cognitive science and linguistics.

1    Introduction

The success of large language models (LLMs) in
natural language processing has raised fundamental
questions about how these models represent mean-
ing. While prior work has examined individual neu-
rons [1], attention patterns [2], and linear probes [3],
relatively little is known about the global geometric
structure of learned representations.

In this paper, we apply tools from algebraic topol-
ogy — specifically persistent homology and sim-
plicial complexes — to analyze the activation spaces
of transformer models ranging from 125M to 70B
parameters. We focus on three families of models:
GPT-2/3/4, LLaMA 1/2/3, and the Gemini series.

Our key contributions:
• We demonstrate that semantic relationships are

encoded as topological invariants, not just as dis-
tances or directions in activation space.

• We show that these topological features are con-
sistent across model scales, suggesting universal
geometric principles of meaning representation.

• We provide a mathematical framework connecting
our findings to established theories in cognitive
semantics.

2    Background

2.1    Persistent Homology

Given a point cloud X ⊂ Rn, persistent homol-
ogy tracks the birth and death of topological fea-
tures (connected components, loops, voids) as we
vary a scale parameter ε. The resulting persistence
diagram D = {(bi, di)} summarizes the topological
structure of X across scales.

Chen et al.                    — 1 —                    March 2026

Definition 2.1. The Vietoris-Rips complex at
scale ε is:

    VR(X, ε) = {σ ⊂ X : diam(σ) ≤ ε}

2.2    Transformer Representations

For a transformer with L layers, we denote the
hidden state at layer l for token position t as h_l^t ∈
Rd. We focus on the residual stream representa-
tions after each attention block.

3    Methodology

We extract activations from the residual stream at
each transformer layer for a curated set of 10,000
English words. For each layer, we:

1. Construct the Vietoris-Rips filtration
2. Compute persistence diagrams using Ripser [4]
3. Analyze the resulting topological features

Table 1: Models analyzed in this study.

Model         | Params  | Layers | d_model
GPT-2         | 124M    | 12     | 768
GPT-3 Ada     | 350M    | 24     | 1024
LLaMA-2 7B    | 6.7B    | 32     | 4096
LLaMA-3 70B   | 70.6B   | 80     | 8192
Gemini Nano   | ~3.25B  | 26     | 2560

4    Results

4.1    Connected Components Encode Concepts

At early layers (l < L/4), the 0-dimensional per-
sistence diagram reveals clear clusters correspond-
ing to semantic categories. Figure 1 shows that
words for animals, colors, and professions form
distinct connected components with high persis-
tence values.

Chen et al.                    — 2 —                    March 2026

Remarkably, these clusters are preserved across
model scales. The Wasserstein distance between per-
sistence diagrams from GPT-2 and LLaMA-3 70B
(at corresponding relative layer depths) is signifi-
cantly smaller than random baselines (p < 0.001).

4.2    Analogies as Homological Features

We find that classic analogy relationships (king:
queen :: man:woman) correspond to 1-dimensional
homological features — persistent loops in the acti-
vation space. These loops appear in middle layers
(L/4 < l < 3L/4) and are most pronounced in mod-
els with ≥1B parameters.

4.3    Hierarchical Structure

Taxonomic relationships (e.g., poodle → dog →
mammal → animal) create nested simplicial com-
plexes. We formalize this using the notion of filtra-
tion-preserving maps between subcomplexes.

5    Discussion

Our findings connect to the "conceptual spaces"
framework of Gärdenfors [5] and the geometric
approach to semantics proposed by Erk [6]. The
key insight is that topological features provide a
scale-invariant description of meaning that comple-
ments existing metric-based analyses.

6    Conclusion

We have shown that the internal representations of
LLMs possess rich topological structure that encodes
semantic meaning in a principled and consistent man-
ner. This opens new avenues for understanding, in-
terpreting, and improving language models.

Acknowledgments

SC was supported by a Google PhD Fellowship. JL
acknowledges support from NSF Grant #2345678.
We thank Alex Turner and Neel Nanda for helpful
discussions.

Chen et al.                    — 3 —                    March 2026

References

[1] Bau, D., et al. "Identifying and controlling impor-
tant neurons in neural machine translation." ICLR 2019.

[2] Clark, K., et al. "What does BERT look at? An
analysis of BERT's attention." BlackboxNLP 2019.

[3] Belinkov, Y. "Probing classifiers: Promises, short-
comings, and advances." Computational Linguistics 2022.

[4] Bauer, U. "Ripser: efficient computation of
Vietoris-Rips persistence barcodes." JACT 2021.

[5] Gärdenfors, P. "Conceptual Spaces: The Geometry
of Thought." MIT Press, 2000.

[6] Erk, K. "What do you know about an alligator when
you know the company it keeps?" Semantics and Prag-
matics, 2012.

A    Appendix: Implementation Details

All experiments were run on a cluster with 8× A100
GPUs. We used PyTorch 2.2 and the Giotto-TDA li-
brary for persistent homology computations. Repro-
duction code is available at github.com/schen/topo-llm.
