#!/usr/bin/env python3
"""Read-only helper to list PDF links exposed by frozen AL-SP norm pages."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from lxml import html


ROOT = Path(__file__).resolve().parents[1]


def discover(target: dict[str, str]) -> dict[str, object]:
    page_url = f"https://www.al.sp.gov.br/norma/{target['norm_id']}"
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required")
    completed = subprocess.run(
        [curl, "-L", "--fail", "--silent", "--show-error", "--max-time", "30", page_url],
        check=True,
        capture_output=True,
        timeout=35,
    )
    document = html.fromstring(completed.stdout)
    links = sorted(
        {
            urljoin(page_url, anchor.get("href"))
            for anchor in document.xpath("//a[@href]")
            if ".pdf" in anchor.get("href", "").lower()
        }
    )
    return {"norm_id": target["norm_id"], "page_url": page_url, "pdf_urls": links}


def main() -> int:
    config = json.loads((ROOT / "evals/state_metadata_targets_v1.json").read_text())
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(discover, config["targets"]))
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
