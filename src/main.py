"""Carrefour Egypt Sitemap Product Scraper - Bilingual Version.

Crawls both Arabic and English product pages, then merges them by SKU.
"""

from __future__ import annotations
import asyncio
import xml.etree.ElementTree as ET
import json
import time
import re
from functools import lru_cache
from typing import Any

from apify import Actor
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee import Request
from bs4 import BeautifulSoup
import httpx

# Constants
SITEMAP_NAMESPACE = 'http://www.sitemaps.org/schemas/sitemap/0.9'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
OFF_API_BASE = 'https://world.openfoodfacts.org/api/v2/product'
MAX_LINE_LENGTH = 100
SITEMAP_TIMEOUT = 30.0
API_TIMEOUT = 10.0

# Performance tracking
performance_stats = {
    'playwright_pages': 0,
    'playwright_time': 0,
    'button_clicks': 0,
    'next_data_extractions': 0
}


def _find_loc_element(element: ET.Element) -> ET.Element | None:
    """Find loc element with or without namespace."""
    loc = element.find('.//loc')
    if loc is None:
        loc = element.find(f'.//{{{SITEMAP_NAMESPACE}}}loc')
    return loc


def _is_product_sitemap(url: str, language_filter: str | None) -> bool:
    """Check if sitemap URL matches product and language filter."""
    if 'product' not in url.lower():
        return False
    
    if language_filter:
        return f'_{language_filter}.xml' in url.lower()
    
    return True


async def _fetch_sitemap_urls(root: ET.Element) -> list[str]:
    """Extract URLs from sitemap XML root."""
    namespaces = {'': SITEMAP_NAMESPACE, 's': SITEMAP_NAMESPACE}
    urls = []
    
    for prefix in ['', 's:', './/']:
        ns = namespaces if prefix and prefix != './/' else {}
        url_elements = root.findall(f'{prefix}url', ns)
        
        if url_elements:
            for url_elem in url_elements:
                loc = _find_loc_element(url_elem)
                if loc is not None and loc.text:
                    urls.append(loc.text)
            break
    
    return urls


