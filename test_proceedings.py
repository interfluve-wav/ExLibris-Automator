#!/usr/bin/env python3
"""Test conference proceedings citation parsing"""

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

from openai_parser import parse_citation_with_openai

# Test citation
citation = """Chang, J. W., & Lou, Y.-C. (2010). Varieties of family brand entitativity. In M. C. Campbell, J. Inman, & R. Pieters (Eds.), Advances in Consumer Research (Vol. 37, pp. 769–771). Association for Consumer Research."""

print('=' * 70)
print('TESTING CONFERENCE PROCEEDINGS CITATION')
print('=' * 70)
print()
print('Citation:')
print(citation)
print()

result = parse_citation_with_openai(citation)

print('EXTRACTED FIELDS:')
print('-' * 70)
print(f"Asset Type:       {result.get('asset_type', 'N/A')}")
print(f"Title:            {result.get('proceedings_title', 'N/A')}")
print(f"Authors:          {result.get('authors', 'N/A')}")
print(f"Year:             {result.get('year', 'N/A')}")
print(f"Book Title:       {result.get('book_title', 'N/A')}")
print(f"Editors:          {result.get('editors', 'N/A')}")
print(f"Volume:           {result.get('volume', 'N/A')}")
print(f"Start Page:       {result.get('start_page', 'N/A')}")
print(f"End Page:         {result.get('end_page', 'N/A')}")
print(f"Publisher:        {result.get('publisher_name', 'N/A')}")
print('=' * 70)

# Check if all required fields are present
required_fields = ['volume', 'start_page', 'end_page', 'editors', 'publisher_name']
all_present = all(result.get(field) for field in required_fields)

print()
if all_present:
    print('✅ SUCCESS: All required fields extracted!')
    print()
    print('These values will be filled in the Esploro form:')
    print(f"  • Volume: {result.get('volume')}")
    print(f"  • Start Page: {result.get('start_page')}")
    print(f"  • End Page: {result.get('end_page')}")
    print(f"  • Editors: {result.get('editors')}")
    print(f"  • Publisher: {result.get('publisher_name')}")
else:
    print('❌ MISSING FIELDS:')
    for field in required_fields:
        if not result.get(field):
            print(f"  - {field}")
