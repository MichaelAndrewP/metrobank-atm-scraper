import json
import os
import requests
import geohash2 as geohash
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import googlemaps
from dotenv import load_dotenv
from google.cloud import firestore
import pytz  # Import pytz for time zone conversion

# Load environment variables from .env file
# Ensure to enable Geocoding API
load_dotenv()

# Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

# Initialize Google Maps client with API key from environment variable
gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))

# Initialize Firestore client
db = firestore.Client()

# Define the URL
url = 'https://04v62bn13i-dsn.algolia.net/1/indexes/MB_locator_prod/query?x-algolia-agent=Algolia%20for%20JavaScript%20(4.14.2)%3B%20Browser%20(lite)&x-algolia-api-key=a379bd4fb9d35d6cba39d090fbb8b52b&x-algolia-application-id=04V62BN13I'

# Define the payloads for the POST request
payloads = [
    {"query": "Angeles City pampanga"} # done
   # {"query": "Pampanga"}
   # {"query": "Makati City metro manila"},
   # {"query": "Taguig City metro manila"},
   # {"query": "Pasig City metro manila"},
   # {"query":"Oriental Mindoro"}
    # Add more payloads as needed
]

bank_document_path = 'banks/Ke5JR8olV22SDvKwrdD0' 

# Function to fetch JSON content using POST request
def fetch_json(url, payload):
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data from {url}: {e}")
        return None

def reverse_geocode(lat, lng):
    results = gmaps.reverse_geocode((lat, lng))
    
    address = {
        'city': '',
        'country': '',
        'fullAddress': '',
        'postalCode': '',
        'stateProvince': '',
        'streetAddress': ''
    }
    
    for result in results:
        address_components = result['address_components']
        
        for component in address_components:
            if 'locality' in component['types']:
                address['city'] = component['long_name']
            elif 'country' in component['types']:
                address['country'] = component['short_name']
            elif 'postal_code' in component['types']:
                address['postalCode'] = component['long_name']
            elif 'administrative_area_level_1' in component['types']:
                address['stateProvince'] = component['long_name']
            elif 'route' in component['types']:
                address['streetAddress'] = component['long_name']
        
        # If we have at least one of the required components, we can use this result
        if any(address.values()):
            address['fullAddress'] = result['formatted_address']
            return address
    
    return None

# Function to transform item into the new model
def transform_item(item):
    # Convert current time to Asia/Manila time zone
    manila_tz = pytz.timezone('Asia/Manila')
    current_time = datetime.now(manila_tz)
    
    geohash_code = geohash.encode(item['lat'], item['lng'])
    external_id = f"{item['name']}_{current_time.strftime('%Y%m%d%H%M%S')}"
    address_details = reverse_geocode(item['lat'], item['lng'])
    geopoint = firestore.GeoPoint(item['lat'], item['lng'])
    
    # Create a reference to the bank document using the variable
    bank_ref = db.document(bank_document_path)
 
    
    return {
        'address': address_details if address_details else {
            'city': "",
            'country': "PH",
            'fullAddress': item['address'],
            'postalCode': "",
            'stateProvince': "",
            'streetAddress': ""
        },
        'bank': bank_ref,
        'createdAt': current_time,
        'updatedAt': current_time,
        'externalId': external_id,
        'id': '',  # Leave id empty initially
        'lastReportedStatus': {
            'reportedBy': {
                'appVersion': '',
                'deviceId': '',
                'deviceModel': '',
                'osVersion': ''
                        },
            'status': 'online', 
            'timestamp': current_time,
        },       
        'location': {
            'geohash': geohash_code,
            'geopoint': geopoint
        },
        'name': item['name'],
        'qrCode': 'https://example.com/qrcode/ ',
        'status': 'online',
        'addedBy': 'admin',
    }

# Function to create an object from the response data
def create_object_from_data(data):
    # Example: Create a list of dictionaries from the response data
    objects = []
    for item in data.get('hits', []):
        obj = {
            'name': item.get('name'),
            'lat': item.get('_geoloc', {}).get('lat'),
            'lng': item.get('_geoloc', {}).get('lng')
        }
        objects.append(obj)
    return objects

# Main procedure
def main():
    all_data=[]
    not_saved_count = 0

    for payload in payloads:
        json_content = fetch_json(url, payload)
        if json_content:
            print(f"Fetched data successfully for query: {payload['query']}. Creating objects from response data.")
            objects = create_object_from_data(json_content)
            for obj in objects:
                new_object = transform_item(obj)
                print(new_object)
                all_data.append(new_object)
        else:
            print(f"Failed to fetch data for query: {payload['query']}.")

    for item in all_data:
        print(item)
        try:
            # Check if the item already exists in Firestore
            existing_docs = db.collection('atms').where('name', '==', item['name']).stream()
            if any(existing_docs):
                print(f"Item with name {item['name']} already exists. Skipping.")
                not_saved_count += 1
                continue
            
            # Save each item to Firestore and get the document reference
            doc_ref = db.collection('atms').add(item)[1]
            # Update the item with the document ID
            item['id'] = doc_ref.id
            # Update the document with the new ID
            db.collection('atms').document(doc_ref.id).set(item)
        except Exception as e:
            print(f"Error saving item to Firestore: {e}")

    print(f"Total number of objects: {len(all_data)}")
    print(f"Number of objects not saved because it already exists or raw data is not available: {not_saved_count}")

if __name__ == "__main__":
    main()