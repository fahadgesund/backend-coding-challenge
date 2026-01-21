"""
Script to generate large CSV files for stress testing.
Use this to demonstrate performance issues with large files.
"""

import csv
import random
from faker import Faker

fake = Faker()

def generate_csv(filename: str, num_records: int):
    """Generate a CSV file with specified number of records."""
    
    print(f"Generating {filename} with {num_records} records...")
    
    departments = ["Engineering", "Marketing", "Sales", "HR", "Finance", "Operations", "Product"]
    cities = ["San Francisco", "New York", "Chicago", "Boston", "Seattle", "Austin", "Denver"]
    
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'email', 'age', 'department', 'city'])
        writer.writeheader()
        
        for i in range(num_records):
            writer.writerow({
                'name': fake.name(),
                'email': fake.email(),
                'age': random.randint(22, 65),
                'department': random.choice(departments),
                'city': random.choice(cities)
            })
            
            if (i + 1) % 1000 == 0:
                print(f"  Generated {i + 1} records...")
    
    print(f"✅ Created {filename}")


if __name__ == "__main__":
    # Install faker if not present
    try:
        from faker import Faker
    except ImportError:
        print("Installing faker...")
        import os
        os.system("pip install faker")
        from faker import Faker
    
    print("=" * 50)
    print("Large File Generator")
    print("=" * 50)
    print()
    
    # Generate different sizes
    sizes = [
        ("large_100.csv", 100),
        ("large_1000.csv", 1000),
        ("large_10000.csv", 10000),
    ]
    
    for filename, count in sizes:
        generate_csv(filename, count)
        print()
    
    print("=" * 50)
    print("Files generated!")
    print()
    print("Try uploading these to see performance issues:")
    print('  curl -X POST "http://localhost:8000/api/upload" -F "file=@large_1000.csv"')
    print()
    print("Watch how long it takes and if the API remains responsive!")
    print("=" * 50)
