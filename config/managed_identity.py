"""Azure access tokens from the container's managed identity, so the app needs no keys for Azure services.

Container Apps provides IDENTITY_ENDPOINT and IDENTITY_HEADER; AZURE_CLIENT_ID names the app's user-assigned identity.
Run anywhere else, such as building the demo's policy index from this machine, the Azure CLI's sign-in is used.
"""

import os
import shutil
import subprocess

import httpx


def token(resource):
    """A bearer token for an Azure resource, e.g. https://storage.azure.com/ or https://cognitiveservices.azure.com."""
    if 'IDENTITY_ENDPOINT' not in os.environ:
        return subprocess.run([shutil.which('az'), 'account', 'get-access-token', '--resource', resource,
                               '--query', 'accessToken', '-o', 'tsv'],
                              capture_output=True, text=True, check=True).stdout.strip()
    response = httpx.get(os.environ['IDENTITY_ENDPOINT'], headers={'X-IDENTITY-HEADER': os.environ['IDENTITY_HEADER']},
                         params={'resource': resource, 'api-version': '2019-08-01',
                                 'client_id': os.environ['AZURE_CLIENT_ID']}, timeout=30)
    response.raise_for_status()
    return response.json()['access_token']
