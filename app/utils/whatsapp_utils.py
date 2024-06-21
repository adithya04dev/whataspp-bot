import time
import logging
from flask import current_app, jsonify
import json
import requests
import re
from io import BytesIO
from PIL import Image
from langchain_google_genai import GoogleGenerativeAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
import google.generativeai as genai
import PIL.Image
import os
import tempfile

def download_video(video_id):
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{video_id}"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        video_url = response.json().get('url')
        if video_url:
            video_response = requests.get(video_url, headers={
                'Authorization':  f"Bearer {current_app.config['ACCESS_TOKEN']}"
            }, stream=True)

            if video_response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        tmp_file.write(chunk)
                    return tmp_file.name
            else:
                logging.error(f"Failed to download video from URL: {video_response.text}")
        else:
            logging.error("No video URL found in the response")
    else:
        logging.error(f"Failed to get video info: {response.text}")
    return None

def process_video(video_path,prompt):
    genai.configure(api_key=current_app.config['GOOGLE_API_KEY'])
    model = genai.GenerativeModel(model_name="gemini-1.5-pro")
    
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        print('.', end='')
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    if video_file.state.name == "FAILED":
        raise ValueError(video_file.state.name)
    
    response = model.generate_content([video_file,prompt])
    return response.text

def download_image(image_id):
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{image_id}"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        image_url = response.json().get('url')
        if image_url:
            image_response = requests.get(image_url, headers={
                'Authorization':  f"Bearer {current_app.config['ACCESS_TOKEN']}"
            }, stream=True)

            if image_response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                    for chunk in image_response.iter_content(chunk_size=8192):
                        tmp_file.write(chunk)
                    return tmp_file.name
            else:
                logging.error(f"Failed to download image from URL: {image_response.text}")
        else:
            logging.error("No image URL found in the response")
    else:
        logging.error(f"Failed to get image info: {response.text}")
    return None

def process_image(image_path,prompt):
    genai.configure(api_key=current_app.config['GOOGLE_API_KEY'])
    model = genai.GenerativeModel(model_name="gemini-1.5-pro")
    
    image_file = genai.upload_file(path=image_path)


    
    response = model.generate_content([image_file, prompt])
    return response.text

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

def generate_response(response):
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

def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    print(message)
    if "text" in message:
        message_body = message["text"]["body"]
        response = generate_response(message_body)
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
    elif "image" in message:
        prompt = message['image'].get('caption', "Extract text from image")
        image_id = message["image"]["id"]
        image_path = download_image(image_id)
        if image_path:
            try:
                extracted_text = process_image(image_path,prompt)
                response = f"I received your image. Here's what I saw: {extracted_text}"
            finally:
                os.unlink(image_path)
        else:
            response = "Sorry, I couldn't process your image."
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
    elif "video" in message:
        video_id = message["video"]["id"]
        prompt=message['video'].get('caption', "Extract text from video")
        video_path = download_video(video_id)
        if video_path:
            try:
                extracted_text = process_video(video_path,prompt)
                response = f"I received your video. Here's what I saw: {extracted_text}"
            finally:
                os.unlink(video_path)
        else:
            response = "Sorry, I couldn't process your video."
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

