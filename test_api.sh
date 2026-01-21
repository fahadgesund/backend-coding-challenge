#!/bin/bash

# Test script for Data Import API
# Demonstrates the performance issues

echo "========================================="
echo "Data Import API - Test Script"
echo "========================================="
echo ""

# Check if server is running
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Error: API server is not running"
    echo "Start it with: python main.py"
    exit 1
fi

echo "✅ API server is running"
echo ""

# Test 1: Upload CSV file
echo "Test 1: Uploading CSV file..."
echo "Note: Watch how long this takes and if API is responsive during upload"
START=$(date +%s)
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@sample_data.csv" \
  -w "\nHTTP Status: %{http_code}\n" \
  2>/dev/null
END=$(date +%s)
DURATION=$((END - START))
echo "⏱️  Upload took: ${DURATION} seconds"
echo ""

# Test 2: Get all imports
echo "Test 2: Getting all imports..."
curl -s http://localhost:8000/api/imports | python3 -m json.tool
echo ""

# Test 3: Get import details
echo "Test 3: Getting import details (import_id=1)..."
curl -s http://localhost:8000/api/imports/1 | python3 -m json.tool
echo ""

# Test 4: Search records
echo "Test 4: Searching records..."
curl -s -X POST "http://localhost:8000/api/records/search" \
  -H "Content-Type: application/json" \
  -d '{"status": "valid", "limit": 5}' | python3 -m json.tool
echo ""

# Test 5: Get statistics
echo "Test 5: Getting statistics..."
curl -s http://localhost:8000/api/stats | python3 -m json.tool
echo ""

# Test 6: Upload JSON file
echo "Test 6: Uploading JSON file..."
START=$(date +%s)
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@sample_data.json" \
  -w "\nHTTP Status: %{http_code}\n" \
  2>/dev/null
END=$(date +%s)
DURATION=$((END - START))
echo "⏱️  Upload took: ${DURATION} seconds"
echo ""

# Test 7: Try to upload same file again (should detect duplicate)
echo "Test 7: Uploading duplicate file..."
curl -s -X POST "http://localhost:8000/api/upload" \
  -F "file=@sample_data.csv" | python3 -m json.tool
echo ""

echo "========================================="
echo "Tests completed!"
echo ""
echo "Key observations:"
echo "- How long did uploads take?"
echo "- Was API responsive during uploads?"
echo "- Check memory usage: ps aux | grep python"
echo "- Try concurrent uploads to see blocking"
echo "========================================="
