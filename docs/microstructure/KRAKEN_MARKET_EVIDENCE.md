# Kraken USDC/USDT market evidence

Observed from Kraken public REST on 2026-09-10 at approximately
23:05:29Z. Raw responses are local ignored evidence under
`data/evidence/kraken/2026-09-10/`.

- REST pair key: `USDCUSDT`; WebSocket/native display: `USDC/USDT`.
- Pair status: `online`; base USDC; quote USDT.
- Tick/price increment: 0.0001; quantity precision: 8 decimals.
- Minimum base quantity: 5 USDC; minimum cost: 0.5 USDT.
- USDC and USDT asset status: `enabled`.
- A public depth snapshot returned non-empty bid and ask sides.

Raw SHA-256:

- AssetPairs: `ba5d214241c1c2589eaf364a68fedbb0f56343f75c19b48f6cc43f4d3b5749f9`
- Assets: `a0cac7487634d3a56fff5870a8850e08ba5fb90f0416ae585547be1ba98ab11b`
- Depth: `a667aeaba4c492cc97d040c7b7a97484c3db64f734da29c47e41360427ab41f7`

Current public rules prove current availability only. They are not applied to a
2025/2026 historical replay without temporal provenance.

Sources: [Kraken Instruments](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/instrument),
[Kraken public AssetPairs](https://api.kraken.com/0/public/AssetPairs?pair=USDCUSDT).