async def _fetch_child_sitemaps(
    root: ET.Element,
    language_filter: str | None
) -> list[str]:
    """Recursively fetch product URLs from child sitemaps."""
    namespaces = {'s': SITEMAP_NAMESPACE}
    sitemaps = root.findall('.//s:sitemap', namespaces)
    if not sitemaps:
        sitemaps = root.findall('.//sitemap')
    
    if not sitemaps:
        return []
    
    Actor.log.info(f'Found sitemap index with {len(sitemaps)} sitemaps')
    
    product_sitemaps = []
    for sitemap in sitemaps:
        loc_elem = _find_loc_element(sitemap)
        if loc_elem is not None and loc_elem.text:
            if _is_product_sitemap(loc_elem.text, language_filter):
                product_sitemaps.append(loc_elem.text)
    
    lang_filter_str = language_filter or "none"
    Actor.log.info(
        f'Found {len(product_sitemaps)} product sitemaps '
        f'(filter: {lang_filter_str})'
    )
    
    # Fetch child sitemaps in parallel
    tasks = [
        fetch_sitemap_product_urls(url, None)
        for url in product_sitemaps
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    urls = []
    for idx, result in enumerate(results, 1):
        if isinstance(result, Exception):
            Actor.log.error(f'Error fetching sitemap {idx}: {result}')
        else:
            urls.extend(result)
    
    Actor.log.info(f'Total URLs collected: {len(urls)}')
    return urls


@lru_cache(maxsize=32)
async def fetch_sitemap_product_urls(
    sitemap_url: str,
    language_filter: str = None
) -> list[str]:
    """Fetch sitemap XML and extract product URLs with caching.

    Args:
        sitemap_url: URL of the sitemap
        language_filter: Only return '_ar.xml' or '_en.xml' sitemaps

    Returns:
        List of product URLs
    """
    try:
        Actor.log.info(f'Fetching sitemap from: {sitemap_url}')

        client = httpx.AsyncClient(
            timeout=SITEMAP_TIMEOUT,
            headers={'User-Agent': USER_AGENT},
            follow_redirects=True
        )

        try:
            response = await client.get(sitemap_url)
            status = response.status_code
            length = len(response.content)
            Actor.log.info(
                f'Received response (status: {status}, length: {length})'
            )

            root = ET.fromstring(response.content)
            
            # Try to extract URLs directly
            urls = await _fetch_sitemap_urls(root)
            
            # If no URLs, this is a sitemap index
            if not urls:
                urls = await _fetch_child_sitemaps(root, language_filter)
            
            return urls

        finally:
            await client.aclose()

    except Exception as e:
        Actor.log.exception(f'Error fetching sitemap: {e}')
        return []


def _extract_nutriments(nutriments: dict) -> dict:
    """Extract nutrition data per 100g from Open Food Facts."""
    per_100g = {
        'energy_kcal': nutriments.get('energy-kcal_100g'),
        'fat': nutriments.get('fat_100g'),
        'saturated_fat': nutriments.get('saturated-fat_100g'),
        'carbohydrates': nutriments.get('carbohydrates_100g'),
        'sugars': nutriments.get('sugars_100g'),
        'fiber': nutriments.get('fiber_100g'),
        'proteins': nutriments.get('proteins_100g'),
        'salt': nutriments.get('salt_100g'),
        'sodium': nutriments.get('sodium_100g'),
    }
    return {k: v for k, v in per_100g.items() if v is not None}


def _extract_serving_nutriments(nutriments: dict) -> dict:
    """Extract nutrition data per serving from Open Food Facts."""
    per_serving = {
        'energy_kcal': nutriments.get('energy-kcal_serving'),
        'fat': nutriments.get('fat_serving'),
        'saturated_fat': nutriments.get('saturated-fat_serving'),
        'carbohydrates': nutriments.get('carbohydrates_serving'),
        'sugars': nutriments.get('sugars_serving'),
        'fiber': nutriments.get('fiber_serving'),
        'proteins': nutriments.get('proteins_serving'),
        'salt': nutriments.get('salt_serving'),
        'sodium': nutriments.get('sodium_serving'),
    }
    return {k: v for k, v in per_serving.items() if v is not None}


@lru_cache(maxsize=128)
async def fetch_nutrition_facts(barcode: str) -> dict:
    """Fetch nutrition facts from Open Food Facts API with caching.

    Args:
        barcode: Product barcode/EAN/GTIN

    Returns:
        Dictionary with nutrition facts or empty dict if not found
    """
    if not barcode:
        return {}
    
    try:
        url = f'{OFF_API_BASE}/{barcode}.json'
        
        client = httpx.AsyncClient(
            timeout=API_TIMEOUT,
            headers={'User-Agent': 'CarrefourScraper/1.0'},
            follow_redirects=True
        )
        
        try:
            response = await client.get(url)
            
            if response.status_code != 200:
                return {}
            
            data = response.json()
            if data.get('status') != 1 or 'product' not in data:
                return {}
            
            product = data['product']
            nutriments = product.get('nutriments', {})
            
            nutrition = {
                'nutriscore_grade': product.get('nutriscore_grade'),
            }
            
            # Add serving size information
            serving_size = product.get('serving_size')
            serving_quantity = product.get('serving_quantity')
            if serving_size:
                nutrition['serving_size'] = serving_size
            if serving_quantity:
                nutrition['serving_quantity'] = serving_quantity
            
            # Extract per 100g nutrition
            per_100g = _extract_nutriments(nutriments)
            if per_100g:
                nutrition['per_100g'] = per_100g
            
            # Extract per serving nutrition
            per_serving = _extract_serving_nutriments(nutriments)
            if per_serving:
                nutrition['per_serving'] = per_serving
            
            return nutrition
                    
        finally:
            await client.aclose()
            
    except Exception as e:
        Actor.log.debug(f'Failed to fetch nutrition for {barcode}: {e}')
    
    return {}


async def _fetch_bilingual_sitemaps(
    sitemap_url: str
) -> tuple[list[str], list[str]]:
    """Fetch Arabic and English sitemaps concurrently.
    
    Returns:
        Tuple of (arabic_urls, english_urls)
    """
    try:
        ar_task = fetch_sitemap_product_urls(sitemap_url, 'ar')
        en_task = fetch_sitemap_product_urls(sitemap_url, 'en')
        ar_urls, en_urls = await asyncio.gather(
            ar_task, en_task, return_exceptions=True
        )

        if isinstance(ar_urls, Exception):
            Actor.log.error(f'Error fetching Arabic sitemaps: {ar_urls}')
            ar_urls = []
        if isinstance(en_urls, Exception):
            Actor.log.error(f'Error fetching English sitemaps: {en_urls}')
            en_urls = []
        
        return ar_urls, en_urls

    except Exception as e:
        Actor.log.error(f'Error in parallel sitemap fetching: {e}')
        return [], []


def _limit_urls_balanced(
    ar_urls: list[str],
    en_urls: list[str],
    max_pages: int
) -> list[str]:
    """Limit URLs while maintaining language balance."""
    ar_limit = min(len(ar_urls), max_pages // 2)
    en_limit = min(len(en_urls), max_pages - ar_limit)
    limited_urls = ar_urls[:ar_limit] + en_urls[:en_limit]
    all_urls = list(set(limited_urls))
    
    Actor.log.info(
        f'Limited to {len(all_urls)} unique URLs '
        f'(AR: {ar_limit}, EN: {en_limit})'
    )
    return all_urls


def _get_browser_launch_options() -> dict:
    """Get Playwright browser launch options."""
    return {
        'args': [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor'
        ]
    }


async def _fetch_nutrition_for_products(
    products_by_sku: dict
) -> dict[str, dict]:
    """Pre-fetch nutrition facts for all products in parallel.
    
    Returns:
        Dictionary mapping barcode to nutrition facts
    """
    barcodes = []
    for lang_data in products_by_sku.values():
        first_data = lang_data.get('ar') or lang_data.get('en') or {}
        barcode = first_data.get('barcode', '')
        if barcode:
            barcodes.append(barcode)
    
    Actor.log.info(
        f'Fetching nutrition facts for {len(barcodes)} products '
        f'in parallel...'
    )
    
    tasks = [fetch_nutrition_facts(bc) for bc in barcodes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    Actor.log.info('Nutrition facts fetched')
    return dict(zip(barcodes, results))


def _determine_availability(ar_avail: str, en_avail: str) -> str:
    """Smart availability check across languages."""
    if ar_avail == 'In Stock' or en_avail == 'In Stock':
        return 'In Stock'
    elif ar_avail == 'Out of Stock' and en_avail == 'Out of Stock':
        return 'Out of Stock'
    elif ar_avail != 'Unknown':
        return ar_avail
    elif en_avail != 'Unknown':
        return en_avail
    else:
        return 'Unknown'


def _create_bilingual_product(
    sku: str,
    lang_data: dict,
    nutrition_cache: dict
) -> dict:
    """Create merged bilingual product record."""
    first_data = lang_data.get('ar') or lang_data.get('en') or {}
    
    ar_avail = lang_data.get('ar', {}).get('availability', 'Unknown')
    en_avail = lang_data.get('en', {}).get('availability', 'Unknown')
    availability = _determine_availability(ar_avail, en_avail)
    
    bilingual_product = {
        'type': 'carrefour_product_bilingual',
        'sku': sku,
        'brand': first_data.get('brand', ''),
        'price': first_data.get('price', ''),
        'currency': first_data.get('currency', 'EGP'),
        'availability': availability,
        'size': first_data.get('size', ''),
        'barcode': first_data.get('barcode', ''),
        'images': {
            'main': first_data.get('main_image', ''),
            'gallery': first_data.get('images', [])
        },
        'nutrition_facts': {},
        'arabic': {},
        'english': {}
    }
    
    # Add nutrition facts from cache
    barcode = first_data.get('barcode', '')
    if barcode and barcode in nutrition_cache:
        nutrition = nutrition_cache[barcode]
        if nutrition and not isinstance(nutrition, Exception):
            bilingual_product['nutrition_facts'] = nutrition
            Actor.log.debug(f'Found nutrition data for barcode {barcode}')
    
    # Add language-specific data
    for lang, key in [('ar', 'arabic'), ('en', 'english')]:
        if lang in lang_data:
            data = lang_data[lang]
            bilingual_product[key] = {
                'url': data.get('url', ''),
                'name': data.get('product_name', ''),
                'category': data.get('category', ''),
                'description': data.get('description', ''),
                'page_title': data.get('page_title', '')
            }
        else:
            bilingual_product[key] = {
                'url': '', 'name': '', 'category': '',
                'description': '', 'page_title': ''
            }
    
    return bilingual_product


def _log_performance_stats(start_time: float) -> None:
    """Log performance statistics."""
    total_time = time.time() - start_time
    total_pages = performance_stats['playwright_pages']
    
    Actor.log.info('=' * 60)
    Actor.log.info('PERFORMANCE STATISTICS')
    Actor.log.info('=' * 60)
    Actor.log.info(f'Total pages processed: {total_pages}')
    Actor.log.info(f'Total time: {total_time:.2f}s')
    
    if total_pages > 0:
        avg_time = total_time / total_pages
        Actor.log.info(f'Average per page: {avg_time:.2f}s')
    else:
        Actor.log.info('Average per page: N/A')
    
    Actor.log.info('')
    Actor.log.info(f'Playwright pages: {total_pages}')
    
    if total_pages > 0:
        pw_time = performance_stats["playwright_time"]
        Actor.log.info(f'  Total time: {pw_time:.2f}s')
        Actor.log.info(f'  Avg per page: {pw_time/total_pages:.2f}s')
    
    Actor.log.info('')
    next_data = performance_stats["next_data_extractions"]
    Actor.log.info(f'Description extractions from __NEXT_DATA__: {next_data}')
    
    btn_clicks = performance_stats["button_clicks"]
    Actor.log.info(f'Description button clicks: {btn_clicks}')
    Actor.log.info('=' * 60)


async def main() -> None:
    """Main entry point."""
    async with Actor:
        actor_input = await Actor.get_input() or {}
        sitemap_url = actor_input.get(
            'sitemap_url',
            'https://www.carrefouregypt.com/sitemap.xml'
        )
        max_pages = actor_input.get('max_pages_per_crawl', 100)
        
        start_time = time.time()
        Actor.log.info(
            f'Input: sitemap_url={sitemap_url}, max_pages={max_pages}'
        )
        
        # Temporary storage for products by SKU
        products_by_sku = {}
        Actor.products_by_sku = products_by_sku
        
        # Fetch bilingual sitemaps
        Actor.log.info(
            'Fetching Arabic and English sitemaps concurrently...'
        )
        ar_urls, en_urls = await _fetch_bilingual_sitemaps(sitemap_url)
        
        Actor.log.info(f'Found {len(ar_urls)} Arabic URLs')
        Actor.log.info(f'Found {len(en_urls)} English URLs')
        
        # Combine and deduplicate URLs
        all_urls = list(set(ar_urls + en_urls))
        ar_count = len(ar_urls)
        en_count = len(en_urls)
        Actor.log.info(
            f'Total unique URLs: {len(all_urls)} '
            f'(AR: {ar_count}, EN: {en_count})'
        )

        # Limit URLs if needed
        if max_pages > 0:
            all_urls = _limit_urls_balanced(ar_urls, en_urls, max_pages)

        # Create requests
        start_urls = [Request.from_url(url) for url in all_urls]
        Actor.log.info(f'Starting crawl with {len(start_urls)} product URLs')
        
        # Create crawler
        max_requests = len(start_urls) if max_pages > 0 else None
        crawler = PlaywrightCrawler(
            max_requests_per_crawl=max_requests,
            request_handler=product_page_handler,
            headless=True,
            browser_type='chromium',
            browser_launch_options=_get_browser_launch_options()
        )
        
        # Crawl all pages
        await crawler.run(start_urls)
        
        # Merge products by SKU
        Actor.log.info(f'Merging {len(products_by_sku)} products by SKU...')
        
        # Fetch nutrition facts
        nutrition_cache = await _fetch_nutrition_for_products(
            products_by_sku
        )
        
        # Create and save bilingual products
        for sku, lang_data in products_by_sku.items():
            bilingual_product = _create_bilingual_product(
                sku, lang_data, nutrition_cache
            )
            
            ar_name = bilingual_product['arabic'].get('name', 'N/A')
            en_name = bilingual_product['english'].get('name', 'N/A')
            price = bilingual_product.get('price', '')
            currency = bilingual_product.get("currency", "")
            
            Actor.log.info(
                f'Merged: {ar_name} / {en_name} - {price} {currency}'
            )
            
            await Actor.push_data(bilingual_product)
        
        _log_performance_stats(start_time)


def _extract_regex_field(
    pattern: str,
    content: str,
    field_name: str
) -> str | None:
    """Extract field using regex pattern."""
    match = re.search(pattern, content)
    if match:
        return match.group(1)
    return None


def _is_valid_description(text: str) -> bool:
    """Check if description text is valid (not navigation)."""
    nav_indicators = [
        'All Categories', 'جميع الفئات',
        'Fresh Food', 'Beverages'
    ]
    contains_nav = any(kw in text for kw in nav_indicators)
    return text and len(text) > 10 and not contains_nav


async def extract_from_embedded_json(
    page: Any,
    product_data: dict
) -> None:
    """Extract data from embedded JavaScript (Phase 1).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
    """
    try:
        content = await page.content()
        
        if 'pdpResponse' not in content:
            return
        
        # Find pdpResponse section
        pdp_start = content.find('pdpResponse')
        if pdp_start == -1:
            return
        
        # Extract chunk (50KB should be enough)
        chunk_end = min(pdp_start + 50000, len(content))
        pdp_chunk = content[pdp_start:chunk_end]
        
        # Extract fields using regex
        extractions = [
            (r'\\"title\\":\\"([^\\]{5,200})\\"', 'product_name'),
            (r'\\"sku\\":\\"(\d+)\\"', 'sku'),
            (r'\\"imageURL\\":\\"(https?://[^\\]+)\\"', 'main_image'),
            (r'\\"price\\":\s*\\{\s*\\"price\\":\s*([\d.]+)', 'price'),
            (r'\\"currency\\":\\"([A-Z]{3})\\"', 'currency'),
        ]
        
        for pattern, field in extractions:
            if not product_data.get(field):
                value = _extract_regex_field(pattern, pdp_chunk, field)
                if value:
                    product_data[field] = value
        
        # Extract description (more complex)
        if not product_data.get('description'):
            desc_pattern = r'\\"description\\":\\"([^\\]{15,500})\\"'
            for match in re.finditer(desc_pattern, pdp_chunk):
                desc_text = match.group(1).strip()
                if _is_valid_description(desc_text):
                    product_data['description'] = desc_text
                    performance_stats['next_data_extractions'] += 1
                    short_desc = desc_text[:50]
                    Actor.log.info(
                        f'✓ Extracted description from pdpResponse: '
                        f'{short_desc}...'
                    )
                    break
    
    except Exception as e:
        Actor.log.debug(f'Could not extract from embedded data: {e}')


async def extract_from_json_ld(page: Any, product_data: dict) -> bool:
    """Extract data from JSON-LD structured data (Phase 2).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
        
    Returns:
        True if extraction was successful
    """
    try:
        selector = 'script[type="application/ld+json"]'
        json_ld_content = await page.locator(selector).first.inner_text()
        structured_data = json.loads(json_ld_content)
        
        if not isinstance(structured_data, dict):
            Actor.log.warning('Invalid JSON-LD structure')
            return False
        
        # Extract basic fields
        fields = [
            ('sku', 'sku'),
            ('name', 'product_name'),
            ('productCategory', 'category'),
            ('brand', 'brand'),
            ('description', 'description'),
        ]
        
        for json_key, data_key in fields:
            if not product_data.get(data_key):
                value = structured_data.get(json_key, '')
                if value:
                    product_data[data_key] = value
        
        # Extract image
        if not product_data.get('main_image'):
            image = structured_data.get('image')
            if isinstance(image, str):
                product_data['main_image'] = image
            elif isinstance(image, list) and image:
                product_data['main_image'] = image[0]
        
        # Extract offers
        if not product_data.get('price'):
            offers = structured_data.get('offers', {})
            if isinstance(offers, dict):
                product_data['currency'] = offers.get('priceCurrency', 'SAR')
                product_data['price'] = str(offers.get('price', ''))
                
                availability_url = offers.get('availability', '')
                if 'InStock' in availability_url:
                    product_data['availability'] = 'In Stock'
                elif 'OutOfStock' in availability_url:
                    product_data['availability'] = 'Out of Stock'
        
        return True
    
    except Exception as e:
        Actor.log.warning(f'JSON-LD extraction failed: {e}')
        return False


async def extract_barcode(page: Any, product_data: dict) -> None:
    """Extract barcode from additionalAttributes section matching the product SKU (Phase 3).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
    """
    if product_data.get('barcode'):
        return
    
    try:
        content = await page.content()
        sku = product_data.get('sku', '')
        
        if not sku:
            Actor.log.debug('No SKU available for barcode extraction')
            return
        
        # Find ALL additionalAttributes sections and look for the one matching our SKU
        search_pos = 0
        found = False
        
        while True:
            attr_start = content.find('additionalAttributes', search_pos)
            if attr_start == -1:
                break
            
            # Extract chunk after this additionalAttributes (5KB should be enough)
            chunk_end = min(attr_start + 5000, len(content))
            attr_chunk = content[attr_start:chunk_end]
            
            # Check if this section has our productId/SKU
            sku_pattern = f'productId\\":\\"{sku}\\"'
            if sku_pattern in attr_chunk:
                # This is our product's additionalAttributes section
                # Now extract barcode from within this section
                barcode_match = re.search(r'\\"barcode\\":\\"(\d{8,14})\\"', attr_chunk)
                if barcode_match:
                    product_data['barcode'] = barcode_match.group(1)
                    Actor.log.info(f'✓ Extracted barcode {barcode_match.group(1)} from additionalAttributes matching SKU {sku}')
                    found = True
                    break
                else:
                    Actor.log.debug(f'Found additionalAttributes for SKU {sku} but no barcode in it')
            
            # Move to next occurrence
            search_pos = attr_start + 1
        
        if not found:
            # Fallback: try simple pattern in full content
            barcode_match = re.search(r'barcode\\":\\"(\d{8,14})\\"', content)
            if barcode_match:
                product_data['barcode'] = barcode_match.group(1)
                Actor.log.debug(f'Extracted barcode from fallback pattern: {barcode_match.group(1)}')
    except Exception as e:
        Actor.log.debug(f'Failed to extract barcode: {e}')


async def extract_pack_size(page: Any, product_data: dict) -> None:
    """Extract pack size from page (Phase 3).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
    """
    if product_data.get('size'):
        return
    
    try:
        # Try locator for Pack Size label
        selector = 'span:has-text("Pack Size"), span:has-text("حجم العبوة")'
        pack_size_locator = page.locator(selector).first
        
        if await pack_size_locator.count() > 0:
            parent = pack_size_locator.locator('..').first
            size_elem = parent.locator('span.font-bold').first
            
            if await size_elem.count() > 0:
                product_data['size'] = await size_elem.inner_text()
                return
        
        # Fallback: Extract from product name
        size_pattern = (
            r'(\d+(?:\.\d+)?)\s*'
            r'(ml|l|gm|g|kg|oz|liter|litre|gram|kilogram|'
            r'ml|Ml|ML|Gm|GM|L|KG)\b'
        )
        size_match = re.search(
            size_pattern,
            product_data.get('product_name', ''),
            re.IGNORECASE
        )
        
        if size_match:
            amount = size_match.group(1)
            unit = size_match.group(2).lower()
            product_data['size'] = f"{amount} {unit}"
        else:
            product_data['size'] = ''
    
    except Exception:
        product_data['size'] = ''


async def extract_description_with_button(
    page: Any,
    product_data: dict,
    url: str
) -> None:
    """Extract description by clicking button (Phase 4).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
        url: Page URL for logging
    """
    if product_data.get('description'):
        return
    
    try:
        Actor.log.debug(f'Extracting description by clicking button')

        # Try to click description button
        desc_button_clicked = False
        
        for testid in ['Description', 'الوصف']:
            try:
                button = page.locator(f'button[data-testid="{testid}"]')
                if await button.count() > 0:
                    await button.first.click()
                    desc_button_clicked = True
                    performance_stats['button_clicks'] += 1
                    Actor.log.info(f'Clicked description button ({testid})')
                    break
            except Exception as e:
                msg = f'Failed to click button with testid {testid}: {e}'
                Actor.log.debug(msg)

        if not desc_button_clicked:
            Actor.log.debug('No description button found')
            return
        
        # Wait for content
        await page.wait_for_timeout(400)
        
        # Try Playwright extraction first
        desc_locator = page.locator('div.px-md.py-lg div.text-md').first
        if await desc_locator.count() > 0:
            desc_text = await desc_locator.inner_text()
            if desc_text and len(desc_text.strip()) > 0:
                product_data['description'] = desc_text.strip()
                short_desc = desc_text[:60]
                Actor.log.info(f'Extracted description: {short_desc}...')
                return
        
        # Fallback to BeautifulSoup
        await _extract_description_with_bs4(page, product_data)
    
    except Exception as e:
        Actor.log.warning(f'Could not extract description: {e}')


async def _extract_description_with_bs4(
    page: Any,
    product_data: dict
) -> None:
    """Extract description using BeautifulSoup fallback."""
    if product_data.get('description'):
        return
    
    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find divs with specific classes
    class_check = lambda c: c and 'px-md' in c and 'py-lg' in c
    padding_divs = soup.find_all('div', class_=class_check)
    
    for div in padding_divs:
        text_md_check = lambda c: c and 'text-md' in c
        text_md = div.find('div', class_=text_md_check)
        
        if text_md:
            text = text_md.get_text(strip=True)
            
            # Filter out navigation
            nav_indicators = [
                'All Categories', 'جميع الفئات', 'Fresh Food',
                'Beverages', 'Electronics', 'Frozen Food', 'Baby Products'
            ]
            nav_count = sum(1 for kw in nav_indicators if kw in text)
            
            if text and len(text) > 3 and nav_count < 2:
                product_data['description'] = text
                short_text = text[:60]
                Actor.log.info(
                    f'Extracted description via BS4: {short_text}...'
                )
                break


async def extract_images(page: Any, product_data: dict) -> None:
    """Extract product images (Phase 5).
    
    Args:
        page: Playwright page object
        product_data: Product data dictionary to update
    """
    if product_data.get('images'):
        return
    
    images = []
    try:
        product_name = product_data.get("product_name", "")[:30]
        img_locators = page.locator(f'img[alt*="{product_name}"]')
        count = await img_locators.count()
        
        for i in range(min(count, 5)):
            src = await img_locators.nth(i).get_attribute('src')
            if not src:
                src = await img_locators.nth(i).get_attribute('data-src')
            if src and 'cdn.mafrservices.com' in src:
                images.append(src)
    except Exception:
        pass
    
    product_data['images'] = images


async def product_page_handler(context: PlaywrightCrawlingContext) -> None:
    """Extract product data and store by SKU for later merging."""
    start_time = time.time()
    url = str(context.request.url)
    page = context.page
    
    # Block resources to speed up page loads
    block_pattern = '**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf}'
    await page.route(block_pattern, lambda route: route.abort())
    
    # Detect language
    if '/ar/' in url:
        language = 'ar'
    elif '/en/' in url:
        language = 'en'
    else:
        language = 'unknown'
    
    # Initialize product data
    product_data = {
        'url': url,
        'product_name': '',
        'category': '',
        'description': '',
        'sku': '',
        'brand': '',
        'page_title': '',
        'barcode': '',
        'size': '',
        'main_image': '',
        'images': [],
        'price': '',
        'currency': '',
        'availability': 'Unknown',
    }
    
    # Phase 1: Extract from embedded JSON
    await extract_from_embedded_json(page, product_data)
    
    # Phase 2: Fallback to JSON-LD
    if not product_data['sku'] or not product_data['product_name']:
        success = await extract_from_json_ld(page, product_data)
        if not success:
            return
    
    # Validate SKU
    if not product_data['sku']:
        Actor.log.warning(f'No SKU found for {url}')
        return
    
    product_data['page_title'] = await page.title() if page else ''
    
    # Phase 3: Extract remaining fields
    await extract_barcode(page, product_data)
    await extract_pack_size(page, product_data)
    
    # Phase 4: Button click for description
    await extract_description_with_button(page, product_data, url)
    
    # Phase 5: Extract images
    await extract_images(page, product_data)
    
    # Store by SKU and language
    sku = product_data['sku']
    if sku not in Actor.products_by_sku:
        Actor.products_by_sku[sku] = {}
    
    Actor.products_by_sku[sku][language] = product_data
    
    # Log performance
    elapsed = time.time() - start_time
    performance_stats['playwright_pages'] += 1
    performance_stats['playwright_time'] += elapsed
    
    name = product_data["product_name"]
    Actor.log.info(
        f'[Playwright] Extracted ({language}): {name} - '
        f'SKU: {sku} ({elapsed:.2f}s)'
    )
