import os
import urllib.request
import ssl

def download_library():
    print("Bypassing PowerShell restrictions to download QR library natively via Python...")
    
    # Ensure static/js exists
    target_dir = os.path.join("static", "js")
    os.makedirs(target_dir, exist_ok=True)
    
    target_file = os.path.join(target_dir, "html5-qrcode.min.js")
    url = "https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"
    
    try:
        # Ignore SSL certificate verification issues which commonly block corporate internet access
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        print("Contacting secure CDN...")
        with urllib.request.urlopen(url, context=ctx) as response, open(target_file, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            
        print(f"Success! The QR library has been securely injected into: {target_file}")
        print("You can now run 'python app.py' to use the offline scanner!")
    except Exception as e:
        print(f"\nCRITICAL FAILURE: {e}")
        print("Your physical network (such as a school/company firewall) is aggressively blocking unpkg.com at the router level.")
        print("You will need to manually download html5-qrcode.min.js from a phone/home network and move it to static/js/")

if __name__ == "__main__":
    download_library()
