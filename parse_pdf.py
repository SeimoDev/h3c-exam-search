#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parse exam PDF into structured JSON."""

import fitz
import re
import json
import sys

PDF_PATH = r"D:\openclaw\exam_bank.pdf"
OUTPUT_PATH = r"D:\openclaw\exam-search\questions.json"

def extract_all_text(pdf_path):
    """Extract text from all pages."""
    doc = fitz.open(pdf_path)
    full_text = ""
    for i in range(len(doc)):
        page_text = doc[i].get_text()
        # Remove footer lines
        page_text = re.sub(r'新思齐\s*新思齐', '', page_text)
        page_text = re.sub(r'2026.*?全国大学生数字技术大赛备考资料（网络赛道）', '', page_text)
        page_text = re.sub(r'\d+／\d+', '', page_text)
        full_text += page_text + "\n"
    doc.close()
    return full_text

def parse_questions(text):
    """Parse questions from extracted text."""
    # Split by question headers
    pattern = r'问题\s+(\d+)\s*\n'
    parts = re.split(pattern, text)
    
    questions = []
    # parts[0] is before first question, then alternating: number, content
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
        
        # Extract question content (before options)
        content_match = re.search(r'^(.*?)(?=\nA[\.\s])', q_body, re.DOTALL)
        if content_match:
            content = content_match.group(1).strip()
        else:
            # Fallback: everything before answer
            content_match2 = re.search(r'^(.*?)(?=正确答案:)', q_body, re.DOTALL)
            content = content_match2.group(1).strip() if content_match2 else q_body[:200]
        
        # Remove section/chapter info from content
        content = re.sub(r'章节:.*?(?:\n|$)', '', content).strip()
        
        # Extract options
        options = {}
        opt_pattern = r'\n([A-F])[\.\s]\s*(.*?)(?=\n[A-F][\.\s]|\n正确答案:|\nExplanation|$)'
        for opt_match in re.finditer(opt_pattern, q_body, re.DOTALL):
            letter = opt_match.group(1)
            opt_text = opt_match.group(2).strip()
            # Clean up multi-line options
            opt_text = re.sub(r'\n\s*', ' ', opt_text)
            options[letter] = opt_text
        
        # Determine question type
        if len(answer) > 1:
            q_type = "多选题"
        else:
            q_type = "单选题"
        
        # Build full text for embedding
        full_text_parts = [content]
        for letter in sorted(options.keys()):
            full_text_parts.append(f"{letter}. {options[letter]}")
        full_text_embed = "\n".join(full_text_parts)
        
        questions.append({
            "id": q_num,
            "number": q_num,
            "difficulty": difficulty,
            "type": q_type,
            "content": content,
            "options": options,
            "answer": answer,
            "section": section,
            "explanation": explanation,
            "full_text": full_text_embed
        })
    
    return questions

def main():
    print(f"Extracting text from {PDF_PATH}...")
    text = extract_all_text(PDF_PATH)
    print(f"Extracted {len(text)} characters")
    
    print("Parsing questions...")
    questions = parse_questions(text)
    print(f"Parsed {len(questions)} questions")
    
    # Stats
    difficulties = {}
    types = {}
    for q in questions:
        d = q["difficulty"]
        difficulties[d] = difficulties.get(d, 0) + 1
        t = q["type"]
        types[t] = types.get(t, 0) + 1
    
    print(f"\nDifficulty distribution: {dict(sorted(difficulties.items()))}")
    print(f"Question types: {types}")
    
    # Show sample
    if questions:
        q = questions[0]
        print(f"\nSample question #{q['number']}:")
        print(f"  Difficulty: {'★' * q['difficulty']}")
        print(f"  Content: {q['content'][:100]}...")
        print(f"  Options: {list(q['options'].keys())}")
        print(f"  Answer: {q['answer']}")
    
    # Save
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
