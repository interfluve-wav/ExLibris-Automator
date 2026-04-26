#!/usr/bin/env python3
"""
Test citation parser with multiple citation formats
Usage: Add citations to the CITATIONS list below, then run: python3 test_citations.py
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from automation.presentations import parse_any_citation

# Add your citations here - one per line
CITATIONS = [
    "L.D. Ziemba, R.J. Griffin, C.H. Anderson, J.E. Dibb, S.I. Whitlow, B. Lefer, J. Flynn, and B. Rappenglück, Interaction of gas-phase nitric acid and primary organic aerosol in the atmosphere of Houston, TX, American Association for Aerosol Research Annual Meeting, Reno, NV, September 2007.",
    "Tarantino, N., D. MacDonald, and R. Race, Modeling of a Tethered Ballast Point Absorber Wave Energy Converter.  Presentation at Marine Technology Society Marine Renewable Energy Techsurge, Portsmouth, NH, November 2016.",
    "Tarantino, N., D. MacDonald, and R. Race, Modeling of a Tethered Ballast Point Absorber Wave Energy Converter.  Presentation at Marine Technology Society Marine Renewable Energy Techsurge, Portsmouth, NH, November 2016.",
    "LeSeure, P., Chin, E, Sosa, M. & Zhang, S. (2023, March 23 - 24). The Preliminary Qualitative Survey to Inform the Development of a Diabetes Mobile Application for Portuguese American Population. [Poster Presentation]. The Eastern Nursing Research Society (ENRS) 35th Annual Scientific Sessions, Philadelphia, PA, United States.",
    "Long S., Long, M., Hernandez Cuevas, E., Fuller, T., Rademaker, M., Britton, J., Beard, H., Macrine, S., Soto Bonilla, N., & Fugate, J. (Jan 2025). Translating embodied learning for simulation in clinical psychology: Designing and evaluating skill competency and student confidence. National Institute of Teaching Psychology. Clearwater Beach, FL.",
    "M. Aguiar, B. Grassian, C. Trujillo, A. Lavery, and A. Doblas, \"Investigation of a robust focusing metric for focusing microorganisms in underwater lensless imaging,\" Poster in the Optics and Photonics for Information Processing XIX Conference, SPIE Optics + Photonics, San Diego (CA), August 4, 2025.",
]

def format_field(value, max_length=80):
    """Format a field value for display"""
    if not value:
        return "—"
    value_str = str(value)
    if len(value_str) > max_length:
        return value_str[:max_length-3] + "..."
    return value_str

def check_title_quality(title, authors):
    """Check if title looks correct"""
    issues = []

    if not title:
        issues.append("❌ No title extracted")
        return issues

    if len(title) < 5:
        issues.append(f"⚠️  Title too short: '{title}'")

    # Check if title looks like an author name
    if re.fullmatch(r"[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*\s*", title.strip(), flags=re.I):
        issues.append(f"❌ Title looks like an author name: '{title}'")

    # Check if title is just initials
    if re.match(r"^[A-Z](?:[A-Z]|\.)+\s*$", title.strip()):
        issues.append(f"❌ Title is just initials: '{title}'")

    # Check if title matches author (shouldn't happen)
    if authors and title.strip() in authors:
        issues.append(f"⚠️  Title matches author field: '{title}'")

    if not issues:
        issues.append("✅ Title looks good")

    return issues

def test_citation(citation, index):
    """Test a single citation and return results"""
    print(f"\n{'='*100}")
    print(f"Test {index + 1}")
    print(f"{'='*100}")
    print(f"\nCitation:")
    print(f"  {citation}")
    print(f"\n{'-'*100}")

    try:
        result = parse_any_citation(citation)

        # Check for errors
        if 'error' in result:
            print(f"❌ PARSER ERROR: {result['error']}")
            return False

        # Extract key fields
        title = result.get('proceedings_title', '')
        authors = result.get('authors', '')
        year = result.get('year', '')
        conference = result.get('conference_name', '')
        location = result.get('conference_location', '')
        date = result.get('date_presented', '')
        asset_type = result.get('asset_type', '')

        # Display results
        print(f"\nParsed Results:")
        print(f"  {'Title:':<25} {format_field(title)}")
        print(f"  {'Authors:':<25} {format_field(authors)}")
        print(f"  {'Year:':<25} {format_field(year)}")
        print(f"  {'Date Presented:':<25} {format_field(date)}")
        print(f"  {'Conference:':<25} {format_field(conference)}")
        print(f"  {'Location:':<25} {format_field(location)}")
        print(f"  {'Asset Type:':<25} {format_field(asset_type)}")

        # Quality checks
        print(f"\nQuality Checks:")
        title_issues = check_title_quality(title, authors)
        for issue in title_issues:
            print(f"  {issue}")

        # Additional fields
        other_fields = {k: v for k, v in result.items() if k not in [
            'proceedings_title', 'authors', 'year', 'conference_name',
            'conference_location', 'date_presented', 'asset_type', 'channel_id'
        ] and v}

        if other_fields:
            print(f"\nOther Fields:")
            for key, value in other_fields.items():
                print(f"  {key:<25} {format_field(value)}")

        # Overall assessment
        has_errors = any('❌' in issue for issue in title_issues)
        has_warnings = any('⚠️' in issue for issue in title_issues)

        if has_errors:
            print(f"\n❌ FAILED: Title extraction has errors")
            return False
        elif has_warnings:
            print(f"\n⚠️  WARNING: Title extraction has warnings")
            return True
        else:
            print(f"\n✅ PASSED: Title extraction looks good")
            return True

    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if not CITATIONS:
        print("="*100)
        print("No citations to test!")
        print("="*100)
        print("\nPlease add citations to the CITATIONS list in test_citations.py")
        return

    print("="*100)
    print("Citation Parser Test Suite")
    print("="*100)
    print(f"\nTesting {len(CITATIONS)} citation(s)...")

    results = []
    for i, citation in enumerate(CITATIONS):
        if not citation.strip():
            continue
        passed = test_citation(citation.strip(), i)
        results.append(passed)

    # Summary
    print(f"\n{'='*100}")
    print("Summary")
    print(f"{'='*100}")
    total = len(results)
    passed = sum(results)
    failed = total - passed

    print(f"\nTotal Citations: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if failed == 0:
        print(f"\n🎉 All citations parsed successfully!")
    else:
        print(f"\n⚠️  {failed} citation(s) need attention")

if __name__ == "__main__":
    main()
