#!/usr/bin/env python3
"""
Quick test for technical documentation parser
Tests that all required fields are populated correctly
"""
from automation.technical_documentation_impl import parse_any_citation

# Test citations
test_citations = [
    # Your actual citation from the logs
    "Vineyard Wind demersal trawl survey annual report – VW1 study area: 2023/2024 annual report. (2024). Technical Report. INSPIRE Environmental.",
    
    # Variation with more fields
    "Smith, J., & Jones, M. (2024). Coastal Marine Survey Results. National Oceanic Research Institute. Report No. NORI-2024-001. DOI: 10.1234/example.2024",
    
    # Minimal citation
    "Johnson, A. (2023). Environmental Impact Assessment. EPA. Report EPA-2023-456.",
]

def test_parser():
    print("="*80)
    print("TECHNICAL DOCUMENTATION PARSER TEST")
    print("="*80)
    
    for i, citation in enumerate(test_citations, 1):
        print(f"\n{'='*80}")
        print(f"TEST {i}/{len(test_citations)}")
        print(f"{'='*80}")
        print(f"\nCitation:\n{citation}\n")
        
        try:
            result = parse_any_citation(citation)
            
            if "error" in result:
                print(f"❌ PARSER ERROR: {result['error']}")
                continue
            
            # Check critical fields
            print("PARSED FIELDS:")
            print("-" * 80)
            
            critical_fields = [
                'proceedings_title',
                'asset_title',
                'authors',
                'year',
                'publisher_name',
                'report_number',
                'doi',
            ]
            
            has_errors = False
            
            for field in critical_fields:
                value = result.get(field, '')
                status = "✅" if value else "⚠️ "
                print(f"{status} {field:30s} = {value}")
                
            # Verify asset_title and proceedings_title match
            if result.get('asset_title') != result.get('proceedings_title'):
                print(f"\n❌ MISMATCH: asset_title != proceedings_title")
                print(f"   asset_title: {result.get('asset_title')}")
                print(f"   proceedings_title: {result.get('proceedings_title')}")
                has_errors = True
            
            # Check that we have at minimum a title
            if not result.get('proceedings_title') and not result.get('asset_title'):
                print(f"\n❌ CRITICAL: No title found!")
                has_errors = True
            
            # Show all non-empty fields
            print("\nALL NON-EMPTY FIELDS:")
            print("-" * 80)
            for key, value in sorted(result.items()):
                if value and key not in critical_fields:
                    print(f"  {key:30s} = {value}")
            
            if not has_errors:
                print(f"\n✅ TEST {i} PASSED")
            else:
                print(f"\n❌ TEST {i} FAILED")
                
        except Exception as e:
            print(f"\n❌ EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    test_parser()
