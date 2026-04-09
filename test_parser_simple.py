#!/usr/bin/env python3
"""Simple test to verify OpenAI parser is working correctly."""

import os
import json
from dotenv import load_dotenv
load_dotenv()

from openai_parser import parse_citation_with_openai

# Test citations
test_citations = [
    # Conference presentation
    """Smith, J., & Doe, A. (2023, May 15-17). Understanding Machine Learning in Healthcare. 
    Proceedings of the 45th Annual Conference on AI in Medicine. Boston, MA.""",
    
    # Journal article  
    """Johnson, M. (2022). Deep Learning Applications in Medical Imaging. 
    Journal of Medical Informatics, 15(3), 234-256.""",
    
    # Conference proceedings
    """Williams, R. (2021). Data Privacy in the Digital Age. In Proceedings of the 
    International Conference on Cybersecurity (pp. 112-125). San Francisco, CA: ACM Press."""
]

print("=" * 80)
print("SIMPLE PARSER TEST")
print("=" * 80)

for i, citation in enumerate(test_citations, 1):
    print(f"\n{'='*80}")
    print(f"Test {i}")
    print(f"{'='*80}")
    print(f"Citation: {citation[:100]}...")
    print()
    
    result = parse_citation_with_openai(citation)
    
    if "error" in result:
        print(f"❌ ERROR: {result['error']}")
        continue
    
    # Print key fields
    title = result.get('proceedings_title') or result.get('article_title') or 'N/A'
    print(f"Asset Type:        {result.get('asset_type', 'N/A')}")
    print(f"Title:             {title}")
    print(f"Authors:           {result.get('authors', 'N/A')}")
    print(f"Year:              {result.get('year', 'N/A')}")
    print(f"Conference Name:   {result.get('conference_name', 'N/A')}")
    print(f"Location:          {result.get('conference_location', 'N/A')}")
    print(f"Conference Number: {result.get('conference_number', 'N/A')}")
    print(f"Journal Name:      {result.get('journal_name', 'N/A')}")
    print(f"Volume:            {result.get('volume', 'N/A')}")
    print(f"Issue:             {result.get('issue', 'N/A')}")
    print(f"Pages:             {result.get('pages', 'N/A')}")
    
    # Quality checks
    print("\n✓ Quality Checks:")
    if title and title != 'N/A' and len(title) > 5:
        print("  ✅ Title extracted")
    else:
        print("  ❌ Title missing or too short")
    
    if result.get('authors'):
        print("  ✅ Authors extracted")
    else:
        print("  ⚠️  No authors found")
    
    if result.get('year'):
        print("  ✅ Year extracted")
    else:
        print("  ⚠️  No year found")

print("\n" + "="*80)
print("DONE")
print("="*80)
