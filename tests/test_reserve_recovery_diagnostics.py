from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import analyze_recovery


def row(time: int, *, release: bool = False, profit: str = "0", consumed: str = "0") -> dict:
    return {
        "time_us": time,
        "release": release,
        "net_profit": profit,
        "reserve_consumption": consumed,
    }


def test_fifo_overlapping_debts_and_pending_release_count() -> None:
    result = analyze_recovery(
        [
            row(0, release=True, profit="-0.020", consumed="0.020"),
            row(1, profit="0.010"),
            row(2, release=True, profit="-0.030", consumed="0.030"),
            row(3, profit="0.020"),
            row(4, profit="0.020"),
        ],
        D(1),
        4,
    )
    assert result["recovered_count"] == 2
    assert result["censored_count"] == 0
    assert D(result["outstanding_debt"]) == D("0")
    assert [item["recovery_cycles"] for item in result["tranches"]] == [2, 2]
    assert result["tranches"][0]["new_release_while_pending_count"] == 1
    assert result["tranches"][1]["new_release_while_pending_count"] == 0


def test_surplus_before_a_loss_does_not_pay_future_debt() -> None:
    result = analyze_recovery(
        [
            row(0, profit="0.010"),
            row(1, release=True, profit="-0.020", consumed="0.020"),
            row(2, profit="0.010"),
        ],
        D(1),
        2,
    )
    assert result["surplus_contributions"] == "0.010"
    assert result["outstanding_debt"] == "0.010"
    assert result["effective_reserve"] == "10.000"


@pytest.mark.parametrize(
    "funding, expected_debt, expected_surplus",
    [(D(0), "0.020", "0"), (D(1), "0", "0")],
)
def test_funding_endpoints(funding: D, expected_debt: str, expected_surplus: str) -> None:
    result = analyze_recovery(
        [row(0, release=True, profit="-0.020", consumed="0.020"), row(1, profit="0.020")],
        funding,
        1,
    )
    assert result["outstanding_debt"] == expected_debt
    assert result["surplus_contributions"] == expected_surplus


def test_nonpositive_profit_and_positive_release_cycle_semantics() -> None:
    result = analyze_recovery(
        [
            row(0, release=True, profit="0.010"),
            row(1, profit="0"),
            row(2, profit="-0.001"),
            row(3, profit="0.010"),
        ],
        D("0.5"),
        3,
    )
    assert result["ordinary_positive_cycle_count"] == 1
    assert D(result["total_funding"]) == D("0.010")
    assert result["recovered_count"] == 0
    assert result["settlements"][0]["release"] is True


def test_future_and_unsorted_events_are_rejected() -> None:
    with pytest.raises(ValueError, match="TIME_US_OUT_OF_BOUNDS"):
        analyze_recovery([row(2)], D(1), 1)
    with pytest.raises(ValueError, match="SETTLEMENTS_NOT_CHRONOLOGICAL"):
        analyze_recovery([row(1), row(0)], D(1), 1)


def test_censored_tranche_and_conditional_statistics() -> None:
    result = analyze_recovery(
        [row(0, release=True, profit="-0.020", consumed="0.020"), row(1, profit="0.010")],
        D("0.5"),
        3_600_000_000,
    )
    tranche = result["tranches"][0]
    assert result["recovered_count"] == 0
    assert result["censored_count"] == 1
    assert tranche["recoverytimestamp"] is None
    assert tranche["age_hours"] == "1"
    assert result["median_recovery_cycles"] is None
    assert result["median_recovery_cycles_conditional_on_recovered"] is True


def test_known_first_loss_recovers_in_three_ordinary_cycles_at_eighty_percent() -> None:
    result = analyze_recovery(
        [
            row(0, release=True, profit="-0.0198", consumed="0.0198"),
            row(1, profit="0.0099"),
            row(2, profit="0.0099"),
            row(3, profit="0.0099"),
        ],
        D("0.8"),
        3,
    )
    assert result["tranches"][0]["loss"] == "0.0198"
    assert result["tranches"][0]["remaining"] == "0.00000"
    assert result["tranches"][0]["recovery_cycles"] == 3
    assert result["recovered_count"] == 1
    assert D(result["outstanding_debt"]) == D("0")
    assert result["p90_recovery_cycles"] == 3
