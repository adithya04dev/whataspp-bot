import time
import logging
from flask import current_app, jsonify
import json
import requests
from langchain_core.messages import HumanMessage
import base64
from langchain_openai import ChatOpenAI
import os
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
import shelve
import time
from google.generativeai.types import content_types
_USER_ROLE = "user"
_MODEL_ROLE = "model"
import random
def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
def  ask( content: content_types.ContentType,history):
    genai.configure(api_key=current_app.config['GOOGLE_API_KEY'])
    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    content = content_types.to_content(content)
    if not content.role:
        content.role = _USER_ROLE
    history.append(content)
    safe = [
        {
            "category": "HARM_CATEGORY_DANGEROUS",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE",
        },]
    response=model.generate_content(contents=content,safety_settings=safe)
                                    # print(history)
    try:
        text=response.text
        # text+=str(history)

        # history.append(response.candidates[0].content)

    except Exception as e:
        # text="try sending once again"
        text=str(response)
        text+=str(e)
        history=history[:-1]
    return text,history

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

def process_video(video_path,prompt,history):

    
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        print('.', end='')
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    if video_file.state.name == "FAILED":
        raise ValueError(video_file.state.name)
    print("in video"+prompt)
    return ask([video_file,prompt],history)
    # response = model.generate_content([video_file,prompt])
    # return response.text

def download_image(image_id):
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{image_id}"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    random_number = str(random.randint(1, 1000000000))
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        image_url = response.json().get('url')
        if image_url:
            image_response = requests.get(image_url, headers={
                'Authorization':  f"Bearer {current_app.config['ACCESS_TOKEN']}"
            }, stream=True)

            if image_response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg',prefix=random_number) as tmp_file:
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

def process_image(image_path,prompt,history):
    
    image_file = genai.upload_file(path=image_path)
    
    res,his= ask([image_file, prompt],history)
    os.remove(image_path)
    genai.delete_file(image_file.name)
    return res,his

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

# def generate_response(prompt,history):

    # response = model.generate_content([prompt])
    # return response.text
    # return ask([prompt])

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
text="Extract the question and options from image and answer it. Think step by step."
def process_whatsapp_message(body):
    
    # print(f"total message body{body}")
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    # print(body["entry"][0]["changes"][0]["value"]["messages"])
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    print(message)
    global text
    with shelve.open("threads_db1") as threads_shelf:
        history=threads_shelf.get(wa_id, [])
    
    llm = ChatOpenAI(model="gpt-4o-mini")
    response=''
    if "text" in message:
        message_body = message["text"]["body"]
        text=message_body
        message = HumanMessage(content=[{"type": "text", "text": text}], )
        response1 = llm.invoke([message])
        print(response1.content)
        response=response1.content
        # if(message_body.lower()=="cleanup"):
        #     history=[]
        #     response="done"
        # elif message_body.lower()=="history":
        #     response=str(history)
        # else:           
        #     response,history = ask([message_body],history)



    elif "image" in message:
        prompt = message['image'].get('caption', "Here's image")

        
        # print(message)
        # print(prompt)
        image_id = message["image"]["id"]
        image_path = download_image(image_id)
        if image_path:
            # image_data=encode_image(image_path)
            message = HumanMessage(
                content=[
                    {"type": "text", "text": text}
                ],
            )
            # response1 = llm.invoke([message])
            # print(response1.content)
            # response=response1.content
            extracted_text,history = process_image(image_path,"Extraxt text,content,questions,options ..from image",history)
            message = HumanMessage(
                  content=[
                      {"type": "text", "text": text+ extracted_text}
                  ],
              )
            response1 = llm.invoke([message])
            print(response1.content)
            response=response1.content
    
        else:
            response= "Sorry, I couldn't process your image."


    elif "video" in message:
        video_id = message["video"]["id"]
        prompt=message['video'].get('caption', "here's the video")
        # print(prompt)
        video_path = download_video(video_id)
        if video_path:
            extracted_text,history = process_video(video_path,prompt,history)
            response =extracted_text 
        else:
            response = "Sorry, I couldn't process your video."
    else:
        response = f"Unsupported message type received: {message}\n Can only support text,image,video..not docs.."
        logging.warning(f"Unsupported message type received: {message}")
    with shelve.open("threads_db1", writeback=True) as threads_shelf:
        threads_shelf[wa_id] = history
    # response+=str(history)
    data = get_text_message_input(wa_id, response)

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
