from google import genai
import os
os.environ['GEMINI_API_KEY'] = "AIzaSyCXIfIFxKXUvSPJs3fRRkQk8mQNT5LKzBY"

# import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()


# response = client.models.generate_content(
#     model="gemini-2.5-pro", contents="Explain which model you are in a few words"
# )


from google.genai import types

with open('/Users/kobe/Downloads/图片20250609150137.png', 'rb') as f:
    image_bytes = f.read()

response = client.models.generate_content(
    model='gemini-2.5-pro',
    contents=[
      types.Part.from_bytes(
        data=image_bytes,
        mime_type='image/png',
      ),
      'Caption this image.'
    ]
  )


print(response.text)