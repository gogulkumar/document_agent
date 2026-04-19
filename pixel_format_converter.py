import argparse
from PIL import Image
import sys
import os

def convert_image(input_path, output_path, target_pixel_format=None, resize_dim=None, max_size_kb=None):
    """
    Reads an image, senses its pixel format (mode) and file format, 
    and converts it to the target format, dimensions, and file size.
    """
    try:
        with Image.open(input_path) as img:
            original_mode = img.mode
            original_file_format = img.format
            
            print(f"Loaded Image: {input_path}")
            print(f"Original File Format: {original_file_format}")
            print(f"Original Pixel Format (Mode): {original_mode}")
            print(f"Original Dimensions: {img.size}")
            
            converted_img = img
            
            # 1. Resize if needed
            if resize_dim:
                print(f"Resizing image to {resize_dim[0]}x{resize_dim[1]} px...")
                # Use Resampling.LANCZOS for high quality resizing in modern Pillow (or ANTIALIAS for older ones)
                resample_method = getattr(Image, 'Resampling', Image).LANCZOS
                converted_img = converted_img.resize(resize_dim, resample_method)
            
            # 2. Convert pixel format (mode) if target is provided
            if target_pixel_format and target_pixel_format.upper() != original_mode:
                target_mode = target_pixel_format.upper()
                print(f"Converting pixel format from {original_mode} to {target_mode}...")
                
                # Special handling for converting transparency formats to non-transparency
                if converted_img.mode in ('RGBA', 'LA', 'P') and target_mode == 'RGB':
                    bg = Image.new("RGB", converted_img.size, (255, 255, 255)) # White background
                    if converted_img.mode == 'P':
                        converted_img = converted_img.convert('RGBA')
                    
                    if len(converted_img.split()) == 4:
                        bg.paste(converted_img, mask=converted_img.split()[3])
                    else:
                        bg.paste(converted_img)
                    
                    converted_img = bg
                else:
                    try:
                        converted_img = converted_img.convert(target_mode)
                    except ValueError as e:
                        print(f"Error converting to {target_mode}: {e}")
                        return False
            elif target_pixel_format:
                 print(f"Image is already in '{target_pixel_format.upper()}' pixel format.")
            
            # 3. Save the image, managing file size if needed
            if max_size_kb and output_path.lower().endswith(('.jpg', '.jpeg', '.webp')):
                print(f"Attempting to compress image to be under {max_size_kb} KB...")
                quality = 95
                best_quality_saved = False
                while quality >= 10:
                    converted_img.save(output_path, quality=quality)
                    current_kb = os.path.getsize(output_path) / 1024
                    if current_kb <= max_size_kb:
                        print(f"Achieved target size! Quality: {quality}, Size: {current_kb:.2f} KB")
                        best_quality_saved = True
                        break
                    quality -= 5
                
                if not best_quality_saved:
                    current_kb = os.path.getsize(output_path) / 1024
                    print(f"Warning: Could not reduce file below {max_size_kb} KB. Minimum size achieved: {current_kb:.2f} KB")
            else:
                 # Standard save without file size constraints
                 # If target is PNG or other, size constraints aren't easily enforced without more complex quantization
                 if max_size_kb:
                     print("Warning: File size reduction only thoroughly supported for JPEG/WebP formats in this script. Saving normally.")
                 converted_img.save(output_path)
                 
            final_kb = os.path.getsize(output_path) / 1024
            print(f"Successfully saved converted image to: {output_path}")
            print(f"Final Image Size: {final_kb:.2f} KB")
            return True
            
    except FileNotFoundError:
        print(f"Error: Could not find the input image at {input_path}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert an image's pixel format, file type, dimensions, and file size. "
                    "The converted image will be saved in the same directory as the input image."
    )
    parser.add_argument("input", help="Path to the input image")
    parser.add_argument("--mode", "-m", help="Target pixel format/mode (e.g., RGB, RGBA, L for Grayscale)", default=None)
    parser.add_argument("--ext", "-e", help="Optional target file extension (e.g., .jpg, .png).", default=None)
    parser.add_argument("--suffix", "-s", help="Optional suffix for the new file name.", default="_converted")
    parser.add_argument("--width", "-W", type=int, help="Target width in pixels", default=None)
    parser.add_argument("--height", "-H", type=int, help="Target height in pixels", default=None)
    parser.add_argument("--max-size-kb", type=int, help="Target maximum file size in KB (only works well for JPG/WebP)", default=None)
    
    args = parser.parse_args()
    
    # Calculate output path in the same directory
    input_path = os.path.abspath(args.input)
    dir_name = os.path.dirname(input_path)
    base_name = os.path.basename(input_path)
    name_without_ext, original_ext = os.path.splitext(base_name)
    
    new_ext = args.ext if args.ext else original_ext
    if new_ext and not new_ext.startswith('.'):
        new_ext = '.' + new_ext
        
    suffix = args.suffix
    if args.suffix == "_converted" and args.mode:
        suffix = f"_{args.mode.upper()}"
        
    output_filename = f"{name_without_ext}{suffix}{new_ext}"
    output_path = os.path.join(dir_name, output_filename)
    
    print(f"Target Output Path: {output_path}")
    
    resize_dim = None
    if args.width and args.height:
        resize_dim = (args.width, args.height)
    elif args.width or args.height:
        print("Warning: Please provide both --width and --height for resizing.")
    
    success = convert_image(
        input_path, 
        output_path, 
        target_pixel_format=args.mode, 
        resize_dim=resize_dim, 
        max_size_kb=args.max_size_kb
    )
    if not success:
        sys.exit(1)
