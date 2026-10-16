# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regenerate the committed churn fixture CSVs (deterministic, seed 42).

The datasets are sized for behavioral test runs: large enough that Quick-mode
AutoML partitioning is stable (DataRobot needs >=20 rows; tiny datasets flake
on minority-class-per-fold), small enough that runtime is dominated by fixed
AutoML overhead rather than rows. A signal is planted (month-to-month
contracts + low tenure + high charges + support tickets => churn) so
leaderboards measure something real instead of noise.

Run from this directory:  python3 generate_fixtures.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 42
TRAIN_ROWS = 300
HOLDOUT_ROWS = 60

CONTRACTS = ["Month-to-month", "One year", "Two year"]
PAYMENT_METHODS = ["Electronic check", "Mailed check", "Bank transfer", "Credit card"]
INTERNET = ["DSL", "Fiber optic", "No"]

HEADER = [
    "customer_id",
    "tenure_months",
    "monthly_charges",
    "total_charges",
    "contract_type",
    "payment_method",
    "internet_service",
    "num_support_tickets",
    "has_paperless_billing",
    "churn",
]


def _row(rng: random.Random, index: int, with_target: bool) -> list[str]:
    tenure = rng.randint(1, 72)
    monthly = round(rng.uniform(20.0, 120.0), 2)
    total = round(monthly * tenure * rng.uniform(0.9, 1.0), 2)
    contract = rng.choices(CONTRACTS, weights=[5, 3, 2])[0]
    payment = rng.choice(PAYMENT_METHODS)
    internet = rng.choices(INTERNET, weights=[4, 4, 2])[0]
    tickets = rng.choices([0, 1, 2, 3, 5, 8], weights=[40, 25, 15, 10, 7, 3])[0]
    paperless = rng.choice(["Yes", "No"])

    # Planted signal so the target is learnable on a small dataset.
    churn_score = (
        (1.4 if contract == "Month-to-month" else 0.0)
        + (1.0 if tenure < 12 else 0.0)
        + (0.8 if monthly > 85 else 0.0)
        + 0.35 * tickets
        + rng.uniform(0.0, 1.4)
    )
    churn = "Yes" if churn_score > 2.6 else "No"

    row = [
        f"CUST-{index:05d}",
        str(tenure),
        f"{monthly:.2f}",
        f"{total:.2f}",
        contract,
        payment,
        internet,
        str(tickets),
        paperless,
    ]
    if with_target:
        row.append(churn)
    return row


def _write(
    path: Path, rows: int, start_index: int, with_target: bool, rng: random.Random
) -> None:
    header = HEADER if with_target else HEADER[:-1]
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(rows):
            writer.writerow(_row(rng, start_index + i, with_target))
    print(f"wrote {path} ({rows} rows)")


def main() -> None:
    here = Path(__file__).parent
    rng = random.Random(SEED)
    _write(here / "churn_train.csv", TRAIN_ROWS, 0, with_target=True, rng=rng)
    _write(
        here / "churn_holdout.csv", HOLDOUT_ROWS, TRAIN_ROWS, with_target=False, rng=rng
    )


if __name__ == "__main__":
    main()
