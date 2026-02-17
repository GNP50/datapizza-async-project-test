"""
Web Search Service - Abstraction layer for web search functionality.
Supports multiple backends: DuckDuckGo (via ddgs), Google Custom Search.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging
import httpx
import asyncio
import os

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Single search result"""
    title: str
    url: str
    snippet: str
    source: str = "unknown"


@dataclass
class SearchResponse:
    """Response from search operation"""
    query: str
    results: list[SearchResult]
    total_results: int
    search_engine: str


class SearchBackend(ABC):
    """Abstract base class for search backends"""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        """Execute a web search"""
        pass


class DuckDuckGoBackend(SearchBackend):
    """DuckDuckGo search backend using ddgs library"""

    async def _verify_url_exists(self, url: str, timeout: int = 5) -> bool:
        """
        Verify that a URL actually exists by sending a HEAD or GET request.
        Returns True if the URL is accessible (status code 200-399).
        """
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }

                # Try HEAD request first (faster)
                try:
                    response = await client.head(url, headers=headers)

                    # Some servers don't support HEAD, try GET if HEAD fails
                    if response.status_code == 405 or response.status_code == 501:
                        # Method not allowed, try GET instead
                        response = await client.get(url, headers=headers)

                    # Accept 2xx and 3xx status codes as valid
                    if 200 <= response.status_code < 400:
                        return True
                    else:
                        logger.info(f"URL returned status {response.status_code}: {url}")
                        return False

                except httpx.HTTPStatusError:
                    # If HEAD fails with status error, try GET
                    response = await client.get(url, headers=headers)
                    if 200 <= response.status_code < 400:
                        return True
                    else:
                        logger.info(f"URL returned status {response.status_code}: {url}")
                        return False

        except httpx.TimeoutException:
            logger.info(f"URL verification timeout for {url}")
            return False
        except httpx.ConnectError:
            logger.info(f"URL connection failed for {url}")
            return False
        except (httpx.HTTPError, Exception) as e:
            logger.info(f"URL verification failed for {url}: {e}")
            return False

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            from ddgs import DDGS

            results = []
            with DDGS() as ddgs:
                # Enable SafeSearch to filter adult content and specify region for better English results
                search_results = list(ddgs.text(
                    query,
                    max_results=max_results * 3,  # Get more results to filter
                    safesearch='strict',  # Use strict safe search
                    region='wt-wt'  # No region filtering (worldwide)
                ))

                # First pass: filter by content (fast)
                filtered_results = []
                for result in search_results:
                    url = result.get("href", "")
                    title = result.get("title", "")
                    snippet = result.get("body", "")

                    if self._is_safe_and_relevant_url(url, title, snippet):
                        filtered_results.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet
                        })

                    # Get more than needed for URL verification
                    if len(filtered_results) >= max_results * 2:
                        break

                # Second pass: verify URLs actually exist (slower but more accurate)
                # Verify URLs in parallel for speed
                verification_tasks = [
                    self._verify_url_exists(r["url"])
                    for r in filtered_results[:max_results * 2]
                ]

                if verification_tasks:
                    verification_results = await asyncio.gather(*verification_tasks, return_exceptions=True)

                    for i, (result, is_valid) in enumerate(zip(filtered_results, verification_results)):
                        # Skip if verification failed or returned an exception
                        if isinstance(is_valid, Exception) or not is_valid:
                            logger.info(f"URL failed verification: {result['url']}")
                            continue

                        results.append(SearchResult(
                            title=result["title"],
                            url=result["url"],
                            snippet=result["snippet"],
                            source="duckduckgo"
                        ))

                        # Stop when we have enough verified results
                        if len(results) >= max_results:
                            break

            return SearchResponse(
                query=query,
                results=results,
                total_results=len(results),
                search_engine="duckduckgo"
            )
        except ImportError:
            raise RuntimeError(
                "ddgs is not installed. "
                "Install it with: pip install ddgs"
            )
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            raise RuntimeError(f"Search failed: {str(e)}") from e

    def _is_safe_and_relevant_url(self, url: str, title: str, snippet: str) -> bool:
        """
        Filter out inappropriate domains, non-existent sites, low-quality content, and non-English sites.
        Returns True if URL is safe and relevant to use.
        """
        if not url:
            return False

        url_lower = url.lower()
        title_lower = title.lower() if title else ""
        snippet_lower = snippet.lower() if snippet else ""

        # List of common adult content indicators in URLs
        blocked_patterns = [
            'porn', 'xxx', 'adult', 'sex', 'nude', 'nsfw',
            'xvideos', 'pornhub', 'xhamster', 'redtube',
            'youporn', 'tube8', 'spankwire', 'keezmovies',
            'extremetube', 'xtube', 'sexvid', 'erotic',
            'webcam', 'livejasmin', 'chaturbate', 'cams'
        ]

        # Check if any blocked pattern is in the URL
        for pattern in blocked_patterns:
            if pattern in url_lower:
                logger.warning(f"Blocked inappropriate URL: {url}")
                return False

        # Filter out common non-existent or low-quality domains
        # Check both title and snippet for error indicators
        spam_indicators = [
            # 404 and error pages
            '404', 'not found', 'page not found', 'error 404',
            'page doesn\'t exist', 'does not exist', 'cannot be found',
            'no longer available', 'has been removed', 'parked domain',
            # Server errors
            '500 internal server error', '502 bad gateway', '503 service unavailable',
            'server error', 'temporarily unavailable',
            # Domain issues
            'domain expired', 'domain not found', 'this domain may be for sale',
            'buy this domain', 'register this domain',
            # Content removal
            'content removed', 'page removed', 'deleted', 'content unavailable',
            # Redirects and placeholders
            'coming soon', 'under construction', 'placeholder',
            # Access issues
            'access denied', 'forbidden', '403 forbidden',
            # Dead links
            'broken link', 'dead link', 'link not working',
            # Chinese error messages (common in filtered results)
            '找不到', '不存在', '已删除', '错误'
        ]

        # More aggressive filtering - check if any indicator appears
        for indicator in spam_indicators:
            if indicator in title_lower or indicator in snippet_lower:
                logger.info(f"Blocked non-existent/low-quality URL (matched '{indicator}'): {url}")
                return False

        # Additional check: very short snippets often indicate error pages
        if len(snippet.strip()) < 50:
            logger.info(f"Blocked URL with suspiciously short snippet: {url}")
            return False

        # Check for generic/empty titles
        generic_titles = [
            'untitled', 'no title', 'index', 'home', 'default',
            'error', 'oops', 'sorry'
        ]
        if title_lower.strip() in generic_titles or len(title.strip()) < 3:
            logger.info(f"Blocked URL with generic/empty title: {url}")
            return False

        # Detect primarily non-Latin character content (Chinese, Japanese, Korean, etc.)
        # Count non-Latin characters in title and snippet
        def count_non_latin_chars(text: str) -> int:
            if not text:
                return 0
            non_latin = 0
            for char in text:
                # Unicode ranges for CJK (Chinese, Japanese, Korean)
                # and other non-Latin scripts
                if (
                    '\u4e00' <= char <= '\u9fff' or  # CJK Unified Ideographs
                    '\u3400' <= char <= '\u4dbf' or  # CJK Extension A
                    '\u3040' <= char <= '\u309f' or  # Hiragana
                    '\u30a0' <= char <= '\u30ff' or  # Katakana
                    '\uac00' <= char <= '\ud7af' or  # Hangul (Korean)
                    '\u0400' <= char <= '\u04ff' or  # Cyrillic
                    '\u0600' <= char <= '\u06ff' or  # Arabic
                    '\u0e00' <= char <= '\u0e7f'     # Thai
                ):
                    non_latin += 1
            return non_latin

        # If more than 30% of characters are non-Latin, filter it out
        combined_text = title + " " + snippet
        if combined_text:
            total_chars = len(combined_text.replace(" ", ""))
            if total_chars > 10:  # Only check if there's enough text
                non_latin_count = count_non_latin_chars(combined_text)
                non_latin_ratio = non_latin_count / total_chars
                if non_latin_ratio > 0.3:
                    logger.info(f"Blocked non-English URL (non-Latin ratio: {non_latin_ratio:.2f}): {url}")
                    return False

        # Filter out common spammy TLDs
        spammy_tlds = [
            '.tk', '.ml', '.ga', '.cf', '.gq',  # Free domains often used for spam
            '.xyz', '.top', '.win', '.loan',     # Common spam TLDs
        ]

        for tld in spammy_tlds:
            if url_lower.endswith(tld) or tld + '/' in url_lower:
                logger.info(f"Blocked spammy TLD URL: {url}")
                return False

        # Filter out URLs with suspicious patterns that often lead to broken links
        suspicious_patterns = [
            '/search?', '/redirect?', '/goto?', '/link?',  # Redirect URLs
            'doubleclick.net', 'googleadservices.com',      # Ad networks
            '/amp/', '/m.', '/mobile.',                      # Mobile/AMP versions
            'translate.google.com',                          # Translated pages
            'webcache.googleusercontent.com',                # Cached pages
        ]

        for pattern in suspicious_patterns:
            if pattern in url_lower:
                logger.info(f"Blocked suspicious URL pattern ('{pattern}'): {url}")
                return False

        # Ensure URL has a proper scheme
        if not url_lower.startswith(('http://', 'https://')):
            logger.info(f"Blocked URL with invalid scheme: {url}")
            return False

        return True


