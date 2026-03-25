#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build SQLite database with vector embeddings for exam questions."""

import json
import sqlite3
import struct
import sys
import os

# Paths
QUESTIONS_PATH = r"D:\openclaw\exam-search\questions.json"
DB_PATH = r"D:\openclaw\exam-search\exam.db"

def serialize_f32(vector):
    """Serialize a list of floats into bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

def main():
    print("Loading questions...")
    with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    print(f"Loaded {len(questions)} questions")

    print("Loading sentence-transformers model (first time may download ~500MB)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    print("Model loaded")

    # Prepare texts for embedding
    texts = []
    for q in questions:
        # Combine question content + options for richer embedding
        text = q['content']
        for letter in sorted(q['options'].keys()):
            text += f"\n{letter}. {q['options'][letter]}"
        if q['explanation']:
            text += f"\n{q['explanation']}"
        texts.append(text)

    print(f"Generating embeddings for {len(texts)} questions...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    dim = embeddings.shape[1]
    print(f"Embeddings generated: {embeddings.shape}")

    # Create database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("Creating database...")
    conn = sqlite3.connect(DB_PATH)
    
    # Enable sqlite-vec
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Create main questions table
    conn.execute("""
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY,
            number INTEGER,
            difficulty INTEGER,
            type TEXT,
            content TEXT,
            options_json TEXT,
            answer TEXT,
            section TEXT,
            explanation TEXT,
            full_text TEXT
        )
    """)

    # Create FTS5 table for keyword search
    conn.execute("""
        CREATE VIRTUAL TABLE questions_fts USING fts5(
            content, options_text, explanation, answer,
            content_rowid='rowid'
        )
    """)

    # Create vector table
    conn.execute(f"""
        CREATE VIRTUAL TABLE questions_vec USING vec0(
            question_id INTEGER PRIMARY KEY,
            embedding float[{dim}]
        )
    """)

    print("Inserting data...")
    for i, q in enumerate(questions):
        # Insert into main table
        options_text = " ".join([f"{k}. {v}" for k, v in sorted(q['options'].items())])
        conn.execute("""
            INSERT INTO questions (id, number, difficulty, type, content, options_json, answer, section, explanation, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            i + 1,
            q['number'],
            q['difficulty'],
            q['type'],
            q['content'],
            json.dumps(q['options'], ensure_ascii=False),
            q['answer'],
            q['section'],
            q['explanation'],
            q['full_text']
        ))

        # Insert into FTS
        conn.execute("""
            INSERT INTO questions_fts (rowid, content, options_text, explanation, answer)
            VALUES (?, ?, ?, ?, ?)
        """, (i + 1, q['content'], options_text, q['explanation'], q['answer']))

        # Insert embedding
        conn.execute("""
            INSERT INTO questions_vec (question_id, embedding)
            VALUES (?, ?)
        """, (i + 1, serialize_f32(embeddings[i])))

    conn.commit()

    # Verify
    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    vec_count = conn.execute("SELECT COUNT(*) FROM questions_vec").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM questions_fts").fetchone()[0]
    print(f"\nDatabase created: {DB_PATH}")
    print(f"  Questions: {count}")
    print(f"  Vector entries: {vec_count}")
    print(f"  FTS entries: {fts_count}")
    print(f"  Embedding dimension: {dim}")
    print(f"  DB size: {os.path.getsize(DB_PATH) / 1024 / 1024:.1f} MB")

    conn.close()
    print("Done!")

if __name__ == "__main__":
    main()
