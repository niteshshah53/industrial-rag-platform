"""
Seed the Industrial RAG Platform with a demo hydraulic system manual.

Generates a realistic PDF technical manual, uploads it to the API, and waits
for ingestion to complete. Run this before the evaluation pipeline.

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --base-url http://localhost:8000

Run via Makefile:
    make demo

Prerequisites:
    - Platform running: make dev
    - fpdf2 installed: included in dev dependencies
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

# ── Demo document content ─────────────────────────────────────────────────────

MANUAL_SECTIONS = [
    (
        "HYDRAULIC SYSTEM MAINTENANCE MANUAL\n"
        "Model: HY-850 Industrial Hydraulic Unit\n"
        "Document: HY-850-MAN-001 Rev. 3\n\n"
        "IMPORTANT: Read all safety warnings before performing maintenance.\n"
        "Keep this manual accessible to all personnel operating or maintaining this equipment."
    ),
    (
        "Section 1: System Overview\n\n"
        "The HY-850 hydraulic system is designed for continuous industrial operation. "
        "The system consists of a variable-displacement piston pump, hydraulic reservoir, "
        "pressure relief valve, high-pressure filter assembly, oil cooler, and actuator circuit.\n\n"
        "Normal Operating Pressure Range: 150 to 200 bar.\n"
        "Maximum System Pressure: 250 bar (relief valve setting).\n"
        "Hydraulic Reservoir Capacity: 120 litres.\n"
        "Hydraulic Pump Speed: 1450 to 1500 RPM at full load.\n"
        "Pump Flow Rate: 85 litres per minute at rated speed."
    ),
    (
        "Section 2: Temperature Specifications\n\n"
        "Maximum Operating Temperature: The hydraulic system must not exceed 85 degrees "
        "Celsius during normal operation. Sustained temperatures above 80 degrees Celsius "
        "will degrade hydraulic fluid viscosity and reduce system performance. "
        "Install a temperature gauge at the reservoir inlet and monitor continuously.\n\n"
        "Minimum Fluid Temperature: The hydraulic fluid temperature must be at least "
        "10 degrees Celsius before the system is operated at full load. "
        "Operating below this temperature increases fluid viscosity and can cause pump cavitation. "
        "Use the low-pressure warm-up procedure described in Section 7."
    ),
    (
        "Section 3: Hydraulic Fluid Specification\n\n"
        "Approved Fluid: Use only ISO VG 46 hydraulic oil or an approved equivalent "
        "as specified in the parts manual. Do not mix different fluid grades or brands.\n\n"
        "Fluid Change Interval: Replace hydraulic fluid every 2000 operating hours "
        "or annually, whichever comes first. Drain the system completely before refilling "
        "to prevent contamination from degraded fluid.\n\n"
        "Fluid Volume: The system requires 120 litres of hydraulic oil. "
        "Check the sight glass at the reservoir before each operating shift. "
        "Top up only with the specified fluid. Maintain level between MIN and MAX marks."
    ),
    (
        "Section 4: Pressure Relief Valve\n\n"
        "Factory Setting: The pressure relief valve is factory-set to 250 bar and must not "
        "be adjusted under any circumstances. Altering this setting voids the warranty "
        "and creates a safety hazard.\n\n"
        "Inspection Interval: Inspect the pressure relief valve quarterly for signs of "
        "wear, corrosion, or internal leakage. A valve that opens below the set pressure "
        "or fails to close completely must be replaced immediately.\n\n"
        "Replacement Interval: Replace the pressure relief valve every 5000 operating hours "
        "or at the first sign of performance degradation, whichever comes first."
    ),
    (
        "Section 5: Filter Maintenance\n\n"
        "High-Pressure Filter Inspection: Inspect the high-pressure filter element "
        "every 500 operating hours. Check the differential pressure indicator on the "
        "filter housing. A red indicator shows the element is blocked and must be replaced.\n\n"
        "Filter Element Replacement: Replace the filter element when the differential "
        "pressure indicator triggers, or during each annual service regardless of "
        "apparent condition. Never clean and reuse a filter element.\n\n"
        "Filter Housing Bolt Torque: Tighten filter housing bolts to 45 Nm using a "
        "calibrated torque wrench. Do not exceed this torque; overtightening damages "
        "the housing seals.\n\n"
        "Return Filter: Inspect the return-line filter element every 1000 operating hours. "
        "Replace with the specified OEM element only."
    ),
    (
        "Section 6: Actuator and Seal Maintenance\n\n"
        "Seal Inspection: Inspect actuator seals for wear, cracking, and extrusion "
        "every 1000 operating hours. Early replacement of worn seals prevents "
        "contamination of the hydraulic fluid and costly actuator damage.\n\n"
        "Actuator Servicing: When replacing seals, thoroughly clean the actuator bore "
        "with lint-free cloths and fresh hydraulic fluid. Inspect the rod surface for "
        "scoring; a scored rod damages new seals immediately."
    ),
    (
        "Section 7: Oil Cooler and Thermal Management\n\n"
        "Oil Cooler Inspection: Inspect the oil cooler for blockages and leaks every "
        "1000 operating hours. Clean external fins with compressed air to maintain "
        "heat-transfer efficiency. Internal blockages require professional flushing.\n\n"
        "Overheating: Hydraulic system overheating is typically caused by a malfunctioning "
        "oil cooler, a low oil level, or excessive system load. If the temperature alarm "
        "activates, shut down the system and allow it to cool before investigating the cause."
    ),
    (
        "Section 8: Hose and Fitting Inspection\n\n"
        "Hose Inspection Interval: Inspect all hydraulic hoses for cracks, abrasion, "
        "swelling, kinks, and connector leaks every 250 operating hours. "
        "Replace any hose showing external damage; do not attempt repair.\n\n"
        "High-Pressure Fittings: Check all high-pressure fittings for seepage at "
        "each hose inspection. Tighten loose fittings to the specified torque only; "
        "overtightening damages threads and sealing faces."
    ),
    (
        "Section 9: Safety Procedures\n\n"
        "Depressurisation: Always depressurise the hydraulic system completely before "
        "performing any maintenance work. Use the manual pressure-relief procedure in "
        "the control panel before opening any hydraulic connection.\n\n"
        "Personal Protective Equipment: Wear hydraulic-rated gloves and eye protection "
        "at all times when working near high-pressure hydraulic lines. High-pressure "
        "fluid injection injuries are life-threatening; even a pinhole leak is dangerous.\n\n"
        "Lockout/Tagout: Apply lockout/tagout to the main drive motor before opening "
        "the hydraulic circuit. Ensure all stored energy (accumulators, pressure in lines) "
        "is fully discharged before disconnecting any fittings."
    ),
    (
        "Section 10: Troubleshooting\n\n"
        "Low System Pressure: A drop in system pressure below nominal (150 bar) is "
        "typically caused by a blocked high-pressure filter, a worn pump with excessive "
        "internal leakage, or a pressure relief valve malfunction. Check these components "
        "in this order before replacing more expensive parts.\n\n"
        "Excessive Noise: Cavitation noise (rattling or grinding) from the pump indicates "
        "insufficient fluid in the reservoir, a clogged suction strainer, or fluid "
        "viscosity too high for the ambient temperature. Check fluid level and temperature first.\n\n"
        "Fluid Contamination: Discoloured or milky fluid indicates water contamination. "
        "Drain and replace the fluid immediately. Do not operate the system with "
        "contaminated fluid as it accelerates wear in all components."
    ),
    (
        "Section 11: Start-Up After Long-Term Storage\n\n"
        "Pre-Start Inspection: Before starting after storage exceeding 90 days, inspect "
        "all hoses, seals, and fittings for deterioration. Drain and replace hydraulic "
        "fluid regardless of service hours elapsed.\n\n"
        "Warm-Up Procedure: After long-term storage, circulate the oil at low pressure "
        "for at least 10 minutes before applying full load. This allows the fluid to "
        "reach operating temperature and ensures all seals are properly seated."
    ),
    (
        "Section 12: Warranty and Service Information\n\n"
        "Warranty Period: The HY-850 hydraulic system carries a 24-month warranty "
        "from the date of commissioning. The warranty covers manufacturing defects "
        "in materials and workmanship.\n\n"
        "Warranty Exclusions: The warranty does not cover damage caused by incorrect "
        "fluid specification, failure to follow maintenance intervals, or operation "
        "outside the specified pressure and temperature limits. "
        "Unauthorised adjustments to the pressure relief valve void the warranty immediately.\n\n"
        "Authorised Service Centres: Only authorised service centres may perform warranty "
        "repairs. Contact your regional distributor for the nearest authorised centre."
    ),
]


# ── PDF generation ────────────────────────────────────────────────────────────


def generate_manual_pdf() -> bytes:
    """Generate the hydraulic system manual PDF using fpdf2."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    for section_text in MANUAL_SECTIONS:
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, section_text)

    return bytes(pdf.output())


