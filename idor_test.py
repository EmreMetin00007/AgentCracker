import requests

def analyze():
    base_url = "https://605d12c2d6b6cb87.siberlig.org"
    session = requests.Session()
    
    # Get main page
    print("--- Fetching Main Page ---")
    res = session.get(base_url)
    print("Status:", res.status_code)
    print(res.text[:500])

    # Try login
    print("\n--- Attempting Login ---")
    login_url = base_url + "/login" # Guessing login URL, or maybe it's on the main page. Let's see the main page first.
    
if __name__ == "__main__":
    analyze()
