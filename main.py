"""
Data Import & Processing API

A FastAPI application for importing and processing CSV/JSON data files.
Handles bulk data imports, validation, and provides query endpoints with embeddings.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import csv
import io
import sqlite3
import hashlib
import time
import os
import numpy as np

app = FastAPI(title="Data Import API")

# Simple embedding model - loads synchronously on startup (slow!)
try:
    from sentence_transformers import SentenceTransformer
    print("Loading embedding model... (this takes time)")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print("✓ Embedding model loaded")
    EMBEDDINGS_ENABLED = True
except ImportError:
    print("⚠ sentence-transformers not installed. Embeddings disabled.")
    print("  Install with: pip install sentence-transformers")
    embedding_model = None
    EMBEDDINGS_ENABLED = False

# Database connection - not using connection pooling
DB_PATH = "data_imports.db"

# In-memory cache for processed records
processed_cache = {}
upload_status = {}


def get_db_connection():
    """Get database connection without pooling."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            total_records INTEGER DEFAULT 0,
            processed_records INTEGER DEFAULT 0,
            failed_records INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            embedding TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (import_id) REFERENCES imports (id)
        )
    """)
    
    conn.commit()
    conn.close()


# Initialize database on startup
init_database()


class ImportRequest(BaseModel):
    validate: bool = True
    batch_size: int = 100


class RecordQuery(BaseModel):
    import_id: Optional[int] = None
    status: Optional[str] = None
    limit: int = 100


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a CSV or JSON file for processing with embedding generation.
    
    Issues in this endpoint:
    - Reads entire file into memory
    - No file size limits
    - Processes synchronously (blocks the request)
    - Embedding generation runs synchronously (VERY SLOW)
    - No batching for embeddings
    - No proper error handling for malformed files
    - No transaction handling
    """
    
    # Read entire file into memory - problem with large files
    content = await file.read()
    
    # Calculate file hash
    file_hash = hashlib.md5(content).hexdigest()
    
    # Check if file already processed - but has race condition
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM imports WHERE file_hash = ?", (file_hash,))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return JSONResponse(
            status_code=200,
            content={"message": "File already processed", "import_id": existing[0]}
        )
    
    # Create import record
    cursor.execute(
        "INSERT INTO imports (filename, file_hash, status, created_at) VALUES (?, ?, ?, ?)",
        (file.filename, file_hash, "processing", datetime.now().isoformat())
    )
    import_id = cursor.lastrowid
    conn.commit()
    
    # Process file synchronously - blocks the entire API
    try:
        if file.filename.endswith('.csv'):
            records = process_csv(content)
        elif file.filename.endswith('.json'):
            records = process_json(content)
        else:
            cursor.execute("DELETE FROM imports WHERE id = ?", (import_id,))
            conn.commit()
            conn.close()
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        # Process each record synchronously - no batching
        total = len(records)
        processed = 0
        failed = 0
        
        for record in records:
            try:
                # Validate record
                validated = validate_record(record)
                
                # Generate embedding synchronously - BLOCKS THE ENTIRE API!
                # This is the main performance bottleneck
                embedding = generate_embedding(validated)
                
                # Store in database - individual inserts, no batching
                cursor.execute(
                    "INSERT INTO records (import_id, data, embedding, status, created_at) VALUES (?, ?, ?, ?, ?)",
                    (import_id, json.dumps(validated), embedding, "valid", datetime.now().isoformat())
                )
                conn.commit()  # Committing after each insert - very slow
                
                processed += 1
                
                # Update cache
                cache_key = f"{import_id}_{processed}"
                processed_cache[cache_key] = validated  # Memory leak - never cleaned up
                
            except Exception as e:
                # Store failed record but don't stop processing
                cursor.execute(
                    "INSERT INTO records (import_id, data, embedding, status, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (import_id, json.dumps(record), None, "failed", str(e), datetime.now().isoformat())
                )
                conn.commit()
                failed += 1
        
        # Update import status
        cursor.execute(
            "UPDATE imports SET status = ?, total_records = ?, processed_records = ?, failed_records = ?, completed_at = ? WHERE id = ?",
            ("completed", total, processed, failed, datetime.now().isoformat(), import_id)
        )
        conn.commit()
        conn.close()
        
        return {
            "import_id": import_id,
            "status": "completed",
            "total_records": total,
            "processed_records": processed,
            "failed_records": failed
        }
        
    except Exception as e:
        # Poor error handling - loses context
        cursor.execute(
            "UPDATE imports SET status = ? WHERE id = ?",
            ("failed", import_id)
        )
        conn.commit()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


