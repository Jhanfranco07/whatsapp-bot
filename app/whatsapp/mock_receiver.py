import requests


def send_mock_inbound(api_url: str, phone_number: str, message: str):
    response = requests.post(
        f"{api_url.rstrip('/')}/webhooks/whatsapp/inbound",
        json={"phone_number": phone_number, "message": message, "raw_payload": {}},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()
