#!/usr/bin/env python3
"""
Extract structured tables from all pages of District-Consolidation-Data_100-116.pdf

Uses Qwen VL Plus to convert ledger tables to JSON/CSV format.
Supports resume capability - skips already-processed pages.
"""

import asyncio
import aiohttp
import base64
import csv
import json
import os
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from pdf2image import convert_from_path
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()


class TableExtractor:
    """Extract structured tables using Qwen VL Plus with JSON output"""

    def __init__(self, api_key: str, output_dir: Path):
        self.api_key = api_key
        self.output_dir = output_dir
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "qwen/qwen-vl-plus"
        self.max_tokens = 16000
        self.temperature = 0.0
        self.timeout = 240
        self.max_retries = 3
        self.max_image_size = (4000, 4000)
        self.jpeg_quality = 95

        # Set up logging
        log_file = output_dir / "logs" / f"table_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logger.add(log_file, rotation="10 MB")
        logger.info(f"Initialized TableExtractor with model {self.model}")

    def _prepare_image(self, image_path: Path) -> str:
        """Prepare image for API submission (resize, convert to JPEG, base64 encode)"""
        with Image.open(image_path) as img:
            # Resize if necessary
            if img.size[0] > self.max_image_size[0] or img.size[1] > self.max_image_size[1]:
                img.thumbnail(self.max_image_size, Image.Resampling.LANCZOS)

            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Save to bytes
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=self.jpeg_quality)

            # Encode to base64
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _get_system_prompt(self) -> str:
        """Get system prompt for table extraction"""
        return """Extract ALL rows from this NYS ledger table. Use ultra-compact array format.

Return JSON:
{
  "c": "County",
  "t": "ufs|tsu|cd|crs",
  "h": ["col1", "col2", ...],
  "r": [
    ["val1", "val2", ...],
    ["val1", "val2", ...],
    ...
  ]
}

CRITICAL: rows are ARRAYS not objects. This saves 50% space.

Headers: short names (2-4 chars): "n", "town", "date_org", "date_appr", "n_new", "rmk"
Dates: combine "day month year" → "6 July 1915"
Blanks: use "" not null
Complete ALL rows - don't stop early

Table types: ufs=Union Free, tsu=Town Units, cd=Consolidated, crs=Central"""

    async def _call_api(self, image_b64: str) -> Dict:
        """Call Qwen VL Plus via OpenRouter"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/cs-archive",
            "X-Title": "CS Archive Table Extraction"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "Extract the table data from this image following the JSON schema provided."
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        async with aiohttp.ClientSession() as session:
            for attempt in range(self.max_retries):
                try:
                    async with session.post(
                        self.base_url,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']

                            # Parse JSON from response
                            try:
                                # Find JSON in response (handle markdown code blocks)
                                start = content.find('{')
                                end = content.rfind('}') + 1
                                if start >= 0 and end > start:
                                    json_str = content[start:end]
                                    result = json.loads(json_str)
                                    return result
                            except json.JSONDecodeError as e:
                                logger.warning(f"JSON decode error (attempt {attempt + 1}): {e}")
                                # Save malformed JSON for debugging
                                if attempt == self.max_retries - 1:
                                    error_file = self.output_dir / "logs" / f"error_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                    with open(error_file, 'w') as f:
                                        f.write(json_str if 'json_str' in locals() else content)
                                    logger.error(f"Saved malformed JSON to {error_file}")
                                    raise

                        elif response.status == 429:
                            # Rate limited
                            wait_time = 2 ** attempt
                            logger.warning(f"Rate limited, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)

                        else:
                            error_text = await response.text()
                            logger.error(f"API error {response.status}: {error_text[:200]}")

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on attempt {attempt + 1}")
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Exception in API call: {e}")
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(2)

        raise Exception("Failed after max retries")

    async def extract_table_from_page(self, pdf_path: Path, page_num: int) -> Dict:
        """Extract table from a single PDF page"""
        start_time = datetime.now()

        # Convert PDF page to image
        images = convert_from_path(
            pdf_path,
            dpi=300,
            first_page=page_num,
            last_page=page_num
        )

        if not images:
            raise Exception(f"Failed to convert page {page_num}")

        image = images[0]

        # Save image for reference
        image_filename = f"{pdf_path.stem}_page_{page_num}.jpg"
        image_path = self.output_dir / "images" / image_filename
        image.save(image_path, 'JPEG', quality=95)

        # Prepare image for API
        image_b64 = self._prepare_image(image_path)

        # Call API
        table_data = await self._call_api(image_b64)

        # Add metadata
        processing_time = (datetime.now() - start_time).total_seconds()

        # Expand compact schema to full format
        county = table_data.get("c", "Unknown")
        table_type_map = {
            "ufs": "union_free_schools",
            "tsu": "town_school_units",
            "cd": "consolidated_districts",
            "crs": "central_rural_schools"
        }
        table_type = table_type_map.get(table_data.get("t", ""), "unknown")

        # Convert array rows to object rows
        headers = table_data.get("h", [])
        array_rows = table_data.get("r", [])
        object_rows = []

        for row_array in array_rows:
            if isinstance(row_array, list):
                # Convert array to object using headers
                row_obj = {}
                for i, header in enumerate(headers):
                    row_obj[header] = row_array[i] if i < len(row_array) else None
                object_rows.append(row_obj)
            else:
                # Already an object (fallback)
                object_rows.append(row_array)

        result = {
            "metadata": {
                "source_pdf": pdf_path.name,
                "source_pdf_path": str(pdf_path),
                "page_number": page_num,
                "page_image_path": str(image_path),
                "processed_at": datetime.now().isoformat(),
                "model": self.model,
                "processing_time_seconds": processing_time,
                "county": county,
                "table_type": table_type
            },
            "table": {
                "headers": headers,
                "rows": object_rows
            }
        }

        return result

    def save_json_output(self, result: Dict, output_path: Path):
        """Save result as JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    def save_csv_output(self, result: Dict, output_path: Path):
        """Convert table to CSV format"""
        rows = result["table"]["rows"]
        headers = result["table"]["headers"]

        if not rows or not headers:
            logger.warning(f"No rows or headers to export to CSV for page {result['metadata']['page_number']}")
            return

        # Add metadata columns
        metadata_cols = ["source_pdf", "page_number", "county", "table_type", "row_index"]
        csv_headers = metadata_cols + headers

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            writer.writeheader()

            for idx, row in enumerate(rows, 1):
                csv_row = {
                    "source_pdf": result["metadata"]["source_pdf"],
                    "page_number": result["metadata"]["page_number"],
                    "county": result["metadata"]["county"],
                    "table_type": result["metadata"]["table_type"],
                    "row_index": idx
                }
                csv_row.update(row)
                writer.writerow(csv_row)

    def is_page_processed(self, pdf_stem: str, page_num: int) -> bool:
        """Check if a page has already been processed"""
        json_path = self.output_dir / "json" / f"{pdf_stem}_page_{page_num}.json"
        return json_path.exists()

    async def process_all_pages(self, pdf_path: Path, start_page: int = 1, end_page: Optional[int] = None, batch_size: int = 5):
        """Process all pages in the PDF"""

        # Get total page count
        if end_page is None:
            # Quick check to get page count
            test_images = convert_from_path(pdf_path, dpi=72, last_page=1)
            from pdf2image.pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(pdf_path)
            end_page = info.get('Pages', 117)
            logger.info(f"Detected {end_page} pages in PDF")

        total_pages = end_page - start_page + 1
        pages_to_process = []

        # Check which pages need processing
        for page_num in range(start_page, end_page + 1):
            if self.is_page_processed(pdf_path.stem, page_num):
                logger.debug(f"Page {page_num} already processed, skipping")
            else:
                pages_to_process.append(page_num)

        if not pages_to_process:
            logger.info("All pages already processed!")
            return []

        logger.info(f"Processing {len(pages_to_process)} pages (skipping {total_pages - len(pages_to_process)} already processed)")

        results = []
        failed = []

        # Process in batches
        for i in range(0, len(pages_to_process), batch_size):
            batch = pages_to_process[i:i + batch_size]
            batch_results = await self._process_batch(pdf_path, batch)

            for page_num, result in zip(batch, batch_results):
                if "error" not in result:
                    results.append(result)
                    row_count = len(result['table']['rows']) if result['table']['rows'] else 0
                    logger.success(f"Page {page_num} completed - {row_count} rows")
                else:
                    failed.append({"page": page_num, "error": result["error"]})
                    logger.error(f"Page {page_num} failed: {result['error']}")

        # Generate summary
        logger.info(f"\n{'='*80}")
        logger.info(f"PROCESSING COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Total pages: {total_pages}")
        logger.info(f"Successfully processed: {len(results)}")
        logger.info(f"Failed: {len(failed)}")
        logger.info(f"Already existed: {total_pages - len(pages_to_process)}")

        if failed:
            logger.warning(f"\nFailed pages: {[f['page'] for f in failed]}")

        return results

    async def _process_batch(self, pdf_path: Path, page_numbers: List[int]) -> List[Dict]:
        """Process a batch of pages concurrently"""
        tasks = []
        for page_num in page_numbers:
            task = self._process_single_page(pdf_path, page_num)
            tasks.append(task)

        return await asyncio.gather(*tasks)

    async def _process_single_page(self, pdf_path: Path, page_num: int) -> Dict:
        """Process a single page with error handling"""
        try:
            logger.info(f"Processing page {page_num}")

            # Extract table
            result = await self.extract_table_from_page(pdf_path, page_num)

            # Save outputs
            json_path = self.output_dir / "json" / f"{pdf_path.stem}_page_{page_num}.json"
            csv_path = self.output_dir / "csv" / f"{pdf_path.stem}_page_{page_num}.csv"

            self.save_json_output(result, json_path)
            self.save_csv_output(result, csv_path)

            return result

        except Exception as e:
            logger.error(f"Failed to process page {page_num}: {e}")
            return {"error": str(e), "page": page_num}


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Extract tables from NYS county ledger PDF')
    parser.add_argument('--start-page', type=int, default=1, help='First page to process (default: 1)')
    parser.add_argument('--end-page', type=int, default=None, help='Last page to process (default: all)')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of concurrent requests (default: 5)')
    parser.add_argument('--force', action='store_true', help='Reprocess already-processed pages')

    args = parser.parse_args()

    # Configuration
    api_key = os.getenv("OPENROUTER_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_KEY not found in environment")

    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "raw/scans/NYS Archives/B0494/District-Consolidation-Data_100-116.pdf"
    output_dir = project_root / "output/ocr/tables"

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Initialize extractor
    extractor = TableExtractor(api_key, output_dir)

    # Clear existing files if force mode
    if args.force:
        logger.warning("Force mode enabled - will reprocess all pages")
        # Note: Not actually deleting files, just will overwrite them

    # Process all pages
    logger.info(f"Starting extraction from page {args.start_page} to {args.end_page or 'end'}")
    results = await extractor.process_all_pages(
        pdf_path,
        start_page=args.start_page,
        end_page=args.end_page,
        batch_size=args.batch_size
    )

    print(f"\nProcessing complete! Outputs saved to: {output_dir}")
    print(f"JSON files: {output_dir / 'json'}")
    print(f"CSV files: {output_dir / 'csv'}")


if __name__ == "__main__":
    asyncio.run(main())
