# Frozen RestockIQ demand artifact

- Version: `restockiq-demand-v1-a067286b7c1e`
- Training cutoff: `2024-05-31`
- Training data hash: `a067286b7c1e966de43f3db9e1d24a7f8a440d236d94c24365c6d717ca44399c`
- Oracle fields used as features: none
- Contents: one censor-aware reconstruction model and nine direct cumulative quantile models for H1/H7/H14 × Q10/Q50/Q90

`SHA256SUMS` is checked during the backend image build and by:

```bash
python -m app.ml.verify_release_artifacts
```

Do not replace individual model files. Retraining is a new artifact release and must update the manifest, checksums, evaluation evidence, and model version together.
