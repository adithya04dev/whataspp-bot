import time
import logging
from flask import current_app, jsonify
import json
import requests
from langchain_core.messages import HumanMessage
import base64
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_together import ChatTogether
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
from datetime import datetime

_USER_ROLE = "user"
_MODEL_ROLE = "model"
import random
def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
def  ask( content: content_types.ContentType):
    genai.configure(api_key=current_app.config['GOOGLE_API_KEY'])
    model = genai.GenerativeModel(model_name="gemini-1.5-flash-002")
    content = content_types.to_content(content)
    if not content.role:
        content.role = _USER_ROLE
    # history.append(content)

    response=model.generate_content(contents=content)
                                    # print(history)
    try:
        text=response.text
        # text+=str(history)

        # history.append(response.candidates[0].content)

    except Exception as e:
        # text="try sending once again"
        text=str(response)
        text+=str(e)
        # history=history[:-1]
    return text


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

def process_image(image_path,prompt):
    
    image_file = genai.upload_file(path=image_path)
    
    res= ask([image_file, prompt])
    os.remove(image_path)
    genai.delete_file(image_file.name)
    return res

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

sent_text=[]

def process_whatsapp_message(body):
    global sent_text 
    # print(f"total message body{body}")
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    # print(body["entry"][0]["changes"][0]["value"]["messages"])
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    unique_id=message['id']
    if unique_id in sent_text:
      return 

  
    message_timestamp = int(message["timestamp"])
  
  # Convert the message timestamp to a datetime object
    message_time = datetime.fromtimestamp(message_timestamp)
  
  # Get the current time
    current_time = datetime.now()
  
  # Calculate the time difference
    time_difference = current_time - message_time
    print("current time : ",current_time)
    print("message time : ",message_time)
    if time_difference.total_seconds() > 180:
        print("Message is older than 3 minutes, skipping.")
        return
    print(message)
    with shelve.open("threads_db1") as threads_shelf:
        text=threads_shelf.get(wa_id, ' ')

    llm=ChatTogether(model='Qwen/Qwen2.5-72B-Instruct-Turbo')
    # verifier=ChatOpenAI(model="gpt-4o-mini")
    response=''
    verifier_response=None
    verifier_prompt=""" I had given a task to my assistant: 
    {text}.
    He gave me this response:
    {response}.

    I want you to verify if the response is correct or not.
    Let's verify step by step if the response is correct or not. 
    return Final answer.
        """
    if "text" in message:
        
        message_body = message["text"]["body"]
        if text.lower().startswith("context"):
            # send_message(f"text extracted from given images is \n {text}")
            text+=' '+message_body
            initial_response = llm.invoke(text).content
            response=f" initial assistant response: \n {initial_response} "
            print("context answering mode")
            text='  '

        elif message_body.startswith("more"):
            text+=message_body
            print("adding more context using text mode")
            response="text context was added to the prompt."
            verifier_response=None
            
        else:
            text=message_body
            initial_response = llm.invoke(text).content
            print("one shot text answering mode")
            response=f" initial assistant response: \n {initial_response} "
        response+= f'\ntext given was: \n{text}'




    elif "image" in message:
        prompt = message['image'].get('caption', "Here's image")

        
        # print(message)
        # print(prompt)
        image_id = message["image"]["id"]
        image_path = download_image(image_id)
        if image_path:


            extracted_text = process_image(image_path,text)

            if text.lower().startswith("context"):
                text+=' '+ extracted_text
                response=f"Context was added to the prompt. "
                print("context adding using image mode")

            else:
                # send_message(f"text extracted from given single image is \n {extracted_text}")
    
                # initial_response = llm.invoke(f"{text} \n {extracted_text}").content
                # image_text=f"{text} \n {extracted_text}"
                response=extracted_text
                print("one shot image answering mode")
    
        else:
            response= "Sorry, I couldn't process your image."
            verifier_response=None


    elif "video" in message:

        response = "Sorry, I couldn't process your video."
    else:
        response = f"Unsupported message type received: {message}\n Can only support text,image,video..not docs.."
        logging.warning(f"Unsupported message type received: {message}")
    with shelve.open("threads_db1", writeback=True) as threads_shelf:
        threads_shelf[wa_id] = text
    # response+=str(history)
    data = get_text_message_input(wa_id, response)
    print(response)
    send_message(data)
    sent_text.append(unique_id)
    if verifier_response!=None:
        data = get_text_message_input(wa_id, f"Verifier assistant response: \n {verifier_response}")
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
