#!/usr/bin/env python3
"""
Boundary test — enforces this product stays fully token-/AI-free and LLM-free. Run: python test_boundary.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
PRODUCT_FILES = ["config.py", "adapter.py", "churn.py", "kpis.py", "signals.py"]
BANNED = ["token", "anthropic", "claude", "llm", "cogs", "generator", "critic", "consumption"]


def main() -> None:
    passed = failed = 0
    for name in PRODUCT_FILES:
        low = (HERE / name).read_text().lower()
        for w in BANNED:
            if re.search(rf"\b{w}\b", low):
                failed += 1
                print(f"  FAIL  {name}: banned term '{w}'")
            else:
                passed += 1

    try:
        import churn  # noqa: F401
        import adapter  # noqa: F401
        import kpis  # noqa: F401
        assert "anthropic" not in sys.modules, "import pulled in anthropic"
        passed += 1
    except Exception as e:  # noqa: BLE001
        failed += 1
        print(f"  FAIL  import check: {e}")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
