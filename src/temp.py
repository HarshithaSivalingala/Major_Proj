from openai import OpenAI

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="s",

completion = client.chat.completions.create(
  extra_body={},
  model="openai/gpt-oss-20b:free",
  messages=[
    {
      "role": "user",
      "content": 
       "hello",
      
    }
  ]
)
print(completion.choices[0].message.content)
