import os
import urllib.request

def import_efo():
    # Configuration
    # Stable GitHub release link for efo.owl
    EFO_URL = "https://github.com/EBISPOT/efo/releases/latest/download/efo.owl"
    IMPORT_DIR = "imports"
    OUTPUT_FILE = os.path.join(IMPORT_DIR, "efo.owl")

    # Create directory if it doesn't exist
    if not os.path.exists(IMPORT_DIR):
        print(f"Creating directory: {IMPORT_DIR}")
        os.makedirs(IMPORT_DIR)

    # Download EFO
    print(f"Downloading EFO from: {EFO_URL}")
    try:
        # Using Request with User-Agent to avoid potential blocks
        req = urllib.request.Request(EFO_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(OUTPUT_FILE, 'wb') as out_file:
                # Read and write in chunks as EFO can be very large
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)
        
        print(f"Successfully imported EFO to {OUTPUT_FILE}")
        
        # Check file size
        file_size = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
        print(f"File size: {file_size:.2f} MB")
        
    except Exception as e:
        print(f"Error downloading EFO: {e}")

if __name__ == "__main__":
    import_efo()