class GoogleSearchBackend(SearchBackend):
    """Google search backend using googlesearch-python library"""

    async def _verify_url_exists(self, url: str, timeout: int = 5) -> bool:
        """
        Verify that a URL actually exists by sending a HEAD or GET request.
        Returns True if the URL is accessible (status code 200-399).
        """
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }

                # Try HEAD request first (faster)
                try:
                    response = await client.head(url, headers=headers)

                    # Some servers don't support HEAD, try GET if HEAD fails
                    if response.status_code == 405 or response.status_code == 501:
                        response = await client.get(url, headers=headers)

                    # Accept 2xx and 3xx status codes as valid
                    if 200 <= response.status_code < 400:
                        return True
                    else:
                        logger.info(f"URL returned status {response.status_code}: {url}")
                        return False

                except httpx.HTTPStatusError:
                    response = await client.get(url, headers=headers)
                    if 200 <= response.status_code < 400:
                        return True
                    else:
                        logger.info(f"URL returned status {response.status_code}: {url}")
                        return False

        except httpx.TimeoutException:
            logger.info(f"URL verification timeout for {url}")
            return False
        except httpx.ConnectError:
            logger.info(f"URL connection failed for {url}")
            return False
        except (httpx.HTTPError, Exception) as e:
            logger.info(f"URL verification failed for {url}: {e}")
            return False

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        try:
            from googlesearch import search

            results = []

            # Get more results than needed for filtering
            # googlesearch returns an iterator of URLs
            search_urls = []
            try:
                # Use googlesearch-python to get search results
                # num_results should be higher to account for filtering
                search_urls = list(search(query, num_results=max_results * 3, lang='en', sleep_interval=0.5))
            except Exception as e:
                logger.error(f"Google search failed: {e}")
                raise RuntimeError(f"Google search failed: {str(e)}") from e

            # For each URL, we need to fetch title and snippet
            # We'll verify URLs in parallel
            fetch_tasks = []
            for url in search_urls[:max_results * 2]:
                fetch_tasks.append(self._fetch_page_metadata(url))

            if fetch_tasks:
                metadata_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

                for url, metadata in zip(search_urls, metadata_results):
                    # Skip if fetching failed
                    if isinstance(metadata, Exception) or metadata is None:
                        logger.info(f"Failed to fetch metadata for: {url}")
                        continue

                    title, snippet, is_valid = metadata

                    # Only include valid URLs
                    if is_valid and title and snippet:
                        results.append(SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            source="google"
                        ))

                        # Stop when we have enough verified results
                        if len(results) >= max_results:
                            break

            return SearchResponse(
                query=query,
                results=results,
                total_results=len(results),
                search_engine="google"
            )
        except ImportError:
            raise RuntimeError(
                "googlesearch-python is not installed. "
                "Install it with: pip install googlesearch-python"
            )
        except Exception as e:
            logger.error(f"Google search failed: {e}")
            raise RuntimeError(f"Search failed: {str(e)}") from e

    async def _fetch_page_metadata(self, url: str) -> tuple[str, str, bool]:
        """
        Fetch page title and meta description.
        Returns (title, snippet, is_valid).
        """
        try:
            # First verify URL exists
            is_valid = await self._verify_url_exists(url)
            if not is_valid:
                return "", "", False

            # Fetch page content to extract title and description
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
                response = await client.get(url, headers=headers)

                if response.status_code >= 400:
                    return "", "", False

                # Parse HTML to get title and meta description
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract title
                title = ""
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()

                # Extract meta description
                snippet = ""
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if not meta_desc:
                    meta_desc = soup.find('meta', attrs={'property': 'og:description'})

                if meta_desc and meta_desc.get('content'):
                    snippet = meta_desc['content'].strip()
                else:
                    # Fallback: get first paragraph text
                    paragraphs = soup.find_all('p')
                    for p in paragraphs:
                        text = p.get_text().strip()
                        if len(text) > 50:
                            snippet = text[:300]
                            break

                return title, snippet, True

        except Exception as e:
            logger.info(f"Failed to fetch metadata for {url}: {e}")
            return "", "", False


