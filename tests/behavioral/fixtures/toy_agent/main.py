# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entrypoint for the toy churn Q&A agent (behavioral-test fixture)."""

from agent import build_graph


def main() -> None:
    app = build_graph()
    result = app.invoke(
        {"question": "Why do customers churn?", "context": "", "answer": ""}
    )
    print(result["answer"])


if __name__ == "__main__":
    main()
