# M017

MODEL_ID: `M017`
PARENT: `M015`
CREATED_AT: `2026-09-08T15:36:39.568304+00:00`
HYPOTHESIS: Changing only executable protected cap10 to20bps may reduce cap-blocked exposure but can increase reserve erosion.
PROBLEM_OBSERVED: Completed M016 failed sustainability and holding goals; independently reconstructed D2 deadline costs16.812bps while10bps cap bound, reserve and displayed-budget liquidity sufficient at that event.
CHANGE_FROM_PARENT: Actual aggregate protected release budget20bps; normal theoretical H1 cap10 remains unchanged.
EXPECTED_IMPROVEMENT: Measure holding/cycle gains and actual incremental losses under same12 synthetic days,100+10,funding10 andPRICE_PRIORITY.
FULL_STRATEGY_SUMMARY: `{"active_reserve_queues": 0, "calendar_days": 12, "capital_mode": "COMPOUNDING", "currency": "USDT", "deadline_policy_hash": "88b14751e15093cadc6abbaa9f3e1a70e875ff4e884b1cd911cf7146af494224", "deadline_us": 7200000000, "debt_mode": "REPORT_ONLY_NO_FUNDING_STATE_CHANGE", "economic_early_stop": false, "executable_loss_cap_bps": "20", "execution_config_sha256": "a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d", "execution_envelope": "PRICE_PRIORITY", "experimental_control": "M016", "initial_capital": "100", "initial_operating": "100", "initial_reserve": "10", "initial_total_equity": "110", "model_id": "M017", "normal_release": "B10_H1_B10_F2.5", "normal_theoretical_loss_cap_bps": "10", "operating_queues": 1, "owner_withdrawals": false, "phase": "DEVELOPMENT", "position_sizing": "USE_AVAILABLE_OPERATING_BANK", "precedence": "LOSS_CAP_AND_RESERVE_FLOOR_BEFORE_DEADLINE", "preregistration_sha256_lf": "467cc497c78986780c23e427d2ef04ec522bba8cc5f79071f0448b8ee48b3d20", "priority_trade_through": true, "profit_funding": "0.10", "reserve_floor_absolute": "2.5", "scientific_parent": "M015", "selector": "UNCHANGED_M007_HYSTERESIS_AND_AFTER_ORDINARY_EXIT", "source_dates": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-06-01", "2025-08-01", "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-07-01"], "spec_sha256_lf": "d9afab40660e73c56f68601d4617dd76f7d5abb5dd5d2de94e447e387f977e20", "strategy": "B10_PROTECTED_TWO_HOUR_DEADLINE_CAP20", "symbol": "USDCUSDT", "technical_ancestor": "M016", "test_plan": "SYNTHETIC_CONSECUTIVE_12D", "trading_enabled": false}`
FINAL_RESULT: pending
DECISION: pending
REASON: Material loss-budget change with new preregistration; M015/M016 immutable.
