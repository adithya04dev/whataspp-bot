from typing import Optional, Dict
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.memory import ChatMessageHistory
import os
class ChatBot:
    def __init__(self):
        # Initialize the message history
        self.chat_history = ChatMessageHistory()
        
        # Define the prompt template with placeholders for chat history and dynamic inputs
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant. Answer all questions to the best of your ability."),
            MessagesPlaceholder(variable_name="chat_history"),
            # We'll dynamically add either text or image based on the input
            ("human", "{input_text}"),
            ("human", [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,{image_url}"},
                }
            ])
        ])
        
        # Initialize the language model
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-002")
        
        # Create the chain once
        self.chain = self.prompt | self.llm
        
        # Wrap the chain with message history
        self.chain_with_message_history = RunnableWithMessageHistory(
            self.chain,
            lambda session_id: self.chat_history,
            input_messages_key="input_text",
            history_messages_key="chat_history",
        )
    
    def chat(self, user_input: Optional[str] = None, image_url: Optional[str] = None) -> str:
        input_data: Dict[str, Optional[str]] = {}
        
        if user_input:
            input_data["input_text"] = user_input
        if image_url:
            input_data["image_url"] = image_url
        
        response = self.chain_with_message_history.invoke(
            input_data,
            {"configurable": {"session_id": "unused"}}
        )
        
        # Update chat history based on the inputs
        if user_input:
            self.chat_history.add_user_message(user_input)
        if image_url:
            # Assuming you want to store image URLs as user messages
            self.chat_history.add_user_message({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_url}"}
            })
        
        # Add the AI's response to the history
        self.chat_history.add_ai_message(response.content)
        
        return response.content

# Usage example
if __name__ == "__main__":
    bot = ChatBot()
    
    # Text-only input
    print(bot.chat(user_input="whats this!"))
    
    # Image-only input
    base64_image_data = "https://www.google.com/imgres?q=images%20input%20langchain%20chatprompt%20template&imgurl=https%3A%2F%2Fmiro.medium.com%2Fv2%2Fresize%3Afit%3A1374%2F1*C-VbyYG5Iukrpc_3VbHvhw.png&imgrefurl=https%3A%2F%2Ftonylixu.medium.com%2Flangchain-prompt-template-0359d96090c5&docid=fpmeq3v2r9g1HM&tbnid=oWgEPueeOYt6QM&vet=12ahUKEwic4ZDXrsWJAxWmSWwGHZk5HJUQM3oECBoQAA..i&w=687&h=487&hcb=2&ved=2ahUKEwic4ZDXrsWJAxWmSWwGHZk5HJUQM3oECBoQAA"  # Your base64 image string here
    print(bot.chat(image_url=base64_image_data))
    
    # Both text and image
    print(bot.chat(user_input="What's in this image?", image_url=base64_image_data))