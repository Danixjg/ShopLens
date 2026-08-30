# Research attribution

## Clarification-question value

ShopLens's expected-question-value experiment is inspired by:

> Sudha Rao and Hal Daumé III. 2018. *Learning to Ask Good Questions: Ranking Clarification Questions using Neural Expected Value of Perfect Information.*
> Proceedings of the 56th Annual Meeting of the Association for Computational
> Linguistics (Volume 1: Long Papers), pages 2737–2746. Association for
> Computational Linguistics.

- Canonical publication: https://aclanthology.org/P18-1255/
- DOI: https://doi.org/10.18653/v1/P18-1255
- Paper license: Creative Commons Attribution 4.0 International (CC BY 4.0)

The ShopLens implementation is an independent, deterministic adaptation of
the paper's expected-value framing to the competition's fixed
`ask_attribute` contract. It does not reproduce the paper's neural model and
does not copy its source code, training data, annotations, or model weights.
The converted local transcript is research material only, remains Git-ignored,
and is not part of the public release bundle.

## Conversational product-search benchmarking

ShopLens's clarification-quality guards and its evaluation reporting
discipline are informed by:

> Jingheng Ye, Yong Jiang, Xiaobin Wang, Yinghui Li, Yangning Li, Hai-Tao
> Zheng, Pengjun Xie, and Fei Huang. 2024. *ProductAgent: Benchmarking
> Conversational Product Search Agent with Asking Clarification Questions*.
> arXiv:2407.00942 [cs.IR].

- arXiv abstract page: https://arxiv.org/abs/2407.00942
- DOI: https://doi.org/10.48550/arXiv.2407.00942
- Paper license: arXiv non-exclusive distribution license 1.0

That license is an agreement between the authors and arXiv. Unlike the CC BY
4.0 source above, it grants no third-party right to redistribute the paper or
publish a derivative conversion of it, so no copy or conversion is tracked
here. ShopLens contains no ProductAgent code and no AliMe KG records, and runs
no language model, SQL statistics tool, or user simulator. What is taken from
the paper is a set of documented failure modes and reporting rules,
implemented independently. See
[ProductAgent source audit](productagent-integration.md) for the license
finding and the adopt/evaluate/defer boundary.
