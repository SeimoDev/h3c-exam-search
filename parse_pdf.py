#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parse exam PDF into structured JSON - handles both text and image pages."""

import fitz
import re
import json
import sys
import os
import time

PDF_PATH = r"D:\openclaw\exam_bank.pdf"
OUTPUT_PATH = r"D:\openclaw\exam-search\questions.json"
OCR_CACHE_PATH = r"D:\openclaw\exam-search\ocr_cache.json"

def extract_text_pages(doc):
    """Extract text from all pages, using PyMuPDF text extraction."""
    pages = {}
    for i in range(len(doc)):
        text = doc[i].get_text()
        # Remove footers
        text = re.sub(r'新思齐\s*新思齐', '', text)
        text = re.sub(r'2026.*?全国大学生数字技术大赛备考资料（网络赛道）', '', text)
        text = re.sub(r'2026"新华三杯"全国大学生数字技术大赛备考资料（网络赛道）', '', text)
        text = re.sub(r'\d+／\d+', '', text)
        text = re.sub(r'\d+/\d+', '', text)
        clean = text.strip()
        if len(clean) > 30:
            pages[i] = clean
    return pages

def ocr_image_pages(doc, text_pages):
    """OCR pages that don't have enough text."""
    # Load cache if exists
    ocr_cache = {}
    if os.path.exists(OCR_CACHE_PATH):
        with open(OCR_CACHE_PATH, 'r', encoding='utf-8') as f:
            ocr_cache = json.load(f)
        print(f"Loaded OCR cache: {len(ocr_cache)} pages")

    pages_to_ocr = []
    for i in range(len(doc)):
        if i not in text_pages:
            page = doc[i]
            images = page.get_images()
            if images:
                pages_to_ocr.append(i)

    print(f"Pages needing OCR: {len(pages_to_ocr)}")
    
    if not pages_to_ocr:
        return {}

    # Check which ones need OCR (not in cache)
    uncached = [i for i in pages_to_ocr if str(i) not in ocr_cache]
    if uncached:
        print(f"Running OCR on {len(uncached)} new pages...")
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
        from PIL import Image
        import io

        ocr = RapidOCR()
        
        for idx, page_num in enumerate(uncached):
            page = doc[page_num]
            images = page.get_images()
            
            # Find the largest image (main content)
            best_img = None
            best_size = 0
            for img in images:
                xref = img[0]
                base_image = doc.extract_image(xref)
                size = base_image['width'] * base_image['height']
                if size > best_size:
                    best_size = size
                    best_img = base_image
            
            if best_img and best_size > 100000:  # Skip tiny images
                img_data = best_img['image']
                img = Image.open(io.BytesIO(img_data))
                img_np = np.array(img)
                
                result, _ = ocr(img_np)
                if result:
                    text_parts = [text for _, text, conf in result if conf > 0.5]
                    page_text = "\n".join(text_parts)
                    # Clean footer from OCR too
                    page_text = re.sub(r'\d+/\d+\s*$', '', page_text).strip()
                    ocr_cache[str(page_num)] = page_text
                else:
                    ocr_cache[str(page_num)] = ""
            else:
                ocr_cache[str(page_num)] = ""
            
            if (idx + 1) % 10 == 0:
                print(f"  OCR progress: {idx + 1}/{len(uncached)} pages", flush=True)
                # Save cache periodically
                with open(OCR_CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(ocr_cache, f, ensure_ascii=False)
        
        # Final cache save
        with open(OCR_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(ocr_cache, f, ensure_ascii=False)
        print(f"OCR complete. Cache saved: {len(ocr_cache)} pages")

    # Return OCR results for requested pages
    result = {}
    for i in pages_to_ocr:
        text = ocr_cache.get(str(i), "")
        if len(text) > 30:
            result[i] = text
    return result

def parse_format1_questions(text):
    """Parse 问题 N format (pages 1-380ish)."""
    pattern = r'问题\s+(\d+)\s*\n'
    parts = re.split(pattern, text)
    
    questions = []
    for i in range(1, len(parts) - 1, 2):
        q_num = int(parts[i])
        q_body = parts[i + 1].strip()
        
        # Extract difficulty (stars)
        star_match = re.match(r'^([★]+)\s*\n?', q_body)
        difficulty = len(star_match.group(1)) if star_match else 0
        if star_match:
            q_body = q_body[star_match.end():]
        
        # Extract answer
        answer_match = re.search(r'正确答案:\s*([A-F]+)', q_body)
        answer = answer_match.group(1) if answer_match else ""
        
        # Extract section
        section_match = re.search(r'章节:\s*(.+?)(?:\n|$)', q_body)
        section = section_match.group(1).strip() if section_match else ""
        if section == "(无)":
            section = ""
        
        # Extract explanation
        explanation = ""
        exp_match = re.search(r'(?:说明/参考:|Explanation\s*\n说明/参考:)\s*\n?(.*?)(?=问题\s+\d+|$)', q_body, re.DOTALL)
        if exp_match:
            explanation = exp_match.group(1).strip()
        
        # Extract content (before options)
        content_match = re.search(r'^(.*?)(?=\nA[\.\s])', q_body, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            content_match2 = re.search(r'^(.*?)(?=正确答案:)', q_body, re.DOTALL)
            content = content_match2.group(1).strip() if content_match2 else q_body[:200]
        content = re.sub(r'章节:.*?(?:\n|$)', '', content).strip()
        
        # Extract options
        options = {}
        opt_pattern = r'\n([A-F])[\.\s]\s*(.*?)(?=\n[A-F][\.\s]|\n正确答案:|\nExplanation|$)'
        for opt_match in re.finditer(opt_pattern, q_body, re.DOTALL):
            letter = opt_match.group(1)
            opt_text = opt_match.group(2).strip()
            opt_text = re.sub(r'\n\s*', ' ', opt_text)
            options[letter] = opt_text
        
        q_type = "多选题" if len(answer) > 1 else "单选题"
        
        full_text_parts = [content]
        for letter in sorted(options.keys()):
            full_text_parts.append(f"{letter}. {options[letter]}")
        
        questions.append({
            "number": q_num,
            "difficulty": difficulty,
            "type": q_type,
            "content": content,
            "options": options,
            "answer": answer,
            "section": section,
            "explanation": explanation,
            "full_text": "\n".join(full_text_parts)
        })
    
    return questions

def parse_format2_questions(text):
    """Parse N. format or 1.xxx format (OCR pages and later text pages)."""
    # Split by numbered questions: "N." or "N、" at start of line
    # Match patterns like "278.", "1.", "96." etc
    pattern = r'(?:^|\n)(\d+)[\.、．]\s*'
    parts = re.split(pattern, text)
    
    questions = []
    for i in range(1, len(parts) - 1, 2):
        q_num_str = parts[i]
        q_body = parts[i + 1].strip()
        
        try:
            q_num = int(q_num_str)
        except ValueError:
            continue
        
        if len(q_body) < 10:
            continue
        
        # Extract answer - various formats
        answer = ""
        # Format: 答案:ABC or 答案：ABC
        ans_match = re.search(r'答案[:：]\s*([A-F]+)', q_body)
        if ans_match:
            answer = ans_match.group(1)
        else:
            # Format: 正确答案: ABC
            ans_match2 = re.search(r'正确答案[:：]\s*([A-F]+)', q_body)
            if ans_match2:
                answer = ans_match2.group(1)
        
        # Extract explanation
        explanation = ""
        exp_match = re.search(r'(?:解析|说明/参考|Explanation)[:：]?\s*\n?(.*?)(?=\n\d+[\.、．]|\Z)', q_body, re.DOTALL)
        if exp_match:
            explanation = exp_match.group(1).strip()
            # Remove answer line from explanation if present
            explanation = re.sub(r'答案[:：]\s*[A-F]+\s*', '', explanation).strip()
        
        # Extract content (before options)
        content = ""
        content_match = re.search(r'^(.*?)(?=\n[A-F][\.\s、．])', q_body, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            # Try to get content before answer
            content_match2 = re.search(r'^(.*?)(?=答案[:：]|正确答案[:：])', q_body, re.DOTALL)
            if content_match2:
                content = content_match2.group(1).strip()
            else:
                content = q_body[:200]
        
        # Clean content
        content = re.sub(r'[\(（]选择一项或多项[\)）]', '（多选题）', content)
        
        # Extract options
        options = {}
        opt_pattern = r'(?:^|\n)([A-F])[\.、．\s]\s*(.*?)(?=(?:\n[A-F][\.、．\s])|\n答案[:：]|\n解析[:：]|\n正确答案[:：]|\Z)'
        for opt_match in re.finditer(opt_pattern, q_body, re.DOTALL):
            letter = opt_match.group(1)
            opt_text = opt_match.group(2).strip()
            opt_text = re.sub(r'\n\s*', ' ', opt_text)
            if opt_text:
                options[letter] = opt_text
        
        q_type = "多选题" if len(answer) > 1 else "单选题"
        
        full_text_parts = [content]
        for letter in sorted(options.keys()):
            full_text_parts.append(f"{letter}. {options[letter]}")
        
        questions.append({
            "number": q_num,
            "difficulty": 0,
            "type": q_type,
            "content": content,
            "options": options,
            "answer": answer,
            "section": "",
            "explanation": explanation,
            "full_text": "\n".join(full_text_parts)
        })
    
    return questions

def parse_section_headers(text):
    """Try to detect section headers like '九、端口号及命令（40题）'."""
    sections = {}
    pattern = r'[一二三四五六七八九十]+[、．.]\s*(.+?)[\(（]\d+题[\)）]'
    for m in re.finditer(pattern, text):
        sections[m.start()] = m.group(1).strip()
    return sections

def main():
    start_time = time.time()
    
    print(f"Opening PDF: {PDF_PATH}")
    doc = fitz.open(PDF_PATH)
    print(f"Total pages: {len(doc)}")
    
    # Step 1: Extract text from all pages
    print("\n--- Step 1: Text extraction ---")
    text_pages = extract_text_pages(doc)
    print(f"Pages with text: {len(text_pages)}")
    
    # Step 2: OCR image-only pages
    print("\n--- Step 2: OCR image pages ---")
    ocr_pages = ocr_image_pages(doc, text_pages)
    print(f"Pages with OCR text: {len(ocr_pages)}")
    
    # Merge all pages
    all_pages = {}
    all_pages.update(text_pages)
    all_pages.update(ocr_pages)
    print(f"\nTotal pages with content: {len(all_pages)}")
    
    # Combine into single text, ordered by page
    full_text = ""
    for i in sorted(all_pages.keys()):
        full_text += all_pages[i] + "\n\n"
    
    # Step 3: Parse questions using both formats
    print("\n--- Step 3: Parsing questions ---")
    
    # Format 1: "问题 N" style
    q1 = parse_format1_questions(full_text)
    print(f"Format 1 (问题 N): {len(q1)} questions")
    
    # Format 2: "N." style - parse from the remaining text
    # Remove Format 1 questions from text to avoid double-parsing
    remaining = re.sub(r'问题\s+\d+\s*\n.*?(?=问题\s+\d+\s*\n|$)', '', full_text, flags=re.DOTALL)
    q2 = parse_format2_questions(remaining)
    print(f"Format 2 (N.): {len(q2)} questions")
    
    # Also try parsing the full text with format 2 for OCR sections
    # (OCR text won't have "问题 N" format)
    ocr_text = "\n\n".join([ocr_pages[i] for i in sorted(ocr_pages.keys())])
    q3 = parse_format2_questions(ocr_text)
    print(f"Format 2 from OCR: {len(q3)} questions")
    
    # Merge and deduplicate
    all_questions = []
    seen_contents = set()
    
    def add_questions(qs, source):
        added = 0
        for q in qs:
            # Use first 80 chars of content as dedup key
            key = q['content'][:80].strip()
            if key and key not in seen_contents:
                seen_contents.add(key)
                all_questions.append(q)
                added += 1
        print(f"  Added from {source}: {added} (dedup)")
    
    add_questions(q1, "format1")
    add_questions(q2, "format2-text")
    add_questions(q3, "format2-ocr")
    
    # Re-number
    for i, q in enumerate(all_questions):
        q['id'] = i + 1
    
    print(f"\nTotal unique questions: {len(all_questions)}")
    
    # Stats
    difficulties = {}
    types = {}
    with_answer = 0
    with_options = 0
    for q in all_questions:
        d = q['difficulty']
        difficulties[d] = difficulties.get(d, 0) + 1
        t = q['type']
        types[t] = types.get(t, 0) + 1
        if q['answer']:
            with_answer += 1
        if q['options']:
            with_options += 1
    
    print(f"Difficulty distribution: {dict(sorted(difficulties.items()))}")
    print(f"Question types: {types}")
    print(f"With answer: {with_answer}/{len(all_questions)}")
    print(f"With options: {with_options}/{len(all_questions)}")
    
    # Save
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start_time
    print(f"\nSaved to {OUTPUT_PATH}")
    print(f"Total time: {elapsed:.1f}s")

if __name__ == "__main__":
    main()