# ── Upload helpers ────────────────────────────────────────────────────────────


def upload_document(base_url: str, pdf_bytes: bytes, filename: str) -> str:
    """Upload a PDF to the platform and return its document_id."""
    response = httpx.post(
        f"{base_url}/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["document_id"]


def wait_for_ready(base_url: str, document_id: str, max_wait: int = 120) -> str:
    """
    Poll until the document reaches READY or FAILED status.

    Returns the final status string.
    """
    for _ in range(max_wait // 2):
        resp = httpx.get(f"{base_url}/v1/documents/{document_id}", timeout=10.0)
        resp.raise_for_status()
        status = resp.json()["status"]
        if status in ("READY", "FAILED"):
            return status
        time.sleep(2)
    return "TIMEOUT"


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo documents into the RAG platform.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="RAG API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-upload even if a document with the same content already exists.",
    )
    args = parser.parse_args()

    print()
    print("Industrial RAG Platform — Demo Data Seeding")
    print("=" * 50)

    # Check API is available
    try:
        r = httpx.get(f"{args.base_url}/v1/health/live", timeout=5.0)
        r.raise_for_status()
        print(f"  ✓ API reachable at {args.base_url}")
    except Exception as e:
        print(f"  ✗ API unreachable: {e}")
        print("  Start the platform with: make dev")
        return 1

    # Generate PDF
    print("\nGenerating hydraulic_system_manual.pdf...")
    pdf_bytes = generate_manual_pdf()
    print(f"  Generated {len(pdf_bytes):,} bytes ({len(MANUAL_SECTIONS)} pages)")

    # Upload
    print("\nUploading document...")
    try:
        doc_id = upload_document(args.base_url, pdf_bytes, "hydraulic_system_manual.pdf")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409 and not args.force:
            print("  ○ Document already exists (SHA-256 match).")
            print("  Use --force to re-upload anyway.")
            return 0
        raise

    print(f"  ✓ Uploaded — document_id: {doc_id}")

    # Wait for ingestion
    print("  Waiting for ingestion to complete (this may take 30–90 seconds)...")
    status = wait_for_ready(args.base_url, doc_id)

    if status == "READY":
        # Get chunk count
        resp = httpx.get(f"{args.base_url}/v1/documents/{doc_id}", timeout=10.0)
        chunk_count = resp.json().get("chunk_count", "?")
        print(f"  ✓ Ingestion complete — {chunk_count} chunks stored in Qdrant")
        print()
        print("  Demo document is ready. Run evaluation with:")
        print("    make eval")
        print("    python evaluation/run_ragas.py")
    elif status == "FAILED":
        resp = httpx.get(f"{args.base_url}/v1/documents/{doc_id}", timeout=10.0)
        error = resp.json().get("error_message", "unknown error")
        print(f"  ✗ Ingestion failed: {error}")
        print("  Check Ollama is running and nomic-embed-text is available:")
        print("    make pull-models")
        return 1
    else:
        print(f"  ✗ Timed out waiting for ingestion (status: {status})")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
