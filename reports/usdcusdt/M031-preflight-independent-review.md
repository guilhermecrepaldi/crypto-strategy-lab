# M031 independent pre-run review

STATUS=BLOCK_PRE_RUN
REVIEWER=gpt-6-astra
REVIEW_DATE=2026-09-10
MODEL=M031

The source-bound review stopped M031 before registration and before any historical
economic event. The frozen M026 whole-USDC sizing rule makes the proposed geometry
cost more despite equal slot counts. M030's BUY-side rank-weight is 360 coarse
ticks; M031's is 235. Concentration therefore raises the cash required for the same
70 whole-USDC BUY units by exactly `125 × 0.0001 = 0.0125 USDT`.

At the shared synthetic book bid 1.0019 / ask-hotline 1.0020, M030 needs
78.1040 USDT + 78 USDC, while M031 needs 78.1165 USDT + 78 USDC. There is no
normalization that preserves simultaneously the exact M030 bank, all 48 initial
M031 orders, the frozen prices/whole-USDC quantities and 8-unit mobility reserve.
Capital-normalized reporting after the run would not repair unequal initialization.

A common bank of 78.1165 USDT + 78 USDC is a valid matched-control design, but it
adds 0.0125 USDT versus M030 and therefore requires OWNER authorization. Keeping
the original M030 bank instead requires explicitly allowing incomplete initial M031
funding. The reviewer also requires, after OWNER resolves the capital constraint,
full M030 manager-audit parity, exact ACK/pool reconstruction, exact C4 trade-budget
reconstruction and synthetic M030 default/checkpoint equivalence before replay.

No strategy or software pass is issued. M031 remains unregistered and blocked.
