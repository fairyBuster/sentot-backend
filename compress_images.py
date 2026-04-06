import os
from PIL import Image

def get_size(path):
    return os.path.getsize(path)

def compress_images(directory):
    total_saved = 0
    files = [f for f in os.listdir(directory) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    print(f"Processing {len(files)} images in {directory}...")
    
    for filename in files:
        filepath = os.path.join(directory, filename)
        original_size = get_size(filepath)
        
        try:
            with Image.open(filepath) as img:
                # Resize if too large (e.g., max 1600px)
                max_dimension = 1600
                if img.width > max_dimension or img.height > max_dimension:
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                
                # Save options
                save_kwargs = {'optimize': True}
                
                if filename.lower().endswith(('.jpg', '.jpeg')):
                    save_kwargs['quality'] = 80
                elif filename.lower().endswith('.png'):
                    # For PNG, we can try to reduce colors if it's a photo, but that's risky.
                    # Just optimize for now.
                    # Check if image mode is P (palette) or RGBA
                    # If RGBA but no actual transparency, we could convert to RGB, but PNG RGB is still large.
                    # Let's just use optimize=True and compress_level=9 (default is usually 6)
                    save_kwargs['compress_level'] = 9
                
                # Save to a temporary file first to check size
                temp_path = filepath + ".tmp"
                format = img.format  # Get original format (e.g. JPEG, PNG)
                if not format:
                    if filename.lower().endswith(('.jpg', '.jpeg')):
                        format = 'JPEG'
                    elif filename.lower().endswith('.png'):
                        format = 'PNG'
                
                img.save(temp_path, format=format, **save_kwargs)
                
                new_size = os.path.getsize(temp_path)
                
                if new_size < original_size:
                    os.replace(temp_path, filepath)
                    saved = original_size - new_size
                    total_saved += saved
                    print(f"Compressed {filename}: {original_size/1024:.1f}KB -> {new_size/1024:.1f}KB (Saved {saved/1024:.1f}KB)")
                else:
                    os.remove(temp_path)
                    print(f"Skipped {filename}: No reduction (Original: {original_size/1024:.1f}KB)")
                    
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    print(f"\nTotal space saved: {total_saved / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    target_dir = "/root/Ocerinbackend/media/products"
    if os.path.exists(target_dir):
        compress_images(target_dir)
    else:
        print(f"Directory not found: {target_dir}")
