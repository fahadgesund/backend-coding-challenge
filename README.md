# Data Import & Processing API - Live Coding Challenge

A FastAPI-based data import system for processing CSV and JSON files. This project is designed for live coding interviews to evaluate backend development, debugging, and optimization skills.

## Overview

This API allows users to upload CSV/JSON files containing user data, processes the records with validation, and stores them in a SQLite database. It provides endpoints for querying imports, searching records, and viewing statistics.

## What This System Does

1. **File Upload**: Accepts CSV or JSON files via HTTP upload
2. **Data Processing**: Parses and validates records from uploaded files
3. **Storage**: Persists imports and records in SQLite database
4. **Querying**: Provides endpoints to search and retrieve processed data
5. **Statistics**: Shows aggregate statistics about imports and records

## Quick Start

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

```bash
# Clone the repository
cd backend-coding-challenge

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

The API will start on `http://localhost:8000`

**API Documentation**: http://localhost:8000/docs

### Testing the API

```bash
# Upload a CSV file
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@sample_data.csv"

# View all imports
curl http://localhost:8000/api/imports

# Get specific import details
curl http://localhost:8000/api/imports/1

# Search records
curl -X POST "http://localhost:8000/api/records/search" \
  -H "Content-Type: application/json" \
  -d '{"status": "valid", "limit": 10}'

# View statistics
curl http://localhost:8000/api/stats
```

## Features

### Working Features ✅

- **CSV File Upload**: Upload CSV files with user data (name, email, age)
- **JSON File Upload**: Upload JSON arrays or single objects
- **Data Validation**: Basic email and age validation
- **Duplicate Detection**: Checks file hash to prevent duplicate imports
- **Status Tracking**: Tracks processing status of each import
- **Record Search**: Filter records by import_id and status
- **Statistics Dashboard**: View counts and database metrics
- **SQLite Persistence**: All data stored in local database

### API Endpoints

- `POST /api/upload` - Upload CSV/JSON file
- `GET /api/imports` - List all imports
- `GET /api/imports/{id}` - Get import details with all records
- `POST /api/records/search` - Search records with filters
- `DELETE /api/imports/{id}` - Delete an import
- `GET /api/stats` - Get system statistics
- `GET /health` - Health check endpoint

## Sample Data

Two sample files are provided:

**sample_data.csv:**
```csv
name,email,age,department
John Doe,john@example.com,30,Engineering
Jane Smith,jane@example.com,25,Marketing
Bob Wilson,bob@example.com,35,Sales
```

**sample_data.json:**
```json
[
  {"name": "Alice Johnson", "email": "alice@example.com", "age": 28, "department": "HR"},
  {"name": "Charlie Brown", "email": "charlie@example.com", "age": 32, "department": "Finance"}
]
```

## What is Intentionally Suboptimal

This codebase contains several **intentional** design and implementation issues for evaluation purposes:

### Performance Issues

1. **Synchronous File Processing**
   - Files are processed synchronously in the upload endpoint
   - Large files block the entire API during processing
   - No background task processing
   - **Impact**: API becomes unresponsive during uploads

2. **No Batching**
   - Records inserted one-by-one with individual commits
   - Each insert is a separate database transaction
   - **Impact**: Very slow for large files (1000+ records)

3. **N+1 Query Problem**
   - `/api/imports` endpoint fetches record counts individually
   - One query per import instead of a single JOIN
   - **Impact**: Slow when many imports exist

4. **No Connection Pooling**
   - Creates new database connection for each request
   - Connections not reused
   - **Impact**: Resource waste and slower queries

5. **Memory Leaks**
   - `processed_cache` dictionary grows indefinitely
   - Never cleaned up even after import deletion
   - **Impact**: Memory usage grows over time

### Design Issues

6. **No Async/Await Usage**
   - File reading is async but processing is synchronous
   - Doesn't leverage FastAPI's async capabilities
   - Blocks the event loop

