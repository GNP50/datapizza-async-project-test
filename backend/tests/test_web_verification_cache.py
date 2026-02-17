"""
Tests for web verification caching across documents.

Validates that identical facts from different documents share the same
cached verification result.
"""

import pytest
from uuid import uuid4
from app.services.processing_cache_service import processing_cache_service


@pytest.mark.asyncio
async def test_web_verification_cache_across_documents():
    """
    Test that identical facts from different documents share cache.

    This is the key test to validate that cache lookups don't filter
    by document_id, allowing identical facts to reuse verification results
    regardless of which document they came from.
    """
    # Same fact content
    fact_content = "The Eiffel Tower is 330 meters tall"
    content_hash = processing_cache_service.compute_content_hash(fact_content)

    # Two different documents
    document_id_1 = uuid4()
    document_id_2 = uuid4()

    # Verification result
    verification_data = {
        "verification_status": "VERIFIED",
        "web_source_url": "https://example.com/eiffel-tower",
        "all_source_urls": ["https://example.com/eiffel-tower"],
        "confidence_score": 0.95,
        "verification_reasoning": "Multiple reliable sources confirm this fact."
    }

    # 1. Store result for document_1
    await processing_cache_service.set_cached_result(
        content_hash=content_hash,
        stage="web_verification",
        result_data=verification_data,
        document_id=document_id_1,
        metadata={"fact_content": fact_content}
    )

    # 2. Lookup without document_id filter (should find the cached result)
    cached_result = await processing_cache_service.get_cached_result(
        content_hash=content_hash,
        stage="web_verification"
        # No document_id parameter - this allows cache hits across documents
    )

    assert cached_result is not None, "Cache should return result without document_id filter"
    assert cached_result["verification_status"] == "VERIFIED"
    assert cached_result["confidence_score"] == 0.95

    # 3. Lookup from document_2's perspective (should still find the same cached result)
    cached_result_doc2 = await processing_cache_service.get_cached_result(
        content_hash=content_hash,
        stage="web_verification"
        # Again, no document_id filter
    )

    assert cached_result_doc2 is not None
    assert cached_result_doc2["verification_status"] == "VERIFIED"
    assert cached_result_doc2 == cached_result, "Both lookups should return identical results"

    print("✅ Cache successfully shared across different documents!")


@pytest.mark.asyncio
async def test_web_verification_cache_different_content():
    """
    Test that different fact content results in cache misses.
    """
    fact_1 = "The Eiffel Tower is 330 meters tall"
    fact_2 = "The Eiffel Tower is 324 meters tall"  # Different content

    hash_1 = processing_cache_service.compute_content_hash(fact_1)
    hash_2 = processing_cache_service.compute_content_hash(fact_2)

    # Store result for fact_1
    await processing_cache_service.set_cached_result(
        content_hash=hash_1,
        stage="web_verification",
        result_data={
            "verification_status": "VERIFIED",
            "confidence_score": 0.95
        },
        document_id=uuid4()
    )

    # Lookup fact_2 (should be a miss)
    cached_result = await processing_cache_service.get_cached_result(
        content_hash=hash_2,
        stage="web_verification"
    )

    assert cached_result is None, "Different content should result in cache miss"
    print("✅ Different content correctly results in cache miss")


@pytest.mark.asyncio
async def test_cache_key_computation():
    """
    Test that cache keys are computed consistently.
    """
    content = "Test fact content"
    content_hash = processing_cache_service.compute_content_hash(content)

    # Same content should produce same hash
    hash_2 = processing_cache_service.compute_content_hash(content)
    assert content_hash == hash_2

    # Different content should produce different hash
    hash_3 = processing_cache_service.compute_content_hash("Different content")
    assert content_hash != hash_3

    # Cache key should combine content_hash + stage
    cache_key_1 = processing_cache_service.compute_cache_key(content_hash, "web_verification")
    cache_key_2 = processing_cache_service.compute_cache_key(content_hash, "web_verification")
    assert cache_key_1 == cache_key_2

    # Different stage should produce different cache key
    cache_key_3 = processing_cache_service.compute_cache_key(content_hash, "qa_generation")
    assert cache_key_1 != cache_key_3

    print("✅ Cache key computation is consistent")
