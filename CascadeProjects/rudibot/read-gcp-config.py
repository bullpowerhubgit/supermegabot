import json

with open('RudiBot-Secure-API/gcp-config.json') as f:
    config = json.load(f)

project_id = config['project']['id']
print(f"GCP Project ID: {project_id}")

# Also extract other useful info
project_name = config['project']['name']
project_number = config['project']['number']
client_email = config['service_account']['client_email']

print(f"Project Name: {project_name}")
print(f"Project Number: {project_number}")
print(f"Service Account: {client_email}")

# Check enabled APIs
print("\nEnabled APIs:")
for api_name, api_config in config['apis'].items():
    status = "✅" if api_config.get('enabled', False) else "❌"
    print(f"  {status} {api_name}")
