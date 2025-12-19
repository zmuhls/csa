#!/usr/bin/env python3
"""
Process archival materials using Qwen VL Plus OCR
Designed for the Common School Archive project
"""

import asyncio
import sys
import csv
from pathlib import Path
from datetime import datetime
import json

from ocr import QwenVLOCR
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/archive_processing_{time}.log", rotation="10 MB", level="DEBUG")


async def process_loose_images():
    """Process loose images from the inventory"""
    
    # Initialize OCR processor
    ocr = QwenVLOCR(config_path="ocr_config.yaml")
    logger.info("Initialized Qwen VL Plus OCR processor for Loose Images")
    
    inventory_path = Path("csv/images_inventory.csv")
    if not inventory_path.exists():
        logger.error(f"Inventory file not found: {inventory_path}")
        return
    
    # Read inventory
    images_to_process = []
    with open(inventory_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Verify file exists
            img_path = Path(row['relative_path'])
            if img_path.exists():
                images_to_process.append({
                    "path": img_path,
                    "id": row['id'],
                    "item_type": row.get('item_type', '')
                })
    
    logger.info(f"Found {len(images_to_process)} images in inventory")
    
    # Process in batches
    batch_size = 5  # Concurrent requests
    all_results = []
    
    for i in range(0, len(images_to_process), batch_size):
        batch = images_to_process[i:i+batch_size]
        tasks = []
        
        for img_data in batch:
            doc_type = map_item_type_to_ocr_type(img_data['item_type'])
            logger.info(f"Processing {img_data['path'].name} as {doc_type}")
            tasks.append(ocr.process_image(img_data['path'], document_type=doc_type))
        
        # Execute batch
        batch_results = await asyncio.gather(*tasks)
        
        # Add metadata from inventory to results
        for res, img_data in zip(batch_results, batch):
            if res.get("status") == "success":
                res["inventory_id"] = img_data['id']
                
        all_results.extend(batch_results)
        
        # Log progress
        completed = min((i + batch_size), len(images_to_process))
        logger.info(f"Progress: {completed}/{len(images_to_process)} images processed")

    # Generate processing report
    report = generate_processing_report(all_results, "Loose Images")
    
    # Save report
    report_path = Path("output/ocr/reports/images_processing_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Processing report saved to: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("LOOSE IMAGES PROCESSING SUMMARY")
    print("="*60)
    print(f"Total files processed: {len(images_to_process)}")
    print(f"Successful: {report['successful_pages']}")
    print(f"Failed: {report['failed_pages']}")
    print(f"Average confidence: {report['average_confidence']:.2%}")
    print(f"Total text extracted: {report['total_text_length']:,} characters")
    print(f"Report saved to: {report_path}")
    print("="*60)
    
    return report


def map_item_type_to_ocr_type(item_type: str) -> str:
    """Map inventory item_type to OCR document_type"""
    mapping = {
        "ledger_or_register": "mixed",
        "form": "table_form",
        "letter": "handwritten",
        "report": "typed",
        "notecard": "mixed",
        "meeting_minutes": "mixed",
        "pamphlet_or_brochure": "mixed",
        "document_page": "historical_document"
    }
    return mapping.get(item_type, "historical_document")


async def process_kheel_materials():
    """Process all Kheel Center PDFs and scanned materials"""
    
    # Initialize OCR processor
    ocr = QwenVLOCR(config_path="ocr_config.yaml")
    logger.info("Initialized Qwen VL Plus OCR processor")
    
    # Define Kheel Center materials
    kheel_base = Path("raw/scans/Kheel Center")
    
    if not kheel_base.exists():
        logger.error(f"Kheel Center directory not found: {kheel_base}")
        return
    
    # Find all PDFs in Kheel Center directory
    pdf_files = list(kheel_base.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files in Kheel Center collection")
    
    # Process each PDF
    all_results = []
    
    for pdf_path in pdf_files:
        logger.info(f"Processing: {pdf_path.name}")
        
        # Determine document type based on filename
        if "Toward-Better-Schools" in pdf_path.name:
            doc_type = "typed"
            logger.info("Document type: typed/published report")
        else:
            doc_type = "historical_document"
            logger.info("Document type: historical document (default)")
        
        try:
            # Process the PDF
            results = await ocr.process_pdf(pdf_path, document_type=doc_type)
            
            # Log summary
            successful = sum(1 for r in results if r.get("status") == "success")
            logger.info(f"Completed {pdf_path.name}: {successful}/{len(results)} pages successful")
            
            # Add to overall results
            all_results.extend(results)
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            all_results.append({
                "status": "error",
                "source": str(pdf_path),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    # Generate processing report
    report = generate_processing_report(all_results, "Kheel Center")
    
    # Save report
    report_path = Path("output/ocr/reports/kheel_processing_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Processing report saved to: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("KHEEL CENTER PROCESSING SUMMARY")
    print("="*60)
    print(f"Total files processed: {len(pdf_files)}")
    print(f"Total pages processed: {report['total_pages']}")
    print(f"Successful pages: {report['successful_pages']}")
    print(f"Failed pages: {report['failed_pages']}")
    print(f"Average confidence: {report['average_confidence']:.2%}")
    print(f"Total text extracted: {report['total_text_length']:,} characters")
    print(f"Report saved to: {report_path}")
    print("="*60)
    
    return report


async def process_nys_archives():
    """Process NYS Archives materials"""
    
    # Initialize OCR processor
    ocr = QwenVLOCR(config_path="ocr_config.yaml")
    logger.info("Initialized Qwen VL Plus OCR processor for NYS Archives")
    
    # Define NYS Archives base directory
    nys_base = Path("raw/scans/NYS Archives")
    
    if not nys_base.exists():
        logger.error(f"NYS Archives directory not found: {nys_base}")
        return
    
    # Find all PDFs in subdirectories
    pdf_files = list(nys_base.glob("*/*.pdf"))
    # Filter out macOS resource fork files
    pdf_files = [f for f in pdf_files if not f.name.startswith("._")]
    
    logger.info(f"Found {len(pdf_files)} PDF files in NYS Archives collection")
    
    # Process each PDF
    all_results = []
    
    for pdf_path in pdf_files:
        logger.info(f"Processing: {pdf_path.parent.name}/{pdf_path.name}")
        
        # Determine document type based on filename
        doc_type = determine_document_type(pdf_path)
        logger.info(f"Document type: {doc_type}")
        
        try:
            # Process the PDF
            results = await ocr.process_pdf(pdf_path, document_type=doc_type)
            
            # Log summary
            successful = sum(1 for r in results if r.get("status") == "success")
            logger.info(f"Completed {pdf_path.name}: {successful}/{len(results)} pages successful")
            
            # Add series information to results
            series = pdf_path.parent.name
            for result in results:
                result["series"] = series
            
            all_results.extend(results)
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            all_results.append({
                "status": "error",
                "source": str(pdf_path),
                "series": pdf_path.parent.name,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    # Generate processing report
    report = generate_processing_report(all_results, "NYS Archives")
    
    # Save report
    report_path = Path("output/ocr/reports/nys_archives_processing_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Processing report saved to: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("NYS ARCHIVES PROCESSING SUMMARY")
    print("="*60)
    print(f"Total files processed: {len(pdf_files)}")
    print(f"Total pages processed: {report['total_pages']}")
    print(f"Successful pages: {report['successful_pages']}")
    print(f"Failed pages: {report['failed_pages']}")
    print(f"Average confidence: {report['average_confidence']:.2%}")
    print(f"Total text extracted: {report['total_text_length']:,} characters")
    print(f"Report saved to: {report_path}")
    print("="*60)
    
    return report


def determine_document_type(pdf_path: Path) -> str:
    """Determine document type based on filename and path"""
    
    filename = pdf_path.name.lower()
    
    # Check specific patterns
    if "consolidation" in filename or "data" in filename:
        return "table_form"
    elif "notecard" in filename:
        return "mixed"
    elif "roll" in filename:
        return "handwritten"
    elif "records" in filename:
        return "mixed"
    else:
        return "historical_document"


def generate_processing_report(results: list, collection_name: str) -> dict:
    """Generate a comprehensive processing report"""
    
    # Calculate statistics
    total_pages = len(results)
    successful_pages = sum(1 for r in results if r.get("status") == "success")
    failed_pages = total_pages - successful_pages
    
    # Calculate confidence scores
    confidences = [r.get("confidence", 0) for r in results if r.get("status") == "success" and r.get("confidence")]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    # Calculate text lengths
    text_lengths = [r.get("text_length", 0) for r in results if r.get("status") == "success")]
    total_text = sum(text_lengths)
    
    # Group by source file
    files_processed = {}
    for result in results:
        source = result.get("source_pdf") or result.get("source", "unknown")
        if source not in files_processed:
            files_processed[source] = {
                "total_pages": 0,
                "successful_pages": 0,
                "failed_pages": 0,
                "confidences": [],
                "text_length": 0
            }
        
        files_processed[source]["total_pages"] += 1
        
        if result.get("status") == "success":
            files_processed[source]["successful_pages"] += 1
            files_processed[source]["text_length"] += result.get("text_length", 0)
            if result.get("confidence"):
                files_processed[source]["confidences"].append(result.get("confidence"))
        else:
            files_processed[source]["failed_pages"] += 1
    
    # Calculate per-file averages
    for source in files_processed:
        confidences = files_processed[source]["confidences"]
        files_processed[source]["average_confidence"] = (
            sum(confidences) / len(confidences) if confidences else 0
        )
        del files_processed[source]["confidences"]  # Remove raw data from report
    
    # Build report
    report = {
        "collection": collection_name,
        "processed_at": datetime.now().isoformat(),
        "total_files": len(files_processed),
        "total_pages": total_pages,
        "successful_pages": successful_pages,
        "failed_pages": failed_pages,
        "success_rate": successful_pages / total_pages if total_pages > 0 else 0,
        "average_confidence": avg_confidence,
        "total_text_length": total_text,
        "average_text_per_page": total_text / successful_pages if successful_pages > 0 else 0,
        "files": files_processed,
        "errors": [
            {
                "source": r.get("source"),
                "error": r.get("error"),
                "page": r.get("page_number")
            }
            for r in results if r.get("status") == "error"
        ]
    }
    
    return report


async def process_all():
    """Process all Kheel Center, NYS Archives, and Loose Image materials"""
    
    print("\n" + "="*60)
    print("COMMON SCHOOL ARCHIVE OCR PROCESSING")
    print("Using Qwen VL Plus via OpenRouter")
    print("="*60)
    
    # Process Kheel Center
    print("\nStarting Kheel Center processing...")
    kheel_report = await process_kheel_materials()
    
    # Process NYS Archives
    print("\nStarting NYS Archives processing...")
    nys_report = await process_nys_archives()

    # Process Loose Images
    print("\nStarting Loose Images processing...")
    images_report = await process_loose_images()
    
    # Generate combined summary
    print("\n" + "="*60)
    print("COMBINED PROCESSING SUMMARY")
    print("="*60)
    
    reports = [r for r in [kheel_report, nys_report, images_report] if r]
    
    if reports:
        total_pages = sum(r.get("total_pages", 0) for r in reports)
        successful_pages = sum(r.get("successful_pages", 0) for r in reports)
        total_text = sum(r.get("total_text_length", 0) for r in reports)
        
        # Note: For loose images, total_pages == total_files usually
        
        print(f"Total items/pages processed: {total_pages}")
        print(f"Total successful: {successful_pages}")
        if total_pages > 0:
            print(f"Overall success rate: {successful_pages/total_pages:.2%}")
        print(f"Total text extracted: {total_text:,} characters")
    
    print("="*60)
    print("Processing complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process Common School Archive scans with OCR")
    parser.add_argument(
        "--collection",
        choices=["kheel", "nys", "images", "all"],
        default="all",
        help="Which collection to process (default: all)"
    )
    
    args = parser.parse_args()
    
    if args.collection == "kheel":
        asyncio.run(process_kheel_materials())
    elif args.collection == "nys":
        asyncio.run(process_nys_archives())
    elif args.collection == "images":
        asyncio.run(process_loose_images())
    else:
        asyncio.run(process_all())