#!/usr/bin/env python3
"""
Qwen VL OCR Processing for Common School Archive
Uses Qwen VL Plus vision model via OpenRouter API for document transcription
"""

import os
import json
import base64
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import hashlib

import aiohttp
from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path
from loguru import logger
import yaml
from tqdm import tqdm

# Load environment variables
load_dotenv()

class QwenVLOCR:
    """Qwen VL Plus OCR processor for historical documents"""
    
    def __init__(self, config_path: str = "ocr_config.yaml"):
        self.api_key = os.getenv("OPENROUTER_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_KEY not found in environment variables")
        
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "qwen/qwen-vl-plus"
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Setup output directories
        self.output_dir = Path(self.config.get("output_dir", "./output/ocr"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.output_dir / "text").mkdir(exist_ok=True)
        (self.output_dir / "metadata").mkdir(exist_ok=True)
        (self.output_dir / "logs").mkdir(exist_ok=True)
        
        # Setup logging
        log_file = self.output_dir / "logs" / f"ocr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logger.add(log_file, rotation="10 MB")
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        if Path(config_path).exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return self._default_config()
    
    def _default_config(self) -> dict:
        """Default configuration settings"""
        return {
            "output_dir": "./output/ocr",
            "max_image_size": (4000, 4000),
            "jpeg_quality": 95,
            "batch_size": 5,
            "max_retries": 3,
            "retry_delay": 2,
            "max_tokens": 4000,
            "temperature": 0.1,
            "prompts": {
                "historical_document": self._get_historical_prompt(),
                "handwritten": self._get_handwritten_prompt(),
                "typed": self._get_typed_prompt(),
                "mixed": self._get_mixed_prompt()
            }
        }
    
    def _get_historical_prompt(self) -> str:
        """Prompt for historical document OCR"""
        return """You are an expert at transcribing historical documents from the New York State Common School system (1800s-1900s).

Please transcribe this document image following these rules:
1. Preserve original spelling, capitalization, and punctuation exactly as written
2. Maintain original line breaks and formatting where possible
3. For unclear text, use [?] to indicate uncertainty
4. For completely illegible sections, use [illegible]
5. Note any stamps, seals, or marginal annotations in brackets [stamp: ...]
6. Preserve archaic spellings and abbreviations (e.g., "inst." for instant, "&c" for etc.)

Additional context:
- Common terms: selectmen, freeholders, trustees, district, common school
- Typical content: meeting minutes, district formations, tax rolls, teacher appointments
- Date formats often use "instant" to mean current month

Transcribe the complete text from the image:"""

    def _get_handwritten_prompt(self) -> str:
        """Prompt specifically for handwritten documents"""
        return """You are an expert at reading 19th century American handwriting, particularly administrative and legal documents.

Transcribe this handwritten document with special attention to:
1. Period-appropriate script styles and letterforms
2. Common abbreviations and contractions of the era
3. Preserve exact spelling even if archaic
4. Use [?] for uncertain characters or words
5. Note any corrections, insertions, or strikethroughs as [correction: ...]
6. Identify different hands if multiple writers present as [different hand:]

Focus on accuracy over interpretation. Transcribe exactly what is written:"""

    def _get_typed_prompt(self) -> str:
        """Prompt for typewritten documents"""
        return """Transcribe this typewritten historical document exactly as it appears.

Rules:
1. Preserve all formatting, spacing, and alignment
2. Maintain original typos and spelling
3. Note any handwritten additions as [handwritten: ...]
4. Indicate stamps or seals as [stamp: ...]
5. Use [?] for unclear characters due to print quality
6. Preserve headers, footers, and page numbers

Transcribe the document:"""

    def _get_mixed_prompt(self) -> str:
        """Prompt for documents with both typed and handwritten content"""
        return """This document contains both typewritten and handwritten text. Transcribe all content exactly.

Instructions:
1. Clearly distinguish between typed and handwritten sections
2. Use [typed:] and [handwritten:] markers when switching between modes
3. Preserve all original text exactly as written
4. Note any forms, tables, or structured layouts
5. Use [?] for uncertain text
6. Indicate any stamps, seals, or official markings

Transcribe all visible text:"""

    async def process_image(self, image_path: Path, document_type: str = "historical_document") -> Dict:
        """Process a single image with DeepSeek OCR"""
        try:
            # Load and prepare image
            image_data = self._prepare_image(image_path)
            
            # Select appropriate prompt
            prompt = self.config["prompts"].get(document_type, self.config["prompts"]["historical_document"])
            
            # Make API request
            result = await self._call_deepseek_api(image_data, prompt)
            
            # Save results
            output_path = self._save_results(image_path, result)
            
            logger.info(f"Successfully processed: {image_path.name}")
            
            return {
                "status": "success",
                "source": str(image_path),
                "output": str(output_path),
                "timestamp": datetime.now().isoformat(),
                "document_type": document_type,
                "text_length": len(result.get("text", "")),
                "confidence": result.get("confidence"),
                "checksum": self._calculate_checksum(image_path)
            }
            
        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            return {
                "status": "error",
                "source": str(image_path),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _prepare_image(self, image_path: Path) -> str:
        """Prepare image for API submission"""
        with Image.open(image_path) as img:
            # Resize if necessary
            max_size = self.config["max_image_size"]
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                logger.debug(f"Resized image to {img.size}")
            
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Save to bytes
            from io import BytesIO
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=self.config["jpeg_quality"])
            
            # Encode to base64
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    async def _call_deepseek_api(self, image_data: str, prompt: str) -> Dict:
        """Call DeepSeek API via OpenRouter"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/cs-archive",
            "X-Title": "Common School Archive OCR"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": self.config["max_tokens"],
            "temperature": self.config["temperature"]
        }
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(self.config["max_retries"]):
                try:
                    async with session.post(self.base_url, headers=headers, json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            text = data['choices'][0]['message']['content']
                            return {
                                "text": text,
                                "model": self.model,
                                "usage": data.get("usage", {}),
                                "confidence": self._estimate_confidence(text)
                            }
                        else:
                            error_text = await response.text()
                            logger.warning(f"API error (attempt {attempt + 1}): {error_text}")
                            
                except Exception as e:
                    logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                
                if attempt < self.config["max_retries"] - 1:
                    await asyncio.sleep(self.config["retry_delay"] * (attempt + 1))
            
            raise Exception("Failed to get OCR response after all retries")
    
    def _estimate_confidence(self, text: str) -> float:
        """Estimate OCR confidence based on uncertainty markers"""
        if not text:
            return 0.0
        
        uncertainty_markers = text.count('[?]') + text.count('[illegible]')
        total_words = len(text.split())
        
        if total_words == 0:
            return 0.0
        
        # Simple confidence estimation
        confidence = max(0.0, 1.0 - (uncertainty_markers / total_words * 10))
        return round(confidence, 3)
    
    def _save_results(self, source_path: Path, result: Dict) -> Path:
        """Save OCR results to file"""
        # Create output filename based on source
        stem = source_path.stem
        
        # Save text
        text_path = self.output_dir / "text" / f"{stem}.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(result["text"])
        
        # Save metadata
        metadata = {
            "source_file": str(source_path),
            "processed_at": datetime.now().isoformat(),
            "model": result["model"],
            "usage": result.get("usage", {}),
            "confidence": result.get("confidence"),
            "text_length": len(result["text"]),
            "checksum": self._calculate_checksum(source_path)
        }
        
        metadata_path = self.output_dir / "metadata" / f"{stem}.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        return text_path
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    async def process_pdf(self, pdf_path: Path, document_type: str = "historical_document") -> List[Dict]:
        """Process a PDF file by converting to images and OCRing each page"""
        logger.info(f"Processing PDF: {pdf_path}")
        
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=300)
        results = []
        
        # Process each page
        for i, image in enumerate(tqdm(images, desc=f"Processing {pdf_path.name}")):
            # Save temporary image
            temp_path = self.output_dir / "temp" / f"{pdf_path.stem}_page_{i+1}.jpg"
            temp_path.parent.mkdir(exist_ok=True)
            image.save(temp_path, 'JPEG', quality=95)
            
            # Process the image
            result = await self.process_image(temp_path, document_type)
            result["page_number"] = i + 1
            result["source_pdf"] = str(pdf_path)
            results.append(result)
            
            # Clean up temp file
            temp_path.unlink()
        
        # Combine all pages into single document
        self._combine_pdf_results(pdf_path, results)
        
        return results
    
    def _combine_pdf_results(self, pdf_path: Path, results: List[Dict]):
        """Combine OCR results from all pages of a PDF"""
        combined_text = []
        combined_metadata = {
            "source_pdf": str(pdf_path),
            "processed_at": datetime.now().isoformat(),
            "total_pages": len(results),
            "pages": []
        }
        
        for result in results:
            if result["status"] == "success":
                # Read the text file
                text_path = Path(result["output"])
                if text_path.exists():
                    with open(text_path, 'r', encoding='utf-8') as f:
                        page_text = f.read()
                        combined_text.append(f"\n--- Page {result['page_number']} ---\n")
                        combined_text.append(page_text)
                
                combined_metadata["pages"].append({
                    "page": result["page_number"],
                    "status": result["status"],
                    "confidence": result.get("confidence"),
                    "text_length": result.get("text_length")
                })
        
        # Save combined results
        combined_text_path = self.output_dir / "text" / f"{pdf_path.stem}_complete.txt"
        with open(combined_text_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(combined_text))
        
        combined_metadata_path = self.output_dir / "metadata" / f"{pdf_path.stem}_complete.json"
        with open(combined_metadata_path, 'w', encoding='utf-8') as f:
            json.dump(combined_metadata, f, indent=2)
        
        logger.info(f"Combined PDF results saved to {combined_text_path}")
    
    async def process_batch(self, file_paths: List[Path], document_type: str = "historical_document"):
        """Process multiple files in batch"""
        results = []
        
        # Group files by type
        pdfs = [p for p in file_paths if p.suffix.lower() == '.pdf']
        images = [p for p in file_paths if p.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff']]
        
        # Process PDFs
        for pdf in pdfs:
            pdf_results = await self.process_pdf(pdf, document_type)
            results.extend(pdf_results)
        
        # Process images in batches
        batch_size = self.config["batch_size"]
        for i in range(0, len(images), batch_size):
            batch = images[i:i+batch_size]
            tasks = [self.process_image(img, document_type) for img in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        
        # Save batch summary
        self._save_batch_summary(results)
        
        return results
    
    def _save_batch_summary(self, results: List[Dict]):
        """Save summary of batch processing"""
        summary = {
            "processed_at": datetime.now().isoformat(),
            "total_files": len(results),
            "successful": sum(1 for r in results if r.get("status") == "success"),
            "failed": sum(1 for r in results if r.get("status") == "error"),
            "total_text_length": sum(r.get("text_length", 0) for r in results),
            "average_confidence": self._calculate_average_confidence(results),
            "files": results
        }
        
        summary_path = self.output_dir / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Batch summary saved to {summary_path}")
        logger.info(f"Processed {summary['successful']}/{summary['total_files']} files successfully")
    
    def _calculate_average_confidence(self, results: List[Dict]) -> float:
        """Calculate average confidence from results"""
        confidences = [r.get("confidence", 0) for r in results if r.get("status") == "success"]
        if not confidences:
            return 0.0
        return round(sum(confidences) / len(confidences), 3)


async def main():
    """Main entry point for testing"""
    ocr = QwenVLOCR()
    
    # Test with Kheel Center PDF
    kheel_pdf = Path("raw/scans/Kheel Center/Toward-Better-Schools.pdf")
    if kheel_pdf.exists():
        results = await ocr.process_pdf(kheel_pdf, document_type="typed")
        logger.info(f"Processed {len(results)} pages from Kheel Center PDF")
    
    # Test with sample images
    sample_images = list(Path("raw/imgs").glob("*.jpeg"))[:5]
    if sample_images:
        results = await ocr.process_batch(sample_images, document_type="handwritten")
        logger.info(f"Processed {len(results)} sample images")


if __name__ == "__main__":
    asyncio.run(main())