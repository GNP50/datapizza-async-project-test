"""
Web Content Extractor - Extract and process web page content for vectorstore indexing.
Uses LLM to extract relevant information from web pages and stores it in the vectorstore.
"""
import logging
import httpx
from bs4 import BeautifulSoup
from typing import Optional
from uuid import UUID
from datapizza.type import Chunk

logger = logging.getLogger(__name__)


class WebContentExtractor:
    """Extract and process content from web pages"""

    def __init__(self, timeout: int = 30, max_content_length: int = 50000):
        """
        Initialize the web content extractor.

        Args:
            timeout: HTTP request timeout in seconds
            max_content_length: Maximum content length to extract (in characters)
        """
        self.timeout = timeout
        self.max_content_length = max_content_length

    async def fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract clean text content from a web page.

        Args:
            url: The URL to fetch

        Returns:
            Extracted text content or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                # Set user agent to avoid blocking
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                # Parse HTML content
                soup = BeautifulSoup(response.text, 'html.parser')

                # Remove script and style elements
                for script in soup(['script', 'style', 'header', 'footer', 'nav']):
                    script.decompose()

                # Get text content
                text = soup.get_text(separator='\n', strip=True)

                # Clean up excessive whitespace
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                content = '\n'.join(lines)

                # Truncate if too long
                if len(content) > self.max_content_length:
                    content = content[:self.max_content_length]
                    logger.info(f"Truncated content from {url} to {self.max_content_length} characters")

                return content

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}", exc_info=True)
            return None

    async def extract_relevant_chunks(
        self,
        url: str,
        content: str,
        query_context: str,
        llm_client
    ) -> list[str]:
        """
        Use LLM to extract relevant pieces of content based on query context.

        Args:
            url: The source URL
            content: The web page content
            query_context: The original query/context for relevance filtering
            llm_client: The LLM client to use for extraction

        Returns:
            List of relevant text chunks
        """
        try:
            # Create a prompt for the LLM to extract relevant information
            prompt = f"""You are a precise fact extraction assistant. Extract SPECIFIC, CONCRETE facts from the web page that directly relate to the query context.

Query Context: {query_context}

Web Page Content:
{content[:10000]}  # Limit to first 10k chars for LLM processing

CRITICAL REQUIREMENTS:
1. Extract ONLY specific, verifiable facts (numbers, dates, names, events, definitions)
2. Each fact must be ATOMIC - one clear statement per fact
3. Each fact should be 1-2 sentences maximum (prefer 1 sentence)
4. Avoid generic statements, opinions, or vague information
5. Prioritize facts with concrete data: statistics, dates, measurements, specific claims
6. Ignore promotional content, ads, navigation, and filler text
7. Return MAXIMUM 3-4 high-quality facts (quality over quantity)
8. Format each fact as: "- [FACT]" on a separate line

EXAMPLES OF GOOD FACTS:
- "The human heart beats approximately 100,000 times per day"
- "Python 3.11 was released on October 24, 2022"
- "Mount Everest stands at 8,848.86 meters above sea level"

EXAMPLES OF BAD FACTS (DO NOT EXTRACT):
- "This is an important topic" (too vague)
- "Many people believe..." (opinion, not fact)
- "Learn more about our services" (promotional)
- "There are various factors to consider" (generic)

If no specific, concrete facts are found, return "NO_RELEVANT_CONTENT"."""

            # Call the LLM
            response = await llm_client.chat.completions.create(
                model="gpt-4o-mini",  # Use a fast, cost-effective model
                messages=[
                    {"role": "system", "content": "You are a precise content extraction assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )

            extracted_text = response.choices[0].message.content.strip()

            if extracted_text == "NO_RELEVANT_CONTENT":
                logger.info(f"No relevant content found in {url}")
                return []

            # Parse the extracted chunks
            chunks = []
            for line in extracted_text.split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    chunk = line[2:].strip()
                    # Filter: minimum 20 chars, maximum 300 chars for conciseness
                    # Ensure chunks are substantive but not overly verbose
                    if chunk and 20 <= len(chunk) <= 300:
                        chunks.append(chunk)

            # Limit to maximum 3 chunks to keep results focused
            chunks = chunks[:3]

            logger.info(f"Extracted {len(chunks)} relevant chunks from {url}")
            return chunks

        except Exception as e:
            logger.error(f"Error extracting chunks with LLM from {url}: {e}", exc_info=True)
            return []

    async def process_url_to_chunks(
        self,
        url: str,
        query_context: str,
        llm_client,
        chat_id: UUID,
        source_type: str = "web_search"
    ) -> list[Chunk]:
        """
        Fetch a URL, extract relevant content using LLM, and convert to Chunk objects.

        Args:
            url: The URL to process
            query_context: The query context for relevance filtering
            llm_client: The LLM client for extraction
            chat_id: The chat ID for isolation
            source_type: The source type for metadata

        Returns:
            List of Chunk objects ready for vectorstore insertion
        """
        # Fetch page content
        content = await self.fetch_page_content(url)
        if not content:
            logger.warning(f"Could not fetch content from {url}")
            return []

        # Extract relevant chunks using LLM
        text_chunks = await self.extract_relevant_chunks(url, content, query_context, llm_client)
        if not text_chunks:
            logger.info(f"No relevant chunks extracted from {url}")
            return []

        # Convert to Chunk objects
        chunks = []
        for idx, text in enumerate(text_chunks):
            chunk = Chunk(
                content=text,
                metadata={
                    "source_url": url,
                    "source_type": source_type,
                    "chat_id": str(chat_id),
                    "chunk_index": idx,
                    "query_context": query_context
                }
            )
            chunks.append(chunk)

        logger.info(f"Created {len(chunks)} chunks from {url}")
        return chunks


# Global instance
web_content_extractor = WebContentExtractor()
