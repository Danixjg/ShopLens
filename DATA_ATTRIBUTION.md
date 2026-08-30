# Data Attribution and Use

This competition package is derived from **Amazon Reviews 2023**, published by McAuley Lab at UCSD.

- Project page: https://amazon-reviews-2023.github.io/
- Selected category: `Clothing_Shoes_and_Jewelry`
- Product join key: `parent_asin`
- Competition modality: text and structured product metadata only

The competition package does not contain images, videos, account credentials, private organizer labels, or the private holdout sessions.

Participants must follow the source dataset's applicable terms and use the data only for the competition, research, and other permitted purposes. The competition organizer does not claim ownership of the underlying Amazon review or product content.

## Research-method attribution

Planned dialogue-policy experiments are informed by **TRACER**, introduced by
Xiangci Li, Zhiyu Chen, Jason Ingyu Choi, Nikhita Vedula, Besnik Fetahu, Oleg
Rokhlenko, and Shervin Malmasi in *Wizard of Shopping: Target-Oriented
E-commerce Dialogue Generation with Decision Tree Branching* (ACL 2025).

- Paper: https://aclanthology.org/2025.acl-long.641/
- DOI: https://doi.org/10.18653/v1/2025.acl-long.641
- License for the paper: CC BY 4.0
- Source audit and adoption boundary:
  [docs/wizard-of-shopping-integration.md](docs/wizard-of-shopping-integration.md)

ShopLens currently includes no upstream TRACER code and no Wizard of Shopping
dataset records. The source audit explains why those separately published
artifacts remain excluded pending compatible, explicit reuse terms.

Clarification-quality guards and evaluation reporting rules are additionally
informed by **ProductAgent**, introduced by Jingheng Ye, Yong Jiang, Xiaobin
Wang, Yinghui Li, Yangning Li, Hai-Tao Zheng, Pengjun Xie, and Fei Huang in
*ProductAgent: Benchmarking Conversational Product Search Agent with Asking
Clarification Questions* (arXiv:2407.00942, 2024).

- Paper: https://arxiv.org/abs/2407.00942
- DOI: https://doi.org/10.48550/arXiv.2407.00942
- License for the paper: arXiv non-exclusive distribution license 1.0, which
  grants no third-party redistribution or derivative right
- Source audit and adoption boundary:
  [docs/productagent-integration.md](docs/productagent-integration.md)

ShopLens includes no ProductAgent code and no AliMe KG records. That corpus is
outside the Amazon Reviews 2023 competition package and is not part of the
data pipeline.
