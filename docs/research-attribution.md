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
