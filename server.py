#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Web server for exam question search."""

import json
import sqlite3
import struct
import os
import sys

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exam.db")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)

# Load model lazily
_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _model

def get_db():
    """Get a database connection with sqlite-vec loaded."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn

def serialize_f32(vector):
    return struct.pack(f"{len(vector)}f", *vector)

@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(STATIC_DIR, path)

@app.route('/api/search', methods=['GET'])
def search():
    query = request.args.get('q', '').strip()
    mode = request.args.get('mode', 'semantic')  # semantic | keyword | both
    limit = min(int(request.args.get('limit', 20)), 100)
    
    if not query:
        return jsonify({"results": [], "total": 0, "query": query, "mode": mode})
    
    conn = get_db()
    results = []
    
    if mode == 'keyword':
        results = keyword_search(conn, query, limit)
    elif mode == 'semantic':
        results = semantic_search(conn, query, limit)
    else:  # both
        sem_results = semantic_search(conn, query, limit)
        kw_results = keyword_search(conn, query, limit)
        # Merge: deduplicate by id, prefer semantic order
        seen = set()
        for r in sem_results + kw_results:
            if r['id'] not in seen:
                seen.add(r['id'])
                results.append(r)
            if len(results) >= limit:
                break
    
    conn.close()
    return jsonify({
        "results": results,
        "total": len(results),
        "query": query,
        "mode": mode
    })

def semantic_search(conn, query, limit):
    """Vector similarity search."""
    model = get_model()
    query_emb = model.encode([query])[0]
    query_bytes = serialize_f32(query_emb)
    
    rows = conn.execute("""
        SELECT 
            v.question_id,
            v.distance,
            q.number, q.difficulty, q.type, q.content, 
            q.options_json, q.answer, q.section, q.explanation
        FROM questions_vec v
        JOIN questions q ON q.id = v.question_id
        WHERE v.embedding MATCH ?
            AND k = ?
        ORDER BY v.distance
    """, (query_bytes, limit)).fetchall()
    
    results = []
    for row in rows:
        results.append({
            "id": row["question_id"],
            "number": row["number"],
            "difficulty": row["difficulty"],
            "type": row["type"],
            "content": row["content"],
            "options": json.loads(row["options_json"]),
            "answer": row["answer"],
            "section": row["section"],
            "explanation": row["explanation"],
            "score": round(max(0, 1 - row["distance"] / 2), 4),
            "match_type": "semantic"
        })
    return results

def keyword_search(conn, query, limit):
    """FTS5 keyword search."""
    # Escape FTS5 special characters
    safe_query = query.replace('"', '""')
    
    try:
        rows = conn.execute("""
            SELECT 
                q.id, q.number, q.difficulty, q.type, q.content,
                q.options_json, q.answer, q.section, q.explanation,
                bm25(questions_fts) as rank
            FROM questions_fts fts
            JOIN questions q ON q.id = fts.rowid
            WHERE questions_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (safe_query, limit)).fetchall()
    except Exception:
        # Fallback to LIKE search if FTS query is invalid
        like_q = f"%{query}%"
        rows = conn.execute("""
            SELECT 
                id, number, difficulty, type, content,
                options_json, answer, section, explanation,
                0 as rank
            FROM questions
            WHERE content LIKE ? OR answer LIKE ? OR explanation LIKE ?
            LIMIT ?
        """, (like_q, like_q, like_q, limit)).fetchall()
    
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "number": row["number"],
            "difficulty": row["difficulty"],
            "type": row["type"],
            "content": row["content"],
            "options": json.loads(row["options_json"]),
            "answer": row["answer"],
            "section": row["section"],
            "explanation": row["explanation"],
            "score": round(-row["rank"], 4) if row["rank"] else 0,
            "match_type": "keyword"
        })
    return results

@app.route('/api/stats', methods=['GET'])
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    by_difficulty = {}
    for row in conn.execute("SELECT difficulty, COUNT(*) as cnt FROM questions GROUP BY difficulty ORDER BY difficulty"):
        stars = '★' * row['difficulty'] if row['difficulty'] > 0 else '未标注'
        by_difficulty[stars] = row['cnt']
    by_type = {}
    for row in conn.execute("SELECT type, COUNT(*) as cnt FROM questions GROUP BY type"):
        by_type[row['type']] = row['cnt']
    conn.close()
    return jsonify({
        "total": total,
        "by_difficulty": by_difficulty,
        "by_type": by_type
    })

@app.route('/api/question/<int:qid>', methods=['GET'])
def get_question(qid):
    conn = get_db()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": row["id"],
        "number": row["number"],
        "difficulty": row["difficulty"],
        "type": row["type"],
        "content": row["content"],
        "options": json.loads(row["options_json"]),
        "answer": row["answer"],
        "section": row["section"],
        "explanation": row["explanation"]
    })

if __name__ == "__main__":
    print(f"Database: {DB_PATH}")
    print(f"Static files: {STATIC_DIR}")
    print("Pre-loading embedding model...")
    get_model()
    print("Model loaded. Starting server...")
    print("=" * 50)
    print("  Exam Search: http://localhost:8765")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8765, debug=False)
