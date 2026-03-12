Production deployment assets for the published web app.

Files here are intentionally stable, checked-in deploy inputs rather than transient
training artifacts from `artifacts/`.

Current default champion:
- `hex6_champion.pt`

Source checkpoint:
- `artifacts/alphazero_cycle_local_strongest_v2_gumbel_drawfocus/cycle_002/bootstrap_model.pt`

When a new model is promoted for production:
1. Copy the new checkpoint here as `hex6_champion.pt`
2. Redeploy the web app
3. Update this file and any deployment notes if the source run changed
