"""
Download state/destination images from Wikimedia Commons and Unsplash.
Run: python scripts/download_state_images.py
"""
import os
import hashlib
import urllib.request
import urllib.parse

# Airport code -> state (lowercase for filename)
AIRPORT_TO_STATE = {
    'ATL': 'georgia', 'DFW': 'texas', 'DEN': 'colorado', 'ORD': 'illinois',
    'LAX': 'california', 'CLT': 'north_carolina', 'MCO': 'florida',
    'LAS': 'nevada', 'PHX': 'arizona', 'MIA': 'florida', 'SEA': 'washington',
    'IAH': 'texas', 'EWR': 'new_jersey', 'SFO': 'california', 'BOS': 'massachusetts',
    'MSP': 'minnesota', 'DTW': 'michigan', 'FLL': 'florida', 'JFK': 'new_york',
    'LGA': 'new_york', 'PHL': 'pennsylvania', 'BWI': 'maryland', 'DCA': 'virginia',
    'IAD': 'virginia', 'SAN': 'california', 'SLC': 'utah', 'TPA': 'florida',
    'PDX': 'oregon', 'HNL': 'hawaii', 'AUS': 'texas', 'MDW': 'illinois',
    'BNA': 'tennessee', 'DAL': 'texas', 'RDU': 'north_carolina', 'STL': 'missouri',
    'HOU': 'texas', 'SJC': 'california', 'MCI': 'kansas', 'OAK': 'california',
    'SAT': 'texas', 'RSW': 'florida', 'IND': 'indiana', 'CMH': 'ohio',
    'CVG': 'kentucky', 'PIT': 'pennsylvania', 'SMF': 'california', 'CLE': 'ohio',
    'MKE': 'wisconsin', 'SNA': 'california', 'ANC': 'alaska',
}

# State -> direct image URL (Unsplash - free, reliable)
STATE_IMAGE_URLS = {
    'georgia': 'https://images.unsplash.com/photo-1605649487212-47bdab064df7?w=400&h=300&fit=crop',
    'texas': 'https://images.unsplash.com/photo-1516549655169-df83a0774514?w=400&h=300&fit=crop',
    'colorado': 'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=400&h=300&fit=crop',
    'illinois': 'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=400&h=300&fit=crop',
    'california': 'https://images.unsplash.com/photo-1534190760961-74e8c1c5c3da?w=400&h=300&fit=crop',
    'north_carolina': 'https://images.unsplash.com/photo-1590577976098-d2ca5e96c2a8?w=400&h=300&fit=crop',
    'florida': 'https://images.unsplash.com/photo-1514214246283-d427a95c5d2f?w=400&h=300&fit=crop',
    'nevada': 'https://images.unsplash.com/photo-1605833556294-ea5c7a74f57d?w=400&h=300&fit=crop',
    'arizona': 'https://images.unsplash.com/photo-1519501025264-65ba15a82390?w=400&h=300&fit=crop',
    'washington': 'https://images.unsplash.com/photo-1542223616-9de9adb5e3e8?w=400&h=300&fit=crop',
    'new_jersey': 'https://images.unsplash.com/photo-1568667256549-094345857637?w=400&h=300&fit=crop',
    'massachusetts': 'https://images.unsplash.com/photo-1570168007204-dfb528c6958f?w=400&h=300&fit=crop',
    'minnesota': 'https://images.unsplash.com/photo-1578894381163-e72c17f2d45f?w=400&h=300&fit=crop',
    'michigan': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400&h=300&fit=crop',
    'new_york': 'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?w=400&h=300&fit=crop',
    'pennsylvania': 'https://images.unsplash.com/photo-1595071542104-dde77e4f25a6?w=400&h=300&fit=crop',
    'maryland': 'https://images.unsplash.com/photo-1590943031751-d4c59fe74a30?w=400&h=300&fit=crop',
    'virginia': 'https://images.unsplash.com/photo-1559511260-66a654ae982a?w=400&h=300&fit=crop',
    'utah': 'https://images.unsplash.com/photo-1506973035872-a4ec16b8e8d9?w=400&h=300&fit=crop',
    'oregon': 'https://images.unsplash.com/photo-1543783207-ec64e4d95325?w=400&h=300&fit=crop',
    'hawaii': 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&h=300&fit=crop',
    'tennessee': 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=400&h=300&fit=crop',
    'missouri': 'https://images.unsplash.com/photo-1572635706174-da77a0c7a399?w=400&h=300&fit=crop',
    'indiana': 'https://images.unsplash.com/photo-1548013146-72479768bada?w=400&h=300&fit=crop',
    'ohio': 'https://images.unsplash.com/photo-1605537992849-94988f39840a?w=400&h=300&fit=crop',
    'kansas': 'https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=400&h=300&fit=crop',
    'wisconsin': 'https://images.unsplash.com/photo-1555952494-efd681c7e3f9?w=400&h=300&fit=crop',
    'kentucky': 'https://images.unsplash.com/photo-1548013146-72479768bada?w=400&h=300&fit=crop',
    'alaska': 'https://images.unsplash.com/photo-1506973035872-a4ec16b8e8d9?w=400&h=300&fit=crop',
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, '..', 'static', 'images', 'states')


def download_image(url: str, filepath: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'FlightGrab/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        with open(filepath, 'wb') as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    states_done = set()
    for state in STATE_IMAGE_URLS:
        if state in states_done:
            continue
        states_done.add(state)
        url = STATE_IMAGE_URLS[state]
        ext = '.jpg'
        filepath = os.path.join(OUT_DIR, f"{state}{ext}")
        print(f"Downloading {state}...")
        if download_image(url, filepath):
            print(f"  Saved to {filepath}")
        else:
            print(f"  Skipped (using fallback)")


if __name__ == '__main__':
    main()
