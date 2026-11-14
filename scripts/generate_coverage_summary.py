"""Generate and append backend code coverage summary to GitHub Actions Step Summary."""

import os
import sys
from typing import Optional

import defusedxml.ElementTree as ET


def format_coverage_summary(root: ET.Element) -> str:
    """Format coverage metrics from XML root element into markdown table."""
    rate = float(root.attrib.get("line-rate", 0)) * 100
    branch_rate = float(root.attrib.get("branch-rate", 0)) * 100
    lines_valid = root.attrib.get("lines-valid", "N/A")
    lines_covered = root.attrib.get("lines-covered", "N/A")

    return "\n".join(
        [
            "### 📊 Backend Code Coverage Report\n",
            "| Metric | Value |",
            "|:---|:---|",
            f"| **Line Coverage** | **{rate:.2f}%** ({lines_covered}/{lines_valid}) |",
            f"| **Branch Coverage** | **{branch_rate:.2f}%** |\n",
        ]
    )


def handle_missing_coverage(summary_file: Optional[str]) -> None:
    """Write unavailable message and generate a fallback artifact when coverage is missing."""
    unavailable_msg = (
        "### ⚠️ Backend Code Coverage Report Unavailable\n\n"
        "> Coverage reports were not generated. Pytest may have failed or exited abruptly before writing reports.\n"
    )
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(unavailable_msg)
    else:
        print(unavailable_msg)

    # Provide fallback artifact file so artifact upload step always succeeds
    os.makedirs("htmlcov", exist_ok=True)
    fallback_file = os.path.join("htmlcov", "report_unavailable.txt")
    with open(fallback_file, "w", encoding="utf-8") as f:
        f.write("Coverage report unavailable: pytest did not produce coverage.xml.\n")


def generate_coverage_summary(xml_path: str = "coverage.xml") -> None:
    """Parse coverage XML report and append summary table to GITHUB_STEP_SUMMARY."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")

    if not os.path.isfile(xml_path):
        handle_missing_coverage(summary_file)
        return

    # 1. Parse XML and format markdown (isolated parsing error handling)
    try:
        tree = ET.parse(xml_path)
        summary_content = format_coverage_summary(tree.getroot())
    except Exception as exc:
        print(f"[Coverage] Summary parsing skipped: {exc}", file=sys.stderr)
        return

    # 2. Write to Step Summary (file write errors propagate to fail the step if write fails)
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(summary_content)
    else:
        print(summary_content)


if __name__ == "__main__":
    xml_file = sys.argv[1] if len(sys.argv) > 1 else "coverage.xml"
    generate_coverage_summary(xml_file)