def process_csv(content: bytes) -> List[Dict]:
    """
    Process CSV content.
    
    Issues:
    - No encoding handling
    - Assumes first row is header
    - No error handling for malformed CSV
    """
    text = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def process_json(content: bytes) -> List[Dict]:
    """
    Process JSON content.
    
    Issues:
    - No error handling
    - Assumes array format
    - No size limits
    """
    data = json.loads(content)
    if isinstance(data, list):
        return data
    else:
        return [data]


def generate_embedding(record: Dict) -> Optional[str]:
    """
    Generate embedding for a record.
    
    Issues:
    - Runs synchronously (blocks processing)
    - Generates embeddings one at a time (no batching)
    - CPU/GPU intensive operation in request handler
    - No caching or optimization
    """
    if not EMBEDDINGS_ENABLED:
        return None
    
    try:
        # Create text representation of record
        text_parts = []
        for key, value in record.items():
            if value and str(value).strip():
                text_parts.append(f"{key}: {value}")
        
        text = " | ".join(text_parts)
        
        # Generate embedding - BLOCKS EVERYTHING!
        # This is CPU/GPU intensive and takes 50-200ms per record
        embedding_vector = embedding_model.encode(text)
        
        # Convert to JSON string for storage
        return json.dumps(embedding_vector.tolist())
    except Exception as e:
        # Silent failure - just skip embedding
        return None


def validate_record(record: Dict) -> Dict:
    """
    Validate a single record.
    
    Issues:
    - Minimal validation
    - Silent data coercion
    - No schema validation
    """
    validated = {}
    
    # Required fields check - but silently creates empty values
    validated['name'] = record.get('name', '')
    validated['email'] = record.get('email', '')
    validated['age'] = record.get('age', 0)
    
    # Try to convert age to int - silent failure
    try:
        validated['age'] = int(validated['age'])
    except:
        validated['age'] = 0
    
    # Basic email validation - very weak
    if '@' not in validated['email']:
        raise ValueError("Invalid email format")
    
    # Copy all other fields without validation
    for key, value in record.items():
        if key not in validated:
            validated[key] = value
    
    return validated


@app.get("/api/imports")
def get_imports():
    """
    Get all imports.
    
    Issues:
    - Returns all records without pagination
    - N+1 query pattern when getting details
    - No connection pooling
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM imports ORDER BY created_at DESC")
    imports = cursor.fetchall()
    
    # Convert to list of dicts - inefficient
    result = []
    for imp in imports:
        import_dict = dict(imp)
        
        # N+1 query - gets record count for each import separately
        cursor.execute(
            "SELECT COUNT(*) FROM records WHERE import_id = ?",
            (imp['id'],)
        )
        import_dict['record_count'] = cursor.fetchone()[0]
        
        result.append(import_dict)
    
    conn.close()
    return {"imports": result}


@app.get("/api/imports/{import_id}")
def get_import_details(import_id: int):
    """
    Get import details with all records.
    
    Issues:
    - Loads all records into memory
    - No pagination
    - Inefficient JSON parsing
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM imports WHERE id = ?", (import_id,))
    import_data = cursor.fetchone()
    
    if not import_data:
        conn.close()
        raise HTTPException(status_code=404, detail="Import not found")
    
    # Get all records - no limit
    cursor.execute("SELECT * FROM records WHERE import_id = ?", (import_id,))
    records = cursor.fetchall()
    
    # Parse JSON data for each record - inefficient
    parsed_records = []
    for record in records:
        record_dict = dict(record)
        try:
            record_dict['data'] = json.loads(record_dict['data'])
        except:
            pass
        parsed_records.append(record_dict)
    
    conn.close()
    
    return {
        "import": dict(import_data),
        "records": parsed_records
    }


