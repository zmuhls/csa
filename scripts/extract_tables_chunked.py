#!/usr/bin/env python3
"""
Extract tables with automatic chunking for large tables that exceed API limits.

Handles the ~4000 character API response truncation by:
1. Attempting full extraction first
2. On failure, extracting in chunks (rows 1-15, 16-30, etc.)
3. Merging chunks into complete table
"""

import asyncio
import aiohttp
import base64
import csv
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from pdf2image import convert_from_path
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class ChunkedTableExtractor:
    """Extract tables with automatic chunking for large tables"""

    def __init__(self, api_key: str, output_dir: Path):
        self.api_key = api_key
        self.output_dir = output_dir
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "qwen/qwen3-vl-32b-instruct"
        self.max_tokens = 16000
        self.temperature = 0.0
        self.timeout = 180
        self.max_retries = 3
        self.chunk_size = 12  # Extract 12 rows at a time

        log_file = output_dir / "logs" / f"chunked_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logger.add(log_file, rotation="10 MB")
        logger.info(f"Initialized ChunkedTableExtractor")

    def _prepare_image(self, image_path: Path) -> str:
        """Prepare image for API submission"""
        with Image.open(image_path) as img:
            if img.size[0] > 4000 or img.size[1] > 4000:
                img.thumbnail((4000, 4000), Image.Resampling.LANCZOS)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=95)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _get_prompt(self, chunk_info: Optional[Dict] = None) -> str:
        """Get extraction prompt (full or chunked)"""
        if chunk_info:
            # Chunked extraction
            start = chunk_info['start']
            end = chunk_info['end']
            return f"""Extract rows {start} to {end} from this table. Use compact array format.

Return JSON:
{{
  "c": "County",
  "t": "ufs|tsu|cd|crs",
  "h": ["col1", "col2", ...],
  "r": [
    ["val1", "val2", ...],
    ...
  ],
  "total": total_rows_in_table
}}

CRITICAL:
- rows are ARRAYS not objects
- Extract ONLY rows {start}-{end}, not the entire table
- Count total rows and return in "total" field
- Headers: short names (2-4 chars)
- Dates: combine "day month year" → "6 July 1915"
- Blanks: use ""

Table types: ufs=Union Free, tsu=Town Units, cd=Consolidated, crs=Central"""
        else:
            # Full extraction
            return """Extract ALL rows from this table. Use ultra-compact array format.

Return JSON:
{
  "c": "County",
  "t": "ufs|tsu|cd|crs",
  "h": ["col1", "col2", ...],
  "r": [
    ["val1", "val2", ...],
    ...
  ]
}

CRITICAL: rows are ARRAYS not objects. This saves 50% space.
Headers: short names (2-4 chars): "n", "town", "date_org", "date_appr", "n_new", "rmk"
Dates: combine "day month year" → "6 July 1915"
Blanks: use ""
Complete ALL rows

Table types: ufs=Union Free, tsu=Town Units, cd=Consolidated, crs=Central"""

    async def _call_api(self, image_b64: str, chunk_info: Optional[Dict] = None) -> Dict:
        """Call Qwen API"""
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
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": self._get_prompt(chunk_info)}
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }

        async with aiohttp.ClientSession() as session:
            for attempt in range(self.max_retries):
                try:
                    async with session.post(self.base_url, headers=headers, json=payload, timeout=self.timeout) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']

                            start = content.find('{')
                            end = content.rfind('}') + 1
                            if start >= 0 and end > start:
                                json_str = content[start:end]
                                result = json.loads(json_str)
                                return result

                        elif response.status == 429:
                            wait_time = 2 ** attempt
                            await asyncio.sleep(wait_time)
                        else:
                            error_text = await response.text()
                            logger.error(f"API error {response.status}: {error_text[:200]}")

                except json.JSONDecodeError as e:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(2)
                except asyncio.TimeoutError:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(2)
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise
                    await asyncio.sleep(2)

        raise Exception("Failed after max retries")

    async def extract_table_chunked(self, pdf_path: Path, page_num: int) -> Dict:
        """Extract table with automatic chunking if needed"""
        # Convert PDF page to image
        images = convert_from_path(pdf_path, dpi=300, first_page=page_num, last_page=page_num)
        if not images:
            raise Exception(f"Failed to convert page {page_num}")

        image = images[0]
        image_filename = f"{pdf_path.stem}_page_{page_num}.jpg"
        image_path = self.output_dir / "images" / image_filename
        image.save(image_path, 'JPEG', quality=95)

        image_b64 = self._prepare_image(image_path)

        # Try full extraction first
        try:
            logger.info(f"Page {page_num}: Attempting full extraction")
            table_data = await self._call_api(image_b64)
            logger.success(f"Page {page_num}: Full extraction successful")
            return self._format_result(pdf_path, page_num, image_path, table_data)

        except Exception as e:
            logger.warning(f"Page {page_num}: Full extraction failed ({e}), switching to chunked mode")

        # Chunked extraction
        try:
            # First, get total row count
            first_chunk = await self._call_api(image_b64, {"start": 1, "end": self.chunk_size})
            total_rows = first_chunk.get("total", 20)  # Default to 20 if not provided

            logger.info(f"Page {page_num}: Chunked extraction - estimated {total_rows} total rows")

            # Extract all chunks
            all_rows = first_chunk.get("r", [])
            county = first_chunk.get("c")
            table_type = first_chunk.get("t")
            headers = first_chunk.get("h", [])

            # Get remaining chunks
            current_row = self.chunk_size + 1
            while current_row <= total_rows:
                end_row = min(current_row + self.chunk_size - 1, total_rows)
                logger.info(f"Page {page_num}: Extracting rows {current_row}-{end_row}")

                chunk = await self._call_api(image_b64, {"start": current_row, "end": end_row})
                chunk_rows = chunk.get("r", [])

                if not chunk_rows:
                    logger.warning(f"Page {page_num}: No rows in chunk {current_row}-{end_row}, assuming end of table")
                    break

                all_rows.extend(chunk_rows)
                current_row = end_row + 1

                # Small delay to avoid rate limiting
                await asyncio.sleep(1)

            # Merge all chunks
            merged_data = {
                "c": county,
                "t": table_type,
                "h": headers,
                "r": all_rows
            }

            logger.success(f"Page {page_num}: Chunked extraction complete - {len(all_rows)} rows")
            return self._format_result(pdf_path, page_num, image_path, merged_data, chunked=True)

        except Exception as e:
            logger.error(f"Page {page_num}: Chunked extraction failed: {e}")
            raise

    def _format_result(self, pdf_path: Path, page_num: int, image_path: Path,
                       table_data: Dict, chunked: bool = False) -> Dict:
        """Format extraction result"""
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
                row_obj = {}
                for i, header in enumerate(headers):
                    row_obj[header] = row_array[i] if i < len(row_array) else None
                object_rows.append(row_obj)
            else:
                object_rows.append(row_array)

        return {
            "metadata": {
                "source_pdf": pdf_path.name,
                "source_pdf_path": str(pdf_path),
                "page_number": page_num,
                "page_image_path": str(image_path),
                "processed_at": datetime.now().isoformat(),
                "model": self.model,
                "county": county,
                "table_type": table_type,
                "extraction_method": "chunked" if chunked else "full"
            },
            "table": {
                "headers": headers,
                "rows": object_rows
            }
        }

    def save_outputs(self, result: Dict):
        """Save JSON, CSV, and Markdown outputs"""
        page_num = result["metadata"]["page_number"]
        pdf_stem = Path(result["metadata"]["source_pdf"]).stem

        # Save JSON
        json_path = self.output_dir / "json" / f"{pdf_stem}_page_{page_num}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Save CSV
        rows = result["table"]["rows"]
        headers = result["table"]["headers"]

        if rows and headers:
            csv_path = self.output_dir / "csv" / f"{pdf_stem}_page_{page_num}.csv"
            metadata_cols = ["source_pdf", "page_number", "county", "table_type", "row_index"]
            csv_headers = metadata_cols + headers

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_headers)
                writer.writeheader()

                for idx, row in enumerate(rows, 1):
                    csv_row = {
                        "source_pdf": result["metadata"]["source_pdf"],
                        "page_number": page_num,
                        "county": result["metadata"]["county"],
                        "table_type": result["metadata"]["table_type"],
                        "row_index": idx
                    }
                    csv_row.update(row)
                    writer.writerow(csv_row)

            # Save Markdown
            md_path = self.output_dir / "markdown" / f"{pdf_stem}_page_{page_num}.md"
            image_filename = f"{pdf_stem}_page_{page_num}.jpg"

            with open(md_path, 'w', encoding='utf-8') as f:
                # Write metadata header
                f.write(f"# {result['metadata']['county']} County\n\n")
                f.write(f"**Table Type:** {result['metadata']['table_type'].replace('_', ' ').title()}\n\n")
                f.write(f"**Source:** {result['metadata']['source_pdf']} (Page {page_num})\n\n")
                f.write(f"**Extraction Method:** {result['metadata']['extraction_method']}\n\n")
                f.write(f"**Processed:** {result['metadata']['processed_at']}\n\n")
                f.write(f"**Source Image:** [📄 {image_filename}](../images/{image_filename})\n\n")
                f.write("---\n\n")

                # Embed source image
                f.write("## Source Document\n\n")
                f.write(f"![{result['metadata']['county']} County - {result['metadata']['table_type'].replace('_', ' ').title()} - Page {page_num}](../images/{image_filename})\n\n")
                f.write("---\n\n")

                # Write table
                f.write("## Extracted Table\n\n")

                # Header row
                f.write("| " + " | ".join(headers) + " |\n")

                # Separator row
                f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")

                # Data rows
                for row in rows:
                    values = [str(row.get(h, "")) for h in headers]
                    f.write("| " + " | ".join(values) + " |\n")

    def is_page_processed(self, pdf_stem: str, page_num: int) -> bool:
        """Check if page already processed"""
        json_path = self.output_dir / "json" / f"{pdf_stem}_page_{page_num}.json"
        return json_path.exists()

    async def process_all_pages(self, pdf_path: Path, start_page: int = 1,
                                end_page: Optional[int] = None, force: bool = False):
        """Process all pages with chunked extraction"""
        if end_page is None:
            from pdf2image.pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(pdf_path)
            end_page = info.get('Pages', 117)

        pages_to_process = []
        for page_num in range(start_page, end_page + 1):
            if force or not self.is_page_processed(pdf_path.stem, page_num):
                pages_to_process.append(page_num)

        if not pages_to_process:
            logger.info("All pages already processed!")
            return

        logger.info(f"Processing {len(pages_to_process)} pages with chunked extraction")

        results = []
        failed = []

        for page_num in pages_to_process:
            try:
                result = await self.extract_table_chunked(pdf_path, page_num)
                self.save_outputs(result)
                results.append(result)
                logger.success(f"Page {page_num}: Saved - {len(result['table']['rows'])} rows")

            except Exception as e:
                logger.error(f"Page {page_num}: Failed - {e}")
                failed.append({"page": page_num, "error": str(e)})

        # Summary
        logger.info(f"\n{'='*80}")
        logger.info(f"PROCESSING COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Successfully processed: {len(results)}")
        logger.info(f"Failed: {len(failed)}")
        if failed:
            logger.warning(f"Failed pages: {[f['page'] for f in failed]}")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Extract tables with automatic chunking')
    parser.add_argument('--start-page', type=int, default=1, help='starting page number')
    parser.add_argument('--end-page', type=int, default=None, help='ending page number')
    parser.add_argument('--force', action='store_true', help='reprocess all pages, replacing existing outputs')
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_KEY not found")

    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "raw/scans/NYS Archives/B0494/District-Consolidation-Data_100-116.pdf"
    output_dir = project_root / "output/ocr/tables"

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Create output directories
    for subdir in ["json", "csv", "markdown", "images", "logs"]:
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    if args.force:
        logger.info("Force mode enabled - reprocessing all pages")

    extractor = ChunkedTableExtractor(api_key, output_dir)
    await extractor.process_all_pages(pdf_path, start_page=args.start_page, end_page=args.end_page, force=args.force)

    print(f"\nProcessing complete! Outputs saved to:")
    print(f"  JSON: {output_dir / 'json'}")
    print(f"  CSV: {output_dir / 'csv'}")
    print(f"  Markdown: {output_dir / 'markdown'}")


if __name__ == "__main__":
    asyncio.run(main())