7. **Poor Error Handling**
   - Generic exception catching loses context
   - Silent failures in validation
   - No proper logging

8. **No Transaction Management**
   - Delete operation not wrapped in transaction
   - Can leave orphaned records if import delete fails
   - Data consistency issues

9. **SQL Injection Vulnerability**
   - `/api/records/search` uses string formatting for LIMIT clause
   - **Security risk** if exposed to untrusted input

10. **No Pagination**
    - `/api/imports/{id}` returns ALL records
    - Can exhaust memory with large imports
    - No limit on result set size

### Data Validation Issues

11. **Weak Validation**
    - Email validation only checks for '@' character
    - Silent data coercion (age defaults to 0)
    - No schema enforcement

12. **Race Condition**
    - Duplicate file check not atomic
    - Multiple uploads of same file can race
    - Can create duplicate imports

## Expected Issues to Identify

During a live coding session, candidates should identify:

### Critical (Must Find)
- ⚠️ Synchronous processing blocking the API
- ⚠️ No database transaction handling
- ⚠️ Memory leak in processed_cache
- ⚠️ Individual commits per record (no batching)

### High Priority
- ⚠️ N+1 query pattern in get_imports
- ⚠️ SQL injection in search endpoint
- ⚠️ No pagination for large result sets
- ⚠️ Race condition in duplicate detection

### Medium Priority
- ⚠️ No connection pooling
- ⚠️ Poor error handling
- ⚠️ Weak validation
- ⚠️ No async/await usage

## Suggested Improvements

Candidates might propose:

1. **Use Background Tasks**: Process files asynchronously using `BackgroundTasks`
2. **Batch Inserts**: Use `executemany()` for bulk inserts
3. **Add Transactions**: Wrap operations in database transactions
4. **Connection Pooling**: Use SQLAlchemy or connection pool
5. **Pagination**: Add offset/limit to endpoints
6. **Fix N+1**: Use JOINs or batch queries
7. **Proper Async**: Make processing truly asynchronous
8. **Cache Cleanup**: Implement TTL or size limits on cache
9. **Parameterized Queries**: Fix SQL injection
10. **Better Validation**: Use Pydantic models for data validation

## Live Coding Exercise Ideas

### Task 1: Fix Synchronous Processing
"The API is slow when uploading files. Make file processing asynchronous using FastAPI's BackgroundTasks."

### Task 2: Add Database Transactions
"The delete operation can leave orphaned records. Add proper transaction handling."

### Task 3: Optimize Batch Inserts
"Loading 1000 records takes too long. Implement batch insertion."

### Task 4: Fix Memory Leak
"Memory usage grows over time. Identify and fix the memory leak."

### Task 5: Add Pagination
"Getting import details with 10,000 records crashes. Add pagination."

## Database Schema

```sql
-- Imports table
CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    total_records INTEGER DEFAULT 0,
    processed_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

-- Records table
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id INTEGER NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (import_id) REFERENCES imports (id)
);
```

## Tech Stack

- **FastAPI**: Modern Python web framework
- **SQLite**: Lightweight database
- **Pydantic**: Data validation
- **Uvicorn**: ASGI server

## Project Structure

```
backend-coding-challenge/
├── main.py              # Main application file
├── requirements.txt     # Python dependencies
├── sample_data.csv      # Sample CSV file
├── sample_data.json     # Sample JSON file
├── README.md           # This file
└── data_imports.db     # SQLite database (created on first run)
```

## Troubleshooting

### Port already in use
```bash
# Change port in main.py or kill process
lsof -ti:8000 | xargs kill -9
```

### Database locked
```bash
# Delete database and restart
rm data_imports.db
python main.py
```

### Large file upload fails
This is expected due to synchronous processing. The fix is part of the exercise!

## License

MIT License - For educational and interview purposes.

## Support

This is a live coding exercise. Issues are intentional for evaluation purposes.
