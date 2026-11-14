"""Generate and append backend code coverage summary to GitHub Actions Step Summary."""

import os
import sys

try:
    import defusedxml.etree.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]


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


def generate_coverage_summary(xml_path: str = "coverage.xml") -> None:
    """Parse coverage XML report and append summary table to GITHUB_STEP_SUMMARY."""
    if not os.path.isfile(xml_path):
        print(f"[Coverage] File not found: {xml_path}")
        return

    # 1. Parse XML and format markdown (isolated parsing error handling)
    try:
        tree = ET.parse(xml_path)
        summary_content = format_coverage_summary(tree.getroot())
    except Exception as exc:
        print(f"[Coverage] Summary parsing skipped: {exc}", file=sys.stderr)
        return

    # 2. Write to Step Summary (file write errors propagate to fail the step if write fails)
    if summary_file := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(summary_content)
    else:
        print(summary_content)


if __name__ == "__main__":
    xml_file = sys.argv[1] if len(sys.argv) > 1 else "coverage.xml"
    generate_coverage_summary(xml_file)
