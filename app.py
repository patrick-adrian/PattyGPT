import os
import unicodedata
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuration
ALLOWED_NUMBERS = ['+16478639456', '+16479042199', '+9056175814']  # Replace with your number
MAX_SMS_CHUNKS = 3
CHUNK_SIZE = 160
SMS_COST_PER_SEGMENT = 0.0075
GPT_COST_PER_TOKEN = 0.001  # Average estimate for GPT-3.5

# Initialize Flask
app = Flask(__name__)

# Sanitize function: removes non-ASCII, newlines
def sanitize_sms(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.replace("\n", " ").replace("\r", " ").strip()

# Split long messages into 160-char SMS segments
def split_into_sms_chunks(text, chunk_size=CHUNK_SIZE):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

@app.route("/sms", methods=['POST'])
def sms_reply():
    sender = request.form['From']
    body = request.form['Body']
    print(f"📩 From {sender}: {body}")

    if sender not in ALLOWED_NUMBERS:
        print("❌ Unauthorized sender")
        return "Unauthorized", 403

    try:
        # Get GPT response
        chat_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are PattyGPT, a concise assistant. Reply using plain text only. "
                        "Avoid emojis, newlines, or special characters. Limit your response to 480 characters max."
                    )
                },
                {"role": "user", "content": body}
            ]
        )

        # Step 1: Sanitize reply
        reply = chat_response.choices[0].message.content.strip()
        reply = sanitize_sms(reply)

        # Step 2: Reserve room for cost line
        placeholder_cost_note = "~ PattyGPT 🤖 (cost info)"
        reserved_chars = len(placeholder_cost_note)
        max_reply_chars = (MAX_SMS_CHUNKS * CHUNK_SIZE) - reserved_chars
        reply = reply[:max_reply_chars]

        # Step 3: Token + cost tracking
        total_tokens = chat_response.usage.total_tokens
        gpt_cost = round(total_tokens * GPT_COST_PER_TOKEN, 5)

        # Step 4: Split and calculate SMS cost
        chunks = split_into_sms_chunks(reply)
        sms_cost = round(len(chunks) * SMS_COST_PER_SEGMENT, 5)
        total_cost = round(gpt_cost + sms_cost, 5)

        # Step 5: Append cost note to last SMS
        cost_note = f"~ PattyGPT 🤖 (GPT: ${gpt_cost}, SMS: ${sms_cost}, Total: ${total_cost})"
        available_space = CHUNK_SIZE - len(cost_note)
        chunks[-1] = chunks[-1][:available_space] + " " + cost_note

        print("✅ Final SMS Chunks:")
        for i, chunk in enumerate(chunks):
            print(f"[{i+1}] {repr(chunk)} ({len(chunk)} chars)")

    except Exception as e:
        print("⚠️ Error:", e)
        chunks = ["Sorry, something went wrong. Please try again later. ~ PattyGPT 🤖"]

    # Build Twilio SMS response
    twilio_response = MessagingResponse()
    for chunk in chunks:
        twilio_response.message(chunk)
    return str(twilio_response)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