@app.post("/api/records/search")
def search_records(query: RecordQuery):
    """
    Search records with filters.
    
    Issues:
    - No indexing on search fields
    - Loads all matching records
    - Inefficient JSON parsing
    - SQL injection vulnerability in dynamic queries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build query - potential SQL injection
    sql = "SELECT * FROM records WHERE 1=1"
    params = []
    
    if query.import_id:
        sql += " AND import_id = ?"
        params.append(query.import_id)
    
    if query.status:
        sql += " AND status = ?"
        params.append(query.status)
    
    sql += f" LIMIT {query.limit}"  # String formatting - SQL injection risk
    
    cursor.execute(sql, params)
    records = cursor.fetchall()
    
    # Parse all records
    result = []
    for record in records:
        record_dict = dict(record)
        try:
            record_dict['data'] = json.loads(record_dict['data'])
        except:
            pass
        result.append(record_dict)
    
    conn.close()
    return {"records": result}


@app.delete("/api/imports/{import_id}")
def delete_import(import_id: int):
    """
    Delete an import and its records.
    
    Issues:
    - No transaction handling
    - Doesn't clean up orphaned records if import delete fails
    - No cascade delete
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if import exists
    cursor.execute("SELECT id FROM imports WHERE id = ?", (import_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Import not found")
    
    # Delete records first - but not in transaction
    cursor.execute("DELETE FROM records WHERE import_id = ?", (import_id,))
    conn.commit()
    
    # Simulate potential failure point
    time.sleep(0.1)
    
    # Delete import
    cursor.execute("DELETE FROM imports WHERE id = ?", (import_id,))
    conn.commit()
    
    conn.close()
    
    # Don't clean up cache - memory leak
    
    return {"message": "Import deleted"}


@app.get("/api/stats")
def get_statistics():
    """
    Get system statistics.
    
    Issues:
    - Multiple separate queries - not efficient
    - No caching
    - Recalculates everything on each call
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Multiple queries instead of one
    cursor.execute("SELECT COUNT(*) FROM imports")
    total_imports = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM imports WHERE status = 'completed'")
    completed_imports = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM imports WHERE status = 'failed'")
    failed_imports = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM records")
    total_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM records WHERE status = 'valid'")
    valid_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM records WHERE status = 'failed'")
    failed_records = cursor.fetchone()[0]
    
    # Calculate cache size - exposes internal implementation
    cache_size = len(processed_cache)
    
    conn.close()
    
    return {
        "total_imports": total_imports,
        "completed_imports": completed_imports,
        "failed_imports": failed_imports,
        "total_records": total_records,
        "valid_records": valid_records,
        "failed_records": failed_records,
        "cache_entries": cache_size,
        "database_size_mb": os.path.getsize(DB_PATH) / (1024 * 1024) if os.path.exists(DB_PATH) else 0
    }


@app.get("/health")
def health_check():
    """Basic health check."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    print("Starting Data Import API...")
    print("API Documentation: http://localhost:8000/docs")
    print(f"\nEmbeddings: {'✓ Enabled' if EMBEDDINGS_ENABLED else '✗ Disabled'}")
    print("\nKnown Issues:")
    print("- Synchronous file processing blocks the API")
    print("- Embedding generation runs synchronously (VERY SLOW)")
    print("- No batching for embeddings")
    print("- No proper async handling")
    print("- Memory leaks in cache")
    print("- N+1 query patterns")
    print("- No transaction handling")
    print("- SQL injection vulnerabilities")
    print("- No connection pooling")
    uvicorn.run(app, host="0.0.0.0", port=8000)
