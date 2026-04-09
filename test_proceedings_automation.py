#!/usr/bin/env python3
"""Test conference proceedings automation field entry logic"""

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

from openai_parser import parse_citation_with_openai

# Test citation
citation = """Chang, J. W., & Lou, Y.-C. (2010). Varieties of family brand entitativity. In M. C. Campbell, J. Inman, & R. Pieters (Eds.), Advances in Consumer Research (Vol. 37, pp. 769–771). Association for Consumer Research."""

print('=' * 70)
print('TESTING CONFERENCE PROCEEDINGS AUTOMATION')
print('=' * 70)
print()
print('Citation:')
print(citation)
print()

# Parse with OpenAI
result = parse_citation_with_openai(citation)

if 'error' in result:
    print(f"❌ ERROR: {result['error']}")
    exit(1)

print('PARSED FIELDS:')
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
print(f"Conf Name:        {result.get('conference_name', 'N/A')}")
print(f"Conf Location:    {result.get('conference_location', 'N/A')}")
print(f"Conf Number:      {result.get('conference_number', 'N/A')}")
print('=' * 70)
print()

# Simulate what the automation will do
print('AUTOMATION SIMULATION:')
print('-' * 70)

# Check what will be filled
fields_to_fill = []

# Title (required)
title = result.get('proceedings_title', '').strip()
if title:
    fields_to_fill.append(f"✓ Title: {title}")
else:
    fields_to_fill.append("✗ Title: EMPTY (PROBLEM!)")

# Date
date_to_fill = (
    result.get('date_presented_mmddyyyy')
    or result.get('date_presented_mmyyyy')
    or result.get('year', '')
)
if date_to_fill:
    fields_to_fill.append(f"✓ Date: {date_to_fill}")
else:
    fields_to_fill.append("✗ Date: EMPTY")

# Conference name
conf_name = result.get('conference_name', '').strip()
if conf_name:
    fields_to_fill.append(f"✓ Conference name: {conf_name}")
else:
    fields_to_fill.append("⚠️  Conference name: EMPTY (will skip)")

# Conference location
conf_loc = result.get('conference_location', '').strip()
if conf_loc:
    fields_to_fill.append(f"✓ Conference location: {conf_loc}")
else:
    fields_to_fill.append("⚠️  Conference location: EMPTY")

# Conference number
conf_num = result.get('conference_number', '').strip()
if conf_num:
    fields_to_fill.append(f"✓ Conference number: {conf_num}")
else:
    fields_to_fill.append("⚠️  Conference number: EMPTY")

# Volume
volume = result.get('volume', '').strip()
if volume:
    fields_to_fill.append(f"✓ Volume: {volume}")
else:
    fields_to_fill.append("⚠️  Volume: EMPTY (will skip)")

# Start Page
start_page = result.get('start_page', '').strip()
if start_page:
    fields_to_fill.append(f"✓ Start Page: {start_page}")
else:
    fields_to_fill.append("⚠️  Start Page: EMPTY (will skip)")

# End Page
end_page = result.get('end_page', '').strip()
if end_page:
    fields_to_fill.append(f"✓ End Page: {end_page}")
else:
    fields_to_fill.append("⚠️  End Page: EMPTY (will skip)")

# Publisher
publisher = result.get('publisher_name', '').strip()
if publisher:
    fields_to_fill.append(f"✓ Publisher: {publisher}")
else:
    fields_to_fill.append("⚠️  Publisher: EMPTY (will skip)")

# Editors
editors = result.get('editors', '').strip()
if editors:
    fields_to_fill.append(f"ℹ️  Editors: {editors} (parsed but may not have form field)")
else:
    fields_to_fill.append("⚠️  Editors: EMPTY")

for field_status in fields_to_fill:
    print(field_status)

print('=' * 70)
print()

# Check critical fields
required_fields = ['volume', 'start_page', 'end_page', 'publisher_name']
all_present = all(result.get(field) for field in required_fields)

if all_present:
    print('✅ SUCCESS: All critical fields will be filled!')
    print()
    print('Expected automation output:')
    print('  ✓ Added date')
    print(f"  Filling Conference name: '{conf_name or 'EMPTY'}'")
    print('  ✓ Conference name filled' if conf_name else '  ✗ Parsed conference_name is empty; skipping fill')
    print('  ✓ Filled conference location')
    print('  ✓ Filled conference number')
    print(f"  ✓ Filled volume: {volume}")
    print(f"  ✓ Filled start page: {start_page}")
    print(f"  ✓ Filled end page: {end_page}")
    print(f"  ✓ Filled publisher: {publisher}")
    print('  ✓ Form filled for: Varieties of family brand entitativity')
else:
    print('❌ MISSING CRITICAL FIELDS:')
    for field in required_fields:
        if not result.get(field):
            print(f"  - {field}")
