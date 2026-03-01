import json
import pandas as pd
from pathlib import Path

# Read all JSON files from the dataset
dataset_dir = Path('storage/datasets/default')
json_files = sorted(dataset_dir.glob('*.json'))

data = []
for json_file in json_files:
    if json_file.name.startswith('__'):
        continue  # Skip metadata files
    
    with open(json_file, 'r', encoding='utf-8') as f:
        product = json.load(f)
        
        # Flatten the nested structure for Excel
        row = {
            'SKU': product.get('sku', ''),
            'Brand': product.get('brand', ''),
            'Price': product.get('price', ''),
            'Currency': product.get('currency', ''),
            'Availability': product.get('availability', ''),
            'Size': product.get('size', ''),
            'Barcode': product.get('barcode', ''),
            
            # Arabic fields
            'Arabic_Name': product.get('arabic', {}).get('name', ''),
            'Arabic_Category': product.get('arabic', {}).get('category', ''),
            'Arabic_Description': product.get('arabic', {}).get('description', ''),
            'Arabic_URL': product.get('arabic', {}).get('url', ''),
            
            # English fields
            'English_Name': product.get('english', {}).get('name', ''),
            'English_Category': product.get('english', {}).get('category', ''),
            'English_Description': product.get('english', {}).get('description', ''),
            'English_URL': product.get('english', {}).get('url', ''),
            
            # Images
            'Main_Image': product.get('images', {}).get('main', ''),
            'Gallery_Images': ', '.join(product.get('images', {}).get('gallery', [])),
            
            # Nutrition facts - General
            'Nutriscore': product.get('nutrition_facts', {}).get('nutriscore_grade', ''),
            'Serving_Size': product.get('nutrition_facts', {}).get('serving_size', ''),
            
            # Nutrition facts - Per 100g
            'Energy_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('energy_kcal', ''),
            'Fat_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('fat', ''),
            'Saturated_Fat_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('saturated_fat', ''),
            'Carbs_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('carbohydrates', ''),
            'Sugars_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('sugars', ''),
            'Fiber_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('fiber', ''),
            'Protein_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('proteins', ''),
            'Salt_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('salt', ''),
            'Sodium_100g': product.get('nutrition_facts', {}).get('per_100g', {}).get('sodium', ''),
            
            # Nutrition facts - Per Serving
            'Energy_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('energy_kcal', ''),
            'Fat_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('fat', ''),
            'Saturated_Fat_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('saturated_fat', ''),
            'Carbs_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('carbohydrates', ''),
            'Sugars_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('sugars', ''),
            'Fiber_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('fiber', ''),
            'Protein_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('proteins', ''),
            'Salt_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('salt', ''),
            'Sodium_Serving': product.get('nutrition_facts', {}).get('per_serving', {}).get('sodium', ''),
        }
        
        data.append(row)

# Create DataFrame
df = pd.DataFrame(data)

# Export to Excel
output_file = 'carrefour_products.xlsx'
df.to_excel(output_file, index=False, engine='openpyxl')

print(f'✅ Exported {len(data)} products to {output_file}')
print(f'Columns: {", ".join(df.columns)}')