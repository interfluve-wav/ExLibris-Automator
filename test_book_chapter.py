#!/usr/bin/env python3
"""Test book chapter citation parsing."""

import os
from dotenv import load_dotenv
load_dotenv()

from openai_parser import parse_citation_with_openai

citation = """Chang, J. W. (2011). The mediation of family brand entitativity on extension feedback effects. In J. Cotte, L. Price, J. Xiao, & Z. Yi (Eds.), Advances in Consumer Research: Asia Pacific (Vol. 9, pp. 63–64). Association for Consumer Research."""

print("=" * 80)
print("BOOK CHAPTER CITATION TEST")
print("=" * 80)
print(f"\nCitation:\n{citation}\n")

result = parse_citation_with_openai(citation)

if "error" in result:
    print(f"❌ ERROR: {result['error']}")
else:
    print("Parsed Fields:")
    print("=" * 80)
    
    # Key fields for book chapter
    fields_to_check = [
        ('asset_type', 'Asset Type'),
        ('authors', 'Author'),
        ('year', 'Year'),
        ('article_title', 'Paper Title'),
        ('proceedings_title', 'Proceedings Title'),
        ('book_title', 'Book Title'),
        ('volume', 'Volume'),
        ('pages', 'Pages'),
        ('start_page', 'Start Page'),
        ('end_page', 'End Page'),
        ('editors', 'Editors'),
        ('publisher_name', 'Publisher'),
    ]
    
    for key, label in fields_to_check:
        value = result.get(key, 'N/A')
        if value and value != 'N/A':
            print(f"{label:20s}: {value}")
    
    print("\n" + "=" * 80)
    print("Quality Checks:")
    print("=" * 80)
    
    checks = []
    
    # Check author
    if result.get('authors') and 'Chang' in result.get('authors', ''):
        checks.append(("✅", "Author extracted (Chang, J. W.)"))
    else:
        checks.append(("❌", "Author missing or incorrect"))
    
    # Check year
    if result.get('year') == '2011':
        checks.append(("✅", "Year correct (2011)"))
    else:
        checks.append(("❌", f"Year incorrect: {result.get('year')}"))
    
    # Check title
    title = result.get('article_title') or result.get('proceedings_title', '')
    if title and 'entitativity' in title.lower():
        checks.append(("✅", "Paper title extracted"))
    else:
        checks.append(("❌", "Paper title missing"))
    
    # Check book title
    book_title = result.get('book_title', '')
    if book_title and 'Consumer Research' in book_title:
        checks.append(("✅", "Book title extracted"))
    else:
        checks.append(("❌", f"Book title missing or incorrect: {book_title}"))
    
    # Check volume
    if result.get('volume') and '9' in result.get('volume', ''):
        checks.append(("✅", "Volume extracted (9)"))
    else:
        checks.append(("❌", f"Volume missing or incorrect: {result.get('volume')}"))
    
    # Check pages
    if result.get('pages') or (result.get('start_page') and result.get('end_page')):
        checks.append(("✅", "Pages extracted"))
    else:
        checks.append(("❌", "Pages missing"))
    
    # Check editors
    if result.get('editors'):
        checks.append(("✅", f"Editors extracted ({len(result.get('editors', '').split(','))} names)"))
    else:
        checks.append(("❌", "Editors missing"))
    
    # Check publisher
    if result.get('publisher_name') and 'Association' in result.get('publisher_name', ''):
        checks.append(("✅", "Publisher extracted"))
    else:
        checks.append(("❌", "Publisher missing"))
    
    for icon, msg in checks:
        print(f"  {icon} {msg}")
    
    # Overall assessment
    passed = sum(1 for icon, _ in checks if icon == "✅")
    total = len(checks)
    print(f"\n{'='*80}")
    print(f"Score: {passed}/{total} checks passed")
    print("=" * 80)