class SearchService:
    """
    Main search service that manages different search backends.
    Provides a unified interface for web search operations.
    """

    def __init__(self, backend: Optional[SearchBackend] = None):
        if backend:
            self.backend = backend
        else:
            # Default to DuckDuckGo (more reliable, no extra dependencies needed)
            # Can be overridden by setting backend explicitly
            self.backend = DuckDuckGoBackend()
            logger.info("Using DuckDuckGo search backend")

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        """
        Execute a web search.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            SearchResponse with results
        """
        try:
            return await self.backend.search(query, max_results)
        except RuntimeError as e:
            # If current backend fails with ImportError, try fallback to DuckDuckGo
            error_msg = str(e)
            if "googlesearch-python is not installed" in error_msg and not isinstance(self.backend, DuckDuckGoBackend):
                logger.warning(f"Google search failed, falling back to DuckDuckGo: {e}")
                self.backend = DuckDuckGoBackend()
                return await self.backend.search(query, max_results)
            else:
                logger.error(f"Search failed for query '{query}': {e}")
                raise
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise RuntimeError(f"Search failed: {str(e)}") from e

    async def verify_fact(self, fact: str) -> tuple[bool, Optional[str], float]:
        """
        Verify a fact using web search.

        Args:
            fact: The fact to verify

        Returns:
            Tuple of (is_verified, source_url, confidence_score)
        """
        try:
            response = await self.search(fact, max_results=3)

            if not response.results:
                return False, None, 0.0

            best_result = response.results[0]
            confidence = min(0.95, 0.5 + (len(response.results) * 0.15))

            return True, best_result.url, confidence
        except Exception as e:
            logger.error(f"Fact verification failed: {e}")
            return False, None, 0.0

    def set_backend(self, backend: SearchBackend):
        """Switch to a different search backend"""
        self.backend = backend


# Global instance - defaults to DuckDuckGo (reliable and no extra dependencies)
search_service = SearchService()
