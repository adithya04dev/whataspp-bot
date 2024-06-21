
# from app.services.openai_service import generate_response
# OpenAI Integration
# response = generate_response(message_body, wa_id, name)
# response = process_text_for_whatsapp(response)
import logging
from flask import current_app, jsonify
import json
import requests
import re

def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")

def get_text_message_input(recipient, text):
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    })

def get_image_message_input(recipient, image_url):
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "image",
        "image": {"url": image_url}
    })

def generate_response(response):
    # Return text in uppercase
    return response.upper()

def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        log_http_response(response)
        return response

def process_text_for_whatsapp(text):
    pattern = r"\【.*?\】"
    text = re.sub(pattern, "", text).strip()
    pattern = r"\*\*(.*?)\*\*"
    replacement = r"*\1*"
    whatsapp_style_text = re.sub(pattern, replacement, text)
    return whatsapp_style_text
import requests
from io import BytesIO
from PIL import Image

def download_image(image_id):
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{image_id}"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        image_url = response.json().get('url')
        if image_url:
            # Download the actual image
            image_response = requests.get(image_url)
            if image_response.status_code == 200:
                return Image.open(BytesIO(image_response.content))
            else:
                logging.error(f"Failed to download image from URL: {image_response.text}")
        else:
            logging.error("No image URL found in the response")
    else:
        logging.error(f"Failed to get image info: {response.text}")
    return None

def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    
    if "text" in message:
        message_body = message["text"]["body"]
        response = generate_response(message_body)
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
    elif "image" in message:
        image_id = message["image"]["id"]
        image_url = download_image(image_id)
        if image_url:
            response = "I received your image. Here's what I think about it: [Your image analysis here]"
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
            # Optionally, you can send the image back or a processed version
            # data = get_image_message_input(current_app.config["RECIPIENT_WAID"], image_url)
        else:
            response = "Sorry, I couldn't process your image."
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
    else:
        logging.warning(f"Unsupported message type received: {message}")
        return

    send_message(data)

def is_valid_whatsapp_message(body):
    try:
        return (
            body.get("object") == "whatsapp_business_account" and
            body.get("entry") and
            body["entry"][0].get("changes") and
            body["entry"][0]["changes"][0].get("value") and
            body["entry"][0]["changes"][0]["value"].get("messages") and
            body["entry"][0]["changes"][0]["value"]["messages"][0]
        )
    except (KeyError, IndexError):
        return False
